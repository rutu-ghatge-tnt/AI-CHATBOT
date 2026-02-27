"""
Ensemble Skin Analysis — shared constants.
Uses the same 9 parameters as the existing Face Analysis API for compatibility.
"""

from typing import List

# Same 9 parameters as core.config.SKIN_ANALYSIS_PARAMETERS (single source when imported from config in API)
SKIN_PARAMETERS: List[str] = [
    "acne",
    "dark_spot",
    "dark_circle",
    "wrinkle",
    "uneven_skintone",
    "pores",
    "pigmentation",
    "dullness",
    "overall_skin_health",
]

SKIN_TYPE_CLASSES: List[str] = [
    "normal",
    "dry",
    "oily",
    "combination",
    "sensitive",
]

# Default ensemble weights (to be learned from validation data when available)
DEFAULT_ENSEMBLE_WEIGHTS = {
    "classical": 0.20,
    "deep": 0.45,
    "claude": 0.35,
}
