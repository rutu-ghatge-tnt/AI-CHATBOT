# app/main.py
from fastapi import FastAPI
from app.api import router as api_router

app = FastAPI(
    title="SkinBB AI Skincare Chatbot",
    description="An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0"
)

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact."}
