# app/chatbot/api.py
from fastapi import APIRouter, HTTPException
from app.chatbot.rag_pipeline import get_rag_chain, stream_rag_tokens
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
from openai import OpenAI

router = APIRouter()

# Lazy-init RAG so import doesn't crash the whole app if Chroma perms are wrong on boot.
_rag_chain = None


def _get_rag_chain_cached():
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = get_rag_chain()
    return _rag_chain

OFFENSIVE_WORDS = {"stupid", "idiot", "dumb", "hate", "shut up"}

# Initialize OpenAI client for formulator chatbot
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None

class ChatTurn(BaseModel):
    query: str
    response: str

class ChatRequest(BaseModel):
    query: str
    history: list[ChatTurn] = []

class FormulatorChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []
    conversation_state: dict = {}

def is_offensive(text: str) -> bool:
    text_lower = text.lower()
    return any(word in text_lower for word in OFFENSIVE_WORDS)


def _is_simple_greeting(text: str) -> bool:
    """Avoid full RAG + LLM for hi/hello — Chroma is large and makes trivial turns slow."""
    t = text.rstrip("?!.").lower().strip()
    if not t:
        return False
    one_word = {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "hai",
        "howdy",
        "namaste",
        "gm",
        "helloo",
        "helo",
    }
    short_phrases = {
        "hi there",
        "hey there",
        "hello there",
        "good morning",
        "good afternoon",
        "good evening",
        "hi!",
        "hello!",
        "hey!",
    }
    if t in short_phrases:
        return True
    words = t.split()
    if len(words) <= 3 and words[0] in one_word:
        return True
    return False


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    user_query = request.query.strip()
    clean_query = user_query.rstrip("?!.").lower()

    identity_triggers = {
        "who are you", "what is your name", "tell me about yourself",
        "who is skinsage", "are you a bot", "your identity"
    }

    if clean_query in identity_triggers:
        return JSONResponse(content={
            "answer": "🌟 Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant. Ask me anything about skincare — ingredients, routines, or products!"
        })

    if _is_simple_greeting(user_query):
        greet = (
            "🌟 Hi! I'm **SkinSage**, your skincare assistant on SkinBB. "
            "Ask about products, ingredients, routines, or where to find things on the site (shop, account, shelf, help)."
        )

        async def stream_greeting():
            yield json.dumps({"response": greet + "\n", "done": False}) + "\n"
            yield json.dumps({"response": "", "done": True}) + "\n"

        return StreamingResponse(stream_greeting(), media_type="application/json")

    if is_offensive(user_query):
        return JSONResponse(content={
            "answer": "I'm here to help with skincare, not to battle words. Let's keep it friendly! 😊"
        })

    # Format frontend-passed history
    chat_context = "\n".join([
        f"User: {turn.query}\nAssistant: {turn.response}"
        for turn in request.history[-5:]
        if turn.query and turn.response
    ])

    async def stream_response():
        try:
            if _get_rag_chain_cached() is None:
                msg = "Chatbot service is currently unavailable. Please check your API configuration."
                yield json.dumps({"response": msg, "done": False}) + "\n"
            else:
                async for piece in stream_rag_tokens(user_query, chat_context):
                    yield json.dumps({"response": piece, "done": False}) + "\n"
        except Exception as e:
            print("RAG error:", e)
            yield json.dumps(
                {"response": "Sorry, something went wrong while processing your question.", "done": False}
            ) + "\n"

        yield json.dumps({"response": "", "done": True}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/json")


@router.post("/chatbot/chat")
async def formulator_chatbot_endpoint(request: FormulatorChatRequest):
    """
    Formulator chatbot endpoint using OpenAI API.
    Implements rule-based flow: ask intent -> ask inspirations -> provide redirects.
    """
    if not openai_client:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
        )
    
    user_message = request.message.strip()
    conversation_state = request.conversation_state or {}
    conversation_history = request.conversation_history or []
    
    # Detect user intent from message
    intent = detect_intent(user_message)
    has_intent = bool(intent)
    asked_inspirations = conversation_state.get("askedInspirations", False)
    current_intent = conversation_state.get("intent")
    
    # Build system prompt based on conversation state
    system_prompt = """You are a helpful formulation assistant for SkinBB, a cosmetic formulation platform. 
Your role is to guide users to the right features based on their needs.

Available features:
1. Decode Formulations - Analyze and decode existing formulations with detailed ingredient breakdown
2. Create Formulations - Create new cosmetic formulations with ingredient management and compliance checking
3. Market Research - Find products with matching ingredients
4. Compare - Compare ingredients from two different product URLs
5. Account - Manage account settings

Follow this flow:
1. If user hasn't specified intent, ask what they want to do (decode, create, etc.)
2. Once intent is detected, ask if they have any inspirations or reference products
3. After asking about inspirations, provide helpful information about the platform and suggest redirecting to the relevant feature

Be friendly, concise, and helpful. Always explain what the platform can do for them."""
    
    # Build conversation messages for OpenAI
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history (last 10 messages to avoid token limits)
    for msg in conversation_history[-10:]:
        if msg.get("role") and msg.get("content"):
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Add current user message
    messages.append({"role": "user", "content": user_message})
    
    # Determine if we should ask about inspirations
    should_ask_inspirations = False
    if has_intent and not current_intent:
        # New intent detected, we'll ask about inspirations
        should_ask_inspirations = True
        conversation_state["intent"] = intent
        conversation_state["askedInspirations"] = False
    elif current_intent and not asked_inspirations:
        # We have intent, now asking about inspirations
        should_ask_inspirations = True
        conversation_state["askedInspirations"] = True
    
    # Add context about what to ask next
    if should_ask_inspirations and not asked_inspirations:
        messages.append({
            "role": "system",
            "content": "The user has indicated they want to " + intent + ". Now ask them if they have any inspirations or reference products they'd like to use."
        })
    
    try:
        # Call OpenAI API
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o for better understanding
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        )
        
        assistant_message = response.choices[0].message.content.strip()
        
        # Determine redirect buttons
        redirect_buttons = []
        if current_intent or intent:
            intent_to_use = current_intent or intent
            intent_lower = intent_to_use.lower()
            
            # Map intent to route
            intent_route_map = {
                "decode": "/formulations/decode",
                "create": "/formulations/create",
                "market research": "/market-research",
                "compare": "/compare",
                "account": "/account",
            }
            
            if intent_lower in intent_route_map:
                route = intent_route_map[intent_lower]
                redirect_buttons = [{
                    "label": f"Go to {intent_to_use.title()}",
                    "route": route,
                    "description": get_feature_description(intent_lower)
                }]
        
        # Build response
        response_data = {
            "message": assistant_message,
            "intent": current_intent or intent,
            "hasInspirations": should_ask_inspirations and not asked_inspirations,
            "redirectButtons": redirect_buttons if (current_intent or intent) and asked_inspirations else [],
        }
        
        # Add platform info if this is a general query
        if not has_intent and not current_intent:
            response_data["platformInfo"] = """SkinBB is India's First Cosmetic Formulation Platform. 
You can:
- Decode existing formulations to understand ingredient breakdowns
- Create new formulations with compliance checking
- Research the market to find similar products
- Compare products side by side
- Manage your account and preferences

What would you like to do today?"""
        
        return JSONResponse(content=response_data)
        
    except Exception as e:
        print(f"OpenAI API error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get response from chatbot: {str(e)}"
        )


def detect_intent(message: str) -> Optional[str]:
    """Detect user intent from message"""
    message_lower = message.lower()
    
    if any(word in message_lower for word in ["decode", "analyze", "break down", "understand", "ingredient breakdown"]):
        return "decode"
    if any(word in message_lower for word in ["create", "make", "new formulation", "build", "develop"]):
        return "create"
    if any(word in message_lower for word in ["market research", "find products", "search", "research", "similar products"]):
        return "market research"
    if any(word in message_lower for word in ["compare", "comparison", "side by side"]):
        return "compare"
    if any(word in message_lower for word in ["account", "settings", "profile", "preferences"]):
        return "account"
    
    return None


def get_feature_description(intent: str) -> str:
    """Get description for a feature based on intent"""
    descriptions = {
        "decode": "Analyze and decode existing formulations with detailed ingredient breakdown",
        "create": "Create new cosmetic formulations with ingredient management and compliance checking",
        "market research": "Find products with matching ingredients",
        "compare": "Compare ingredients from two different product URLs",
        "account": "Manage your account settings",
    }
    return descriptions.get(intent, "")
