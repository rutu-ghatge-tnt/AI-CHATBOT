# app/chatbot/rag_pipeline.py
"""RAG orchestration via LangGraph (retrieve → generate). Chroma + embeddings stay on LangChain integrations."""

from __future__ import annotations

from typing import Any, AsyncIterator, List, NotRequired, TypedDict

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import END, START, StateGraph

from app.chatbot.llm_claude import get_claude_llm
from app.config import (
    CHROMA_DB_PATH,
    RAG_FETCH_K,
    RAG_RETRIEVAL_K,
    RAG_STREAM_BUFFER_MAX,
    RAG_STREAM_RAW_TOKENS,
)

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"

SYSTEM_PROMPT = """You are SkinSage, a friendly and expert virtual skincare assistant inside the SkinBB Metaverse.

Use **chat history** only for follow-ups and coreference (e.g. "it", "that product", "the first one"). Do not treat history as a source of facts.

Use **retrieved context** as the source of truth for product details, ingredients, and platform facts when it is relevant. If the question is about SkinBB navigation, features, or URLs, answer like a product expert using that context.

If the user asks about "price", "how to use", "benefits", or to "compare" products *without naming products*, assume they mean items from your **previous answer** in chat history; use only those products.

Rules:
- Expand skincare abbreviations (e.g., HA -> Hyaluronic Acid, BHA -> Beta Hydroxy Acid).
- Format in **structured Markdown** with real line breaks between sections and bullets.
- Give user-friendly navigation help, not developer route templates.
- Do NOT output raw placeholders like `/product/[slug]`, `/community/q/[slug]`, `/help/[slug]` unless the user explicitly asks for route patterns.
- For dynamic pages, provide the base path and clear action wording (example: "Open `/community`, then tap a question thread").
- Prefer concrete, clickable links users can use now (for example: `/shop`, `/bbshop`, `/account/orders`, `/account/shelf`, `/help`, `/knowledge-feed`, `/blog`).
- Prefer this structure when it fits:

### ✅ Key Insights
- 2–4 concise bullets; define terms if needed

### 🧴 Related Products (if any)
- Only if the user explicitly asks for recommendations or related products.

### 💡 Tips / Recommendations
- Usage, compatibility, skin-type notes; precautions if relevant

### 🌟 Summary
- Short wrap-up

Special cases:
- Too generic → ask for something more specific.
- No useful retrieved context for the question → say: Sorry, I couldn't find enough info to answer that properly. Feel free to ask me another skincare-related question!
- Off-topic → I'm not sure about that, but I'm here to help with anything skincare-related!
- Greeting only → 🌟 Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant. Ask me anything about skincare — ingredients, routines, or products!
"""


class RAGState(TypedDict):
    """Graph state: inputs from API are query + history; nodes add context and result."""

    query: str
    history: str
    context: NotRequired[str]
    source_documents: NotRequired[List[Document]]
    result: NotRequired[str]


_vectorstore: Chroma | None = None


def _get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL),
        )
    return _vectorstore


def _get_retriever():
    k = max(1, RAG_RETRIEVAL_K)
    fetch_k = max(k + 1, RAG_FETCH_K)
    return _get_vectorstore().as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": fetch_k},
    )


def _format_context(docs: List[Document]) -> str:
    if not docs:
        return "(No matching documents retrieved.)"
    parts: List[str] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        src = meta.get("source") or meta.get("module") or ""
        head = f"[{i}]" + (f" ({src})" if src else "")
        parts.append(f"{head}\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


def _build_user_prompt_block(query: str, history: str, context: str) -> str:
    hist = (history or "").strip() or "(none)"
    return f"""Retrieved context (use for facts about products and the SkinBB platform when relevant):
---
{context}
---

Chat history (follow-ups / coreference only):
---
{hist}
---

User question:
{query}
"""


def _aimessage_chunk_text(chunk) -> str:
    raw = getattr(chunk, "content", None)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: List[str] = []
        for part in raw:
            if isinstance(part, dict):
                parts.append(part.get("text", "") or "")
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(raw)


def _build_graph():
    retriever = _get_retriever()
    llm = get_claude_llm(streaming=False)
    if llm is None:
        return None

    def retrieve(state: RAGState) -> dict[str, Any]:
        docs = retriever.invoke(state["query"])
        return {
            "source_documents": docs,
            "context": _format_context(docs),
        }

    def generate(state: RAGState) -> dict[str, Any]:
        user_block = _build_user_prompt_block(
            state["query"],
            state.get("history") or "",
            state.get("context") or "(No context.)",
        )
        msg = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_block),
            ]
        )
        text = msg.content
        if isinstance(text, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        return {"result": (text or "").strip()}

    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


class RAGChainAdapter:
    """Wraps LangGraph so callers can use .invoke() and read result + source_documents like RetrievalQA."""

    def __init__(self, graph):
        self._graph = graph

    def invoke(self, input_dict: dict) -> dict:
        if self._graph is None:
            return {"result": "", "source_documents": []}
        out = self._graph.invoke(
            {
                "query": input_dict.get("query", ""),
                "history": input_dict.get("history", "") or "",
            }
        )
        return {
            "result": out.get("result", ""),
            "source_documents": out.get("source_documents", []),
        }


_cached_rag = None


def get_rag_chain():
    """
    LangGraph-backed RAG with the same invoke shape as before:
    invoke({"query": str, "history": str}) -> {"result": str, "source_documents": [...]}
    """
    global _cached_rag
    if _cached_rag is not None:
        return _cached_rag
    graph = _build_graph()
    if graph is None:
        print("Warning: Claude LLM not available, returning None")
        return None
    _cached_rag = RAGChainAdapter(graph)
    return _cached_rag


async def stream_rag_tokens(query: str, history: str) -> AsyncIterator[str]:
    """Retrieve then stream LLM output token-by-token (same prompt contract as the graph)."""
    retriever = _get_retriever()
    docs = retriever.invoke(query)
    context = _format_context(docs)
    llm = get_claude_llm(streaming=True)
    if llm is None:
        yield "Chatbot service is currently unavailable. Please check your API configuration."
        return
    user_block = _build_user_prompt_block(query, history, context)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_block),
    ]
    buf = ""
    async for chunk in llm.astream(messages):
        piece = _aimessage_chunk_text(chunk)
        if not piece:
            continue
        if RAG_STREAM_RAW_TOKENS:
            yield piece
            continue
        buf += piece
        ends_ws = buf[-1].isspace()
        too_long = len(buf) >= max(64, RAG_STREAM_BUFFER_MAX)
        if ends_ws or too_long:
            yield buf
            buf = ""
    if buf and not RAG_STREAM_RAW_TOKENS:
        yield buf
