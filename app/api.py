from fastapi import APIRouter
from pydantic import BaseModel
from app.rag_pipeline import get_rag_chain
from serpapi import GoogleSearch 

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

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.query.strip().lower()
    clean_query = user_query.rstrip("?!.")
    identity_triggers = {
        "who are you", "what is your name", "tell me about yourself",
        "who is skinsage", "are you a bot", "your identity"
    }
    if clean_query in identity_triggers:
        return ChatResponse(
            answer="Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant! How can I help you today?"
        )

    if is_offensive(user_query):
        return ChatResponse(
            answer="I'm here to help with skincare, not to battle words. Let's keep it friendly! 😊"
        )

    try:
        rag_result = rag_chain.invoke({"query": user_query})
        print("RAG Result:", rag_result)  # Debug print to terminal/log
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
        answer = (
            "Since I couldn't find the answer in my documents, here's what I found online:\n\n"
            + web_answer
        )

    return ChatResponse(answer=answer)
