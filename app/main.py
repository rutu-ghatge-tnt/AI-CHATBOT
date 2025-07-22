# app/main.py

from fastapi import FastAPI
from app.api import router as api_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SkinBB AI Skincare Chatbot",
    description="An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0"
)

# CORS Configuration: Allow only your frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tt.skintruth.in"],  # Specific frontend origin
    #allow_origins= ["http://localhost:5173"],  
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, PUT, DELETE, OPTIONS
    allow_headers=["*"],  # Allows all headers like Content-Type, Authorization
)


# API Routes
app.include_router(api_router, prefix="/api")

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."}


#changes check