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
    SKINBB_PUBLIC_BASE_URL,
)

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"


def _log_llm_api_error(provider: str, exc: BaseException) -> None:
    """Print Anthropic/LangChain error details to stderr (shows up in gunicorn/journalctl/docker logs)."""
    parts = [f"[{provider}]", type(exc).__name__ + ":", str(exc)]
    sc = getattr(exc, "status_code", None)
    if sc is not None:
        parts.append(f"status_code={sc}")
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(f"body={body!r}")
    resp = getattr(exc, "response", None)
    if resp is not None:
        txt = getattr(resp, "text", None)
        if txt:
            parts.append(f"response.text={txt[:2000]!r}")
    print(" ".join(parts), flush=True)


SYSTEM_PROMPT = """You are SkinSage, a friendly and expert virtual skincare assistant inside the SkinBB Metaverse.

Use **chat history** only for follow-ups and coreference (e.g. "it", "that product", "the first one"). Do not treat history as a source of facts.

Use **retrieved context** as the source of truth for product details, ingredients, and platform facts when it is relevant. If the question is about SkinBB navigation, features, or URLs, answer like a product expert using that context.

Context chunk tags: **inventory_product** or **inventory_products** = SkinBB's own catalog. **external_product** = third-party retailers only — never describe those as sold "on BB Shop" or "on our store".

**Links:** Only **inventory_product** chunks (from the **`products`** Mongo collection, already **published** in this index) may be shared with **Shop deep links** or SkinBB site URLs for buying. For **external_product** chunks (separate **`externalproducts`** collection / third-party catalog), give facts (brand, category, ingredients, price band) only — **never** SkinBB `/product` links, **Shop deep links**, or any SkinBB shop URL that implies buying that item on SkinBB.

If the retrieved context includes any **inventory_product** chunks, you **do** have SkinBB catalog data: summarize and recommend from those with **Shop deep links**. Do **not** say you lack BB Shop inventory or only have external retailers in that case.

If the user asks about "price", "how to use", "benefits", or to "compare" products *without naming products*, assume they mean items from your **previous answer** in chat history; use only those products.

Rules:
- Do **not** open with "Welcome to SkinBB Metaverse", long self-introductions, or welcome emoji lines unless the user's message is **only** a greeting (hi/hello). For real questions, start with the answer.
- Expand skincare abbreviations (e.g., HA -> Hyaluronic Acid, BHA -> Beta Hydroxy Acid).
- Format in **structured Markdown** with real line breaks between sections and bullets.
- Give user-friendly navigation help, not developer route templates.
- Do NOT output raw placeholders like `/product/[slug]`, `/community/q/[slug]`, `/help/[slug]` unless the user explicitly asks for route patterns.
- For dynamic pages, provide the base path and clear action wording (example: "Open `/community`, then tap a question thread").
- If the user message includes a **deployment public base URL** block, format SkinBB navigation as **Markdown links** using that base only (example: `[Shop](https://example.com/shop)`). Do not use bare `/path` as the primary link in that case.
- If there is **no** base URL block, same-origin UIs may use path-style hints (for example: `/shop`, `/bbshop`, `/help`).
- When the user asks about **BB Shop**, **Shop**, or buying on SkinBB, and the base URL block lists **Preset links**, include at least `[BB Shop](...)` and `[Shop](...)` from that block even if no inventory chunks were retrieved.
- When retrieved context includes **Shop deep links** for a catalog product, use those **exact** URLs (same path `/product/...`, same query string, including `id` and variant params such as `shadem`) in Markdown links when you recommend that product. Do not invent slugs or omit/rename query params.
- **Never** invent product PDPs as `/bbshop?id=...` or `/shop?id=...` with a **text slug** in `id` — those are **listing** pages, not product detail pages, and `id=` on those routes is **not** the same as the catalog PDP `id` (a **24-character hex** MongoDB ObjectId from **Shop deep links**). If you have no **Shop deep link** line for an item, do not fabricate a buy URL; use preset `[BB Shop]` / `[Shop]` browsing links only.
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
- No useful retrieved context for the question → answer briefly; if the user asked about shopping or BB Shop, still give the preset Shop / BB Shop links from the base URL block and suggest they browse or name a product. Do **not** use the long "couldn't find info" boilerplate when a shopping link would help.
- Off-topic → I'm not sure about that, but I'm here to help with anything skincare-related!
- Greeting only → 🌟 Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant. Ask me anything about skincare — ingredients, routines, or products!
"""


class RAGState(TypedDict):
    """Graph state: inputs from API are query + history; nodes add context and result."""

    query: str
    history: str
    public_base: NotRequired[str]
    context: NotRequired[str]
    source_documents: NotRequired[List[Document]]
    result: NotRequired[str]


_vectorstore: Chroma | None = None


def _get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        try:
            _vectorstore = Chroma(
                persist_directory=CHROMA_DB_PATH,
                embedding_function=HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL),
            )
        except Exception as e:
            msg = str(e).lower()
            if "readonly" in msg or "read-only" in msg or "readonly database" in msg:
                raise RuntimeError(
                    f"Chroma cannot write under {CHROMA_DB_PATH!r}. "
                    "Ingest likely ran as a different user than Gunicorn. "
                    "Fix: sudo chown -R <gunicorn-user>:<group> "
                    f"{CHROMA_DB_PATH} && sudo chmod -R u+rwX {CHROMA_DB_PATH}"
                ) from e
            raise
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
        typ = meta.get("type") or meta.get("mongo_logical") or ""
        tag = typ or src
        head = f"[{i}]" + (f" ({tag})" if tag else "")
        parts.append(f"{head}\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


def _shop_product_discovery_intent(ql: str) -> bool:
    """
    True when the user is clearly asking for product picks (not ingredient science trivia).
    Used so retrieval searches **inventory_product** chunks; otherwise MMR can drown
    catalog rows with external_product or unrelated docs (e.g. brand + 'suggest products').
    """
    verbs = (
        "suggest",
        "recommend",
        "show me",
        "give me",
        "looking for",
        "what should i get",
        "what can i get",
        "what should i buy",
        "what can i buy",
        "need a",
        "need an",
        "need some",
        "want a",
        "want an",
        "want some",
        "which ",
        "best ",
        "top ",
    )
    productish = (
        "product",
        "products",
        "skincare",
        "moisturizer",
        "moisturiser",
        "cleanser",
        "serum",
        "sunscreen",
        "toner",
        "cream",
        "lotion",
        "routine",
        "kit",
        "combo",
        "patch",
        "patches",
        "acne patch",
        "spot patch",
        "pimple patch",
    )
    if any(v in ql for v in verbs) and any(p in ql for p in productish):
        return True
    if ("daily use" in ql or "everyday" in ql or "daily routine" in ql) and any(
        p in ql for p in productish
    ):
        return True
    return False


def _prefers_skinbb_catalog(q: str) -> bool:
    """True when the user is asking about SkinBB / BB Shop catalog (not generic skincare trivia)."""
    ql = (q or "").lower().strip()
    if not ql:
        return False
    compact = "".join(c for c in ql if c.isalnum())
    if "bbshop" in compact or "bb shop" in ql:
        return True
    if "skinbb" in compact or "skin bb" in ql:
        if any(
            w in ql
            for w in (
                "shop",
                "buy",
                "product",
                "catalog",
                "store",
                "inventory",
                "bb shop",
                "website",
                "site",
            )
        ):
            return True
    if any(
        phrase in ql
        for phrase in (
            "on skinbb",
            "from skinbb",
            "our shop",
            "your shop",
            "on your site",
            "on your website",
        )
    ):
        return True
    if _shop_product_discovery_intent(ql):
        return True
    return False


def _retrieval_query(user_question: str) -> str:
    """Bias embedding search toward SkinBB inventory when the user clearly means our shop."""
    q = (user_question or "").strip()
    if not q:
        return q
    ql = q.lower()
    compact = "".join(ch for ch in ql if ch.isalnum())
    hints: List[str] = []
    if "bbshop" in compact or "bb shop" in ql:
        hints.append(
            "SkinBB MongoDB products collection catalog inventory BB Shop productName slug listing"
        )
    if any(
        phrase in ql
        for phrase in (
            "on skinbb",
            "skinbb shop",
            "your shop",
            "our shop",
            "on your site",
            "available on",
        )
    ):
        hints.append("SkinBB shop catalog inventory product listing")
    if _shop_product_discovery_intent(ql):
        hints.append(
            "SkinBB MongoDB products collection BB Shop catalog inventory brand productName slug"
        )
    if hints:
        return q + "\n\n" + " ".join(hints)
    return q


def _retrieve_documents(user_question: str) -> List[Document]:
    """
    Prefer Mongo catalog chunks when the user clearly means BB Shop / SkinBB store,
    so external_product Nykaa-style docs do not dominate MMR.
    """
    rq = _retrieval_query(user_question)
    k = max(5, RAG_RETRIEVAL_K)
    fetch_k = max(k + 2, RAG_FETCH_K)
    vs = _get_vectorstore()

    if _prefers_skinbb_catalog(user_question):
        inv_filter: dict[str, str] = {"type": "inventory_product"}
        try:
            inv = vs.max_marginal_relevance_search(
                rq, k=k, fetch_k=fetch_k, filter=inv_filter
            )
        except Exception:
            try:
                inv = vs.similarity_search(rq, k=k, filter=inv_filter)
            except Exception:
                inv = []
        if inv:
            return inv
        try:
            inv = vs.max_marginal_relevance_search(
                rq,
                k=k,
                fetch_k=fetch_k,
                filter={"mongo_logical": "inventory_products"},
            )
        except Exception:
            try:
                inv = vs.similarity_search(
                    rq, k=k, filter={"mongo_logical": "inventory_products"}
                )
            except Exception:
                inv = []
        if inv:
            return inv
        print(
            "[rag] Catalog intent (e.g. BB Shop) but no chunks with "
            "type=inventory_product or mongo_logical=inventory_products. "
            "Re-run Mongo ingest with the same CHROMA_DB_PATH as this API, or check metadata."
        )

    return _get_retriever().invoke(rq)


def _link_formatting_instructions(public_base: str = "") -> str:
    base = (public_base or "").strip().rstrip("/") or (SKINBB_PUBLIC_BASE_URL or "").strip().rstrip(
        "/"
    )
    if not base:
        return ""
    return f"""Deployment public site base URL (required for SkinBB navigation in your reply):
{base}

Preset links (copy exactly when the user asks about shopping, BB Shop, or where to buy on SkinBB):
[Shop]({base}/shop)
[BB Shop]({base}/bbshop)

Use Markdown links for other paths the same way: `[label]({base}<path>)` with `<path>` starting with `/`. Do not use bare `/shop`-style paths as the main navigation when this block is present."""


def _build_user_prompt_block(
    query: str, history: str, context: str, public_base: str = ""
) -> str:
    hist = (history or "").strip() or "(none)"
    link_block = _link_formatting_instructions(public_base)
    link_section = f"{link_block}\n\n" if link_block else ""
    return f"""Retrieved context (use for facts about products and the SkinBB platform when relevant):
---
{context}
---

{link_section}Chat history (follow-ups / coreference only):
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
    llm = get_claude_llm(streaming=False)
    if llm is None:
        return None

    def retrieve(state: RAGState) -> dict[str, Any]:
        docs = _retrieve_documents(state["query"])
        return {
            "source_documents": docs,
            "context": _format_context(docs),
        }

    def generate(state: RAGState) -> dict[str, Any]:
        user_block = _build_user_prompt_block(
            state["query"],
            state.get("history") or "",
            state.get("context") or "(No context.)",
            state.get("public_base") or "",
        )
        try:
            msg = llm.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=user_block),
                ]
            )
        except Exception as e:
            _log_llm_api_error("Claude/Anthropic (invoke)", e)
            raise
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
                "public_base": input_dict.get("public_base") or "",
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


async def stream_rag_tokens(
    query: str, history: str, *, public_base: str = ""
) -> AsyncIterator[str]:
    """Retrieve then stream LLM output token-by-token (same prompt contract as the graph)."""
    docs = _retrieve_documents(query)
    context = _format_context(docs)
    llm = get_claude_llm(streaming=True)
    if llm is None:
        yield "Chatbot service is currently unavailable. Please check your API configuration."
        return
    user_block = _build_user_prompt_block(query, history, context, public_base)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_block),
    ]
    buf = ""
    try:
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
    except Exception as e:
        _log_llm_api_error("Claude/Anthropic (astream)", e)
        raise
    if buf and not RAG_STREAM_RAW_TOKENS:
        yield buf
