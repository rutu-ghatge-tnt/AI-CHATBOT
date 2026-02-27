"""
Ensemble Skin Analysis System.

Combines:
- Preprocessing (face detection, alignment, quality) — extend with labelling/segmentation when data is ready
- Classical CV pipeline (DoG, HSV, LBP, Gabor, luminance, tone)
- Deep learning model (stub until trained on labeled data)
- Claude API (cached wrapper)
- Weighted ensemble aggregation

Current API (/analyze) is unchanged. Use /analyze/ensemble when this pipeline is enabled.
"""

from .constants import SKIN_PARAMETERS, SKIN_TYPE_CLASSES, DEFAULT_ENSEMBLE_WEIGHTS
from .preprocessing import PreprocessingPipeline
from .classical_cv import ClassicalCVAnalyzer
from .aggregation import EnsembleAnalyzer

__all__ = [
    "SKIN_PARAMETERS",
    "SKIN_TYPE_CLASSES",
    "DEFAULT_ENSEMBLE_WEIGHTS",
    "PreprocessingPipeline",
    "ClassicalCVAnalyzer",
    "EnsembleAnalyzer",
]
