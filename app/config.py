# app/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

# Load variables from .env file
load_dotenv()

# Claude API settings
from typing import Optional

CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL: str = os.getenv("MODEL_NAME", "claude-3-opus-20240229")

# Path to Chroma vector database
CHROMA_DB_PATH: str = str(Path("chroma_db"))

# Optional: Validate critical env variables early
if not CLAUDE_API_KEY:
    raise ValueError("❌ CLAUDE_API_KEY is not set in the .env file.")
