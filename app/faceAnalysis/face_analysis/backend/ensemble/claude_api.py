"""
Claude API wrapper for ensemble: image -> scores (0-100) + age + skin_type.
Uses hashed image caching to avoid duplicate API calls.
"""

import base64
import hashlib
import json
from typing import Any, Dict, Optional
import cv2
import numpy as np

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .constants import SKIN_PARAMETERS, SKIN_TYPE_CLASSES


class ClaudeAPIAnalyzer:
    """Call Claude for skin scores; cache results by image hash."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ""
        self.client = anthropic.Anthropic(api_key=self.api_key) if (ANTHROPIC_AVAILABLE and self.api_key) else None
        self.cache: Dict[str, dict] = {}
        self.model = "claude-sonnet-4-20250514"

    def _hash_image(self, image: np.ndarray) -> str:
        return hashlib.md5(image.tobytes()).hexdigest()

    def _encode_image(self, image: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", image)
        return base64.b64encode(buf).decode("utf-8")

    def _parse_response(self, text: str) -> dict:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return self._fallback_scores()
        try:
            data = json.loads(text[start:end])
            return self._normalize_result(data)
        except json.JSONDecodeError:
            return self._fallback_scores()

    def _normalize_result(self, data: dict) -> dict:
        out = {}
        for p in SKIN_PARAMETERS:
            if p in data and isinstance(data[p], (int, float)):
                out[p] = float(data[p])
            elif "analysis" in data and isinstance(data["analysis"], dict) and p in data["analysis"]:
                obj = data["analysis"][p]
                if isinstance(obj, dict) and "score" in obj:
                    out[p] = float(obj["score"])
                else:
                    out[p] = 50.0
            else:
                out[p] = 50.0
        out["age"] = data.get("estimated_age", data.get("age", 30))
        if isinstance(out["age"], str):
            try:
                out["age"] = int("".join(c for c in out["age"] if c.isdigit()) or 30)
            except ValueError:
                out["age"] = 30
        out["skin_type"] = data.get("estimated_skintype", data.get("skin_type", "normal"))
        if out["skin_type"] not in SKIN_TYPE_CLASSES:
            out["skin_type"] = "normal"
        return out

    def _fallback_scores(self) -> dict:
        return {
            **{p: 50.0 for p in SKIN_PARAMETERS},
            "age": 30,
            "skin_type": "normal",
        }

    def analyze(self, image: np.ndarray) -> Dict[str, Any]:
        """Return scores dict (SKIN_PARAMETERS + age + skin_type). Uses cache."""
        if self.client is None:
            return {**self._fallback_scores(), "breakdown": "claude_unavailable"}
        key = self._hash_image(image)
        if key in self.cache:
            return self.cache[key]
        b64 = self._encode_image(image)
        prompt = (
            "Analyze this facial image for skin quality. "
            "Provide scores (0-100) for: "
            + ", ".join(SKIN_PARAMETERS)
            + ". Also estimate age (number) and skin_type (one of: "
            + ", ".join(SKIN_TYPE_CLASSES)
            + "). Return ONLY a JSON object with these keys (scores as numbers)."
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = response.content[0].text
            result = self._parse_response(text)
            result["breakdown"] = "claude"
            self.cache[key] = result
            return result
        except Exception:
            return {**self._fallback_scores(), "breakdown": "claude_error"}
