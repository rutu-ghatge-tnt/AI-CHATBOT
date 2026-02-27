"""
Ensemble aggregation: combine classical CV, deep model, and Claude API with configurable weights.
"""

from typing import Any, Dict, Optional
import numpy as np

from .constants import SKIN_PARAMETERS, DEFAULT_ENSEMBLE_WEIGHTS
from .preprocessing import PreprocessingPipeline
from .classical_cv import ClassicalCVAnalyzer
from .claude_api import ClaudeAPIAnalyzer
from .deep_model import run_deep_inference


class EnsembleAnalyzer:
    """
    Run classical CV + deep (if loaded) + Claude (if key set), then weighted average.
    Does not modify the existing FaceAnalyzer or /analyze endpoint.
    """

    def __init__(
        self,
        claude_api_key: Optional[str] = None,
        deep_model_path: Optional[str] = None,
        ensemble_weights: Optional[Dict[str, float]] = None,
    ):
        self.preprocessing = PreprocessingPipeline()
        self.classical = ClassicalCVAnalyzer(use_preprocessing=False)
        self.claude = ClaudeAPIAnalyzer(api_key=claude_api_key)
        self.ensemble_weights = ensemble_weights or dict(DEFAULT_ENSEMBLE_WEIGHTS)
        self._deep_model = None
        if deep_model_path:
            self._load_deep_model(deep_model_path)

    def _load_deep_model(self, path: str) -> None:
        try:
            import torch
            from .deep_model import SkinAnalysisModel
            if SkinAnalysisModel is not None:
                self._deep_model = SkinAnalysisModel()
                self._deep_model.load_state_dict(torch.load(path, map_location="cpu"))
                self._deep_model.eval()
        except Exception:
            self._deep_model = None

    def analyze(
        self,
        image: np.ndarray,
        use_claude: bool = True,
        use_deep: bool = True,
    ) -> Dict[str, Any]:
        """
        Run pipeline: preprocess -> classical + optional deep + optional Claude -> aggregate.
        """
        face_region, mask, quality_info = self.preprocessing.run(image)
        if face_region is None or mask is None:
            return self._empty_result("no_face_detected", quality_info)

        # Classical
        scores_classical = self.classical.analyze(image, face_region=face_region, mask=mask)

        # Deep (stub until checkpoint)
        scores_deep = run_deep_inference(face_region, self._deep_model) if use_deep else None

        # Claude
        scores_claude = self.claude.analyze(face_region) if use_claude else None

        # Weights: normalize so only available branches contribute
        w = self.ensemble_weights
        available = []
        if scores_classical is not None:
            available.append(("classical", w["classical"], scores_classical))
        if scores_deep is not None:
            available.append(("deep", w["deep"], scores_deep))
        if scores_claude is not None and "breakdown" in scores_claude and scores_claude["breakdown"] not in ("claude_unavailable", "claude_error"):
            available.append(("claude", w["claude"], {p: scores_claude[p] for p in SKIN_PARAMETERS}))

        if not available:
            final = dict(scores_classical) if scores_classical else {p: 50.0 for p in SKIN_PARAMETERS}
            confidence = 0.0
            breakdown = {"classical": scores_classical, "deep": scores_deep, "claude": scores_claude}
        else:
            total_w = sum(x[1] for x in available)
            final = {}
            for p in SKIN_PARAMETERS:
                final[p] = sum(s[p] * weight for _, weight, s in available) / total_w
            final = {k: float(np.clip(v, 0, 100)) for k, v in final.items()}
            # Confidence from agreement
            all_scores = [x[2] for x in available]
            variances = [np.var([s[p] for s in all_scores]) for p in SKIN_PARAMETERS]
            confidence = float(np.clip(100 - np.mean(np.sqrt(variances)), 0, 100))
            breakdown = {
                "classical": scores_classical,
                "deep": scores_deep,
                "claude": {p: scores_claude.get(p, 50) for p in SKIN_PARAMETERS} if scores_claude else None,
            }

        age = None
        skin_type = None
        if scores_claude and isinstance(scores_claude.get("age"), (int, float)):
            age = scores_claude["age"]
        if scores_claude and scores_claude.get("skin_type"):
            skin_type = scores_claude["skin_type"]

        return {
            "scores": final,
            "confidence": confidence,
            "breakdown": breakdown,
            "quality": quality_info,
            "estimated_age": age,
            "estimated_skintype": skin_type,
        }

    def _empty_result(self, reason: str, quality_info: dict) -> Dict[str, Any]:
        return {
            "scores": {p: 50.0 for p in SKIN_PARAMETERS},
            "confidence": 0.0,
            "breakdown": {"classical": None, "deep": None, "claude": None},
            "quality": quality_info,
            "estimated_age": None,
            "estimated_skintype": None,
            "error": reason,
        }


class EnsembleWeightLearner:
    """Learn optimal ensemble weights from validation predictions and ground truth."""

    def learn_weights(
        self,
        val_results: Dict[str, Dict[str, np.ndarray]],
        val_labels: Dict[str, np.ndarray],
    ) -> Dict[str, float]:
        """
        val_results: keys 'classical', 'deep', 'claude'; each value is dict of param -> array of scores.
        val_labels: param -> array of ground truth scores.
        Returns optimal weights summing to 1.
        """
        try:
            from scipy.optimize import minimize
        except ImportError:
            return dict(DEFAULT_ENSEMBLE_WEIGHTS)

        def objective(weights: np.ndarray) -> float:
            w_c, w_d, w_cl = weights
            total_mae = 0.0
            n = 0
            for param in SKIN_PARAMETERS:
                y = val_labels.get(param)
                if y is None or len(y) == 0:
                    continue
                preds = []
                if "classical" in val_results and param in val_results["classical"]:
                    preds.append(w_c * val_results["classical"][param])
                if "deep" in val_results and val_results["deep"] and param in val_results["deep"]:
                    preds.append(w_d * val_results["deep"][param])
                if "claude" in val_results and val_results["claude"] and param in val_results["claude"]:
                    preds.append(w_cl * val_results["claude"][param])
                if not preds:
                    continue
                ensemble_pred = sum(preds) / len(preds)
                mae = np.mean(np.abs(ensemble_pred - y))
                total_mae += mae
                n += 1
            return total_mae / n if n else total_mae

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0, 1), (0, 1), (0, 1)]
        x0 = np.array([0.33, 0.33, 0.34])
        result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        return {
            "classical": float(result.x[0]),
            "deep": float(result.x[1]),
            "claude": float(result.x[2]),
        }
