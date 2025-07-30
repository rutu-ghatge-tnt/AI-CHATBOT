from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.rag_pipeline import get_rag_chain
from app.memory import get_or_create_session_id, get_history, add_to_history
from fastapi.responses import JSONResponse, StreamingResponse
from serpapi import GoogleSearch
import asyncio
import json
import time
from datetime import datetime

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
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": "SERPAPI_KEY",  # Replace with your actual SerpAPI key
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

        return "\n".join(snippets)
    except Exception:
        return "Sorry, I couldn't fetch online information right now."

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, raw_request: Request):
    user_query = request.query.strip().lower()
    clean_query = user_query.rstrip("?!.")
    identity_triggers = {
        "who are you", "what is your name", "tell me about yourself",
        "who is skinsage", "are you a bot", "your identity"
    }

    session_id = get_or_create_session_id(raw_request)
    history = get_history(session_id)

    # Handle identity triggers
    if clean_query in identity_triggers:
        return JSONResponse(
            content={"answer": "Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant! How can I help you today?"},
            headers={"Set-Cookie": f"session_id={session_id}"}
        )

    # Handle offensive messages
    if is_offensive(user_query):
        return JSONResponse(
            content={"answer": "I'm here to help with skincare, not to battle words. Let's keep it friendly! 😊"},
            headers={"Set-Cookie": f"session_id={session_id}"}
        )

    # Build conversation context
    chat_context = ""
    for turn in history[-5:]:
        chat_context += f"User: {turn['query']}\nAssistant: {turn['response']}\n"
    chat_context += f"User: {user_query}"

    async def stream_response():
        try:
            rag_result = rag_chain.invoke({"query": chat_context})
            print("RAG Result:", rag_result)
            answer = rag_result.get("result", "").strip()
        except Exception as e:
            print("Error from RAG chain:", e)
            answer = "Sorry, something went wrong while processing your question."

        if not answer:
            answer = "I couldn't find any relevant information in my documents. Please try asking something else!"

        no_info_phrases = [
            "sorry, something went wrong while processing your question.",
            "i couldn't find any relevant information in my documents.",
            "i don't have that information", "i don't know", "not sure",
            "don't have enough information", "i do not have that information",
            "sorry, i don't know", "cannot find", "not found", "no relevant information"
        ]

        if any(phrase in answer.lower() for phrase in no_info_phrases):
            web_answer = web_search_and_summarize(user_query)
            answer += "\n\nSince I couldn't find the answer in my documents, here's what I found online:\n\n" + web_answer

        add_to_history(session_id, user_query, answer)

        # Stream response sentence-by-sentence
        for sentence in answer.split("\n"):
            if sentence.strip():
                chunk = {"response": sentence + "\n", "done": False}
                yield json.dumps(chunk) + "\n"
                await asyncio.sleep(0.05)

        # Final chunk
        yield json.dumps({"response": "", "done": True}) + "\n"


    return StreamingResponse(
        stream_response(),
        media_type="application/json",
        headers={"Set-Cookie": f"session_id={session_id}"}
    )
