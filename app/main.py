# app/main.py

from fastapi import FastAPI
from app.api import router as api_router
from app.image_extractor.route import router as image_extractor_router  # ✅ NEW import
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SkinBB AI Skincare Chatbot",
    description="An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0"
)

# ✅ CORS Configuration: Allow only your frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tt.skintruth.in", "http://localhost:5174"],     
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Existing chatbot API
app.include_router(api_router, prefix="/api")

# ✅ New image-to-JSON API 
app.include_router(image_extractor_router, prefix="/api")  # <--- added here

# ✅ Root healthcheck endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."}
