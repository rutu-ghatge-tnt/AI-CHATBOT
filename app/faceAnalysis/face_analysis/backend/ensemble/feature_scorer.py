"""
Feature-to-score mapping learned from labeled data.

When labels are available: fit(feature_vectors, labels) then use predict(features).
Until then, ClassicalCVAnalyzer uses heuristic _features_to_scores internally.
"""

from typing import Dict, List, Optional
import numpy as np

from .constants import SKIN_PARAMETERS

try:
    from sklearn.ensemble import GradientBoostingRegressor
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    GradientBoostingRegressor = None  # type: ignore


class FeatureScorer:
    """
    Learn optimal feature -> score mappings from labeled data.
    Call fit() when you have (feature dicts, ground-truth scores); then predict() for new features.
    """

    def __init__(self):
        self.models: Dict[str, Optional[object]] = {}
        self._feature_order: Optional[List[str]] = []
        if SKLEARN_AVAILABLE:
            for param in SKIN_PARAMETERS:
                self.models[param] = GradientBoostingRegressor(
                    n_estimators=100, max_depth=3, learning_rate=0.1
                )
        else:
            for param in SKIN_PARAMETERS:
                self.models[param] = None
        self._fitted = False

    def _features_to_array(self, feature_vectors: List[dict]) -> np.ndarray:
        """Flatten list of feature dicts (from classical CV) into a matrix."""
        if not feature_vectors:
            return np.zeros((0, 0))
        # Build consistent key order from first dict (nested keys flattened)
        keys = []
        for k, v in feature_vectors[0].items():
            if isinstance(v, dict):
                for k2 in sorted(v.keys()):
                    keys.append((k, k2))
            else:
                keys.append((k, None))
        rows = []
        for fv in feature_vectors:
            row = []
            for k, k2 in keys:
                if k2 is None:
                    row.append(float(fv.get(k, 0)))
                else:
                    row.append(float(fv[k].get(k2, 0)))
            rows.append(row)
        if not self._feature_order:
            self._feature_order = keys
        return np.array(rows, dtype=np.float64)

    def fit(
        self,
        feature_vectors: List[dict],
        labels: List[Dict[str, float]],
    ) -> None:
        """
        Train scoring models per parameter.

        Args:
            feature_vectors: List of feature dicts from ClassicalCVAnalyzer (raw features before _features_to_scores).
            labels: List of dicts with keys in SKIN_PARAMETERS and values 0-100.
        """
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("sklearn is required for FeatureScorer.fit()")
        X = self._features_to_array(feature_vectors)
        for param in SKIN_PARAMETERS:
            y = np.array([lab.get(param, 50.0) for lab in labels], dtype=np.float64)
            self.models[param].fit(X, y)
        self._fitted = True

    def predict(self, features: dict) -> Dict[str, float]:
        """Convert one feature dict to scores. Uses learned models if fitted, else fallback 50."""
        if not self._fitted or not SKLEARN_AVAILABLE:
            return {p: 50.0 for p in SKIN_PARAMETERS}
        X = self._features_to_array([features])
        if X.size == 0:
            return {p: 50.0 for p in SKIN_PARAMETERS}
        X = X.reshape(1, -1)
        scores = {}
        for param in SKIN_PARAMETERS:
            val = self.models[param].predict(X)[0]
            scores[param] = float(np.clip(val, 0, 100))
        return scores
