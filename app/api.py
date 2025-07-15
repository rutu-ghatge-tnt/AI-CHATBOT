# app/api.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.rag_pipeline import get_rag_chain
from serpapi import GoogleSearch # type: ignore

router = APIRouter()
rag_chain = get_rag_chain()

OFFENSIVE_WORDS = {"stupid", "idiot", "dumb", "hate", "shut up"}

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str

def is_offensive(text: str) -> bool:
    text_lower = text.lower()
    return any(word in text_lower for word in OFFENSIVE_WORDS)

def web_search_and_summarize(query: str) -> str:
    params = {
        "engine": "google",
        "q": query,
        "api_key": "cb04da4c0c4df4e4d85334a3030add8f5142584eea2c8f328e2d670c58711f5e",  # Replace with your actual SerpAPI key
        "num": 3
    }
    search = GoogleSearch(params)
    results = search.get_dict()

    snippets = []
    for organic_result in results.get("organic_results", []):
        snippet = organic_result.get("snippet")
        if snippet:
            snippets.append(snippet)

    if not snippets:
        return "Sorry, I could not find relevant information online."

    # Simple summary by joining snippets
    return "\n".join(snippets)

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.query.strip()

    if is_offensive(user_query):
        return ChatResponse(
            answer="I'm here to help with skincare, not to battle words. Let's keep it friendly! 😊"
        )

    rag_result = rag_chain({"query": user_query})
    answer = rag_result.get("answer") or rag_result.get("result") or ""

    no_info_phrases = [
        "don’t have enough information here",
        "i do not have that information",
        "sorry, i don't know",
        "cannot find",
        "don't have an answer"
    ]

    if any(phrase in answer.lower() for phrase in no_info_phrases):
        web_answer = web_search_and_summarize(user_query)
        answer += (
            "\n\nSince I couldn't find the answer in my documents, here's what I found online:\n"
            + web_answer
        )

    return ChatResponse(answer=answer)
