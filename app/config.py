# app/config.py

from pathlib import Path
import os
from dotenv import load_dotenv

# Get the absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env file in project root
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ .env file not found at: {env_path}")

# Claude API settings
from typing import Optional

CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY")
# Use CLAUDE_MODEL if set, otherwise fall back to MODEL_NAME, otherwise use default
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"

# Get the absolute path to the directory where this config.py file resides
APP_DIR = Path(__file__).parent.resolve()

# Chroma persist dir: absolute path so Gunicorn/cron/ingest all use the same DB regardless of cwd.
# On Linux, set CHROMA_DB_PATH in .env if the vector store lives outside the repo.
_default_chroma = (BASE_DIR / "chroma_db").resolve()
CHROMA_DB_PATH: str = str(Path(os.getenv("CHROMA_DB_PATH", str(_default_chroma))).resolve())

# Optional: Validate critical env variables early
if not CLAUDE_API_KEY:
    print("Warning: CLAUDE_API_KEY is not set in the .env file. Chatbot functionality will be limited.")
else:
    print(f"Claude API key loaded successfully (model: {CLAUDE_MODEL})")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME = os.getenv("DB_NAME", "skin_bb")

# Chatbot RAG: Mongo collection names (override if your DB uses different casing)
MONGO_RAG_INGEST_ENABLED: bool = os.getenv("MONGO_RAG_INGEST_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
MONGO_RAG_PRODUCTS_COLLECTION: str = os.getenv("MONGO_RAG_PRODUCTS_COLLECTION", "products")
MONGO_RAG_VARIANTS_COLLECTION: str = os.getenv("MONGO_RAG_VARIANTS_COLLECTION", "product_variants")
MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION: str = os.getenv(
    "MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION", "externalproducts"
)
MONGO_RAG_BRANDED_INGREDIENTS_COLLECTION: str = os.getenv(
    "MONGO_RAG_BRANDED_INGREDIENTS_COLLECTION", "ingre_branded_ingredients"
)
MONGO_RAG_INCI_COLLECTION: str = os.getenv("MONGO_RAG_INCI_COLLECTION", "ingre_inci")
# 0 = no cap (use with care on large DBs)
MONGO_RAG_MAX_DOCS_PER_COLLECTION: int = int(os.getenv("MONGO_RAG_MAX_DOCS_PER_COLLECTION", "0"))

# Chatbot RAG retrieval (smaller = faster on large Chroma; MMR needs fetch_k >= k)
RAG_RETRIEVAL_K: int = int(os.getenv("RAG_RETRIEVAL_K", "5"))
RAG_FETCH_K: int = int(os.getenv("RAG_FETCH_K", "12"))

# If true, stream raw LLM token chunks (fastest TTFT). If false (default), batch until
# whitespace or max size so clients that wrongly join chunks with spaces break words less often.
RAG_STREAM_RAW_TOKENS: bool = os.getenv("RAG_STREAM_RAW_TOKENS", "false").lower() in (
    "1",
    "true",
    "yes",
)
RAG_STREAM_BUFFER_MAX: int = int(os.getenv("RAG_STREAM_BUFFER_MAX", "512"))

# Logged-in SkinSage chat: Mongo thread storage
MONGO_CHAT_CONVERSATIONS_COLLECTION: str = os.getenv(
    "MONGO_CHAT_CONVERSATIONS_COLLECTION", "skinsage_chat_conversations"
)
CHAT_HISTORY_MAX_MESSAGES: int = int(os.getenv("CHAT_HISTORY_MAX_MESSAGES", "100"))
CHAT_HISTORY_CONTEXT_TURNS: int = int(os.getenv("CHAT_HISTORY_CONTEXT_TURNS", "5"))

# Consumer web origin for chat answers, e.g. https://www.skinbb.com — no trailing slash.
# When set, RAG prompts ask the model to use full Markdown links [label](base/path).
_SKINBB_PUBLIC_BASE = (os.getenv("SKINBB_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
SKINBB_PUBLIC_BASE_URL: str = _SKINBB_PUBLIC_BASE
