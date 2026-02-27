"""
Training entrypoints for when labeled data is available.

- fit_feature_scorer: classical CV feature vectors + labels -> learned score mapping.
- train_deep_model: image paths + labels -> PyTorch checkpoint (stub; implement DataLoader and loop).
- learn_ensemble_weights: validation predictions + labels -> optimal weights.

Data format (for labelling/preprocessing):
  - Images: same as API input (face crop or full image; preprocessing will detect face).
  - Labels: list of dicts with keys SKIN_PARAMETERS (0-100), optional 'age', 'skin_type'.
  - Segmentation: when ready, add mask per image and use in preprocessing pipeline.
"""

from typing import Dict, List, Optional
import numpy as np

from .constants import SKIN_PARAMETERS
from .classical_cv import ClassicalCVAnalyzer
from .feature_scorer import FeatureScorer
from .aggregation import EnsembleWeightLearner

# Optional: from .deep_model import SkinAnalysisModel, SkinAnalysisTrainer


def fit_feature_scorer(
    feature_vectors: List[dict],
    labels: List[Dict[str, float]],
) -> FeatureScorer:
    """Train FeatureScorer on classical CV features + ground truth scores."""
    scorer = FeatureScorer()
    scorer.fit(feature_vectors, labels)
    return scorer


def collect_classical_features(
    image_paths: List[str],
    analyzer: Optional[ClassicalCVAnalyzer] = None,
) -> List[dict]:
    """
    Run classical CV and return raw feature dicts (before scores) for each image.
    Use these + labels to call fit_feature_scorer.
    """
    import cv2
    if analyzer is None:
        analyzer = ClassicalCVAnalyzer()
    features_list = []
    for path in image_paths:
        img = cv2.imread(path)
        if img is None:
            continue
        raw = analyzer.get_raw_features(img)
        if raw is not None:
            features_list.append(raw)
    return features_list


def learn_ensemble_weights(
    val_results: Dict[str, Dict[str, np.ndarray]],
    val_labels: Dict[str, np.ndarray],
) -> Dict[str, float]:
    """Return optimal ensemble weights from validation predictions and ground truth."""
    learner = EnsembleWeightLearner()
    return learner.learn_weights(val_results, val_labels)
