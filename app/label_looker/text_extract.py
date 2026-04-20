from __future__ import annotations

import json
import re
from typing import Any


def strip_markdown_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def extract_bracket_string_array(model_text: str) -> list[str]:
    """Node scanImageToText: regex \\\\[\\\\s*([\\\\s\\\\S]*?)\\\\s*\\\\] then comma split, strip quotes."""
    m = re.search(r"\[\s*([\s\S]*?)\s*\]", model_text)
    if not m:
        return []
    inner = m.group(1)
    parts = [p.strip().strip('"').strip("'") for p in inner.split(",")]
    return [p for p in parts if p]


def extract_first_json_object(model_text: str) -> dict[str, Any]:
    """Node: strip fences; text.match(/\\\\{[\\\\s\\\\S]*\\\\}/) then JSON.parse."""
    t = strip_markdown_fences(model_text)
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        raise ValueError("No JSON object found in model output")
    return json.loads(m.group(0))
