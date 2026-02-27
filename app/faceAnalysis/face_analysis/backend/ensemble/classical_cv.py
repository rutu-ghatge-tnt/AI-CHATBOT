"""
Classical CV pipeline for skin analysis.

DoG (acne), HSV (dark spots), LBP (pores), Gabor (wrinkles), luminance (dullness), RGB variance (tone).
Scores are heuristic until FeatureScorer is fitted on labeled data.
"""

from typing import Dict, Optional
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

from .constants import SKIN_PARAMETERS
from .preprocessing import PreprocessingPipeline

try:
    from skimage.feature import local_binary_pattern
except ImportError:
    local_binary_pattern = None  # type: ignore


class ClassicalCVAnalyzer:
    """Extract skin features via classical CV; map to 0-100 scores (heuristic or learned)."""

    def __init__(self, use_preprocessing: bool = True):
        self.preprocessing = PreprocessingPipeline() if use_preprocessing else None
        self._lbp_available = local_binary_pattern is not None

    def get_raw_features(
        self, image: np.ndarray, face_region: Optional[np.ndarray] = None, mask: Optional[np.ndarray] = None
    ) -> Optional[Dict[str, dict]]:
        """
        Return raw feature dicts (for training FeatureScorer). Returns None if no face.
        """
        if face_region is None or mask is None:
            if self.preprocessing is None:
                return None
            face_region, mask, _ = self.preprocessing.run(image)
            if face_region is None or mask is None:
                return None
        enhanced = self.preprocessing.sharpen_image(face_region) if self.preprocessing else face_region
        return {
            "acne_dog": self._detect_acne_dog(enhanced, mask),
            "darkspot_hsv": self._detect_darkspots_hsv(enhanced, mask),
            "pores_lbp": self._analyze_pores_lbp(enhanced, mask),
            "wrinkles_gabor": self._detect_wrinkles_gabor(enhanced, mask),
            "dullness_luminance": self._analyze_dullness(enhanced, mask),
            "uneven_tone": self._analyze_tone_variance(enhanced, mask),
        }

    def analyze(
        self, image: np.ndarray, face_region: Optional[np.ndarray] = None, mask: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        Run classical CV and return 0-100 scores for SKIN_PARAMETERS.

        If face_region and mask are None, runs preprocessing internally.
        """
        features = self.get_raw_features(image, face_region, mask)
        if features is None:
            return {p: 50.0 for p in SKIN_PARAMETERS}  # neutral fallback
        return self._features_to_scores(features)

    def _detect_acne_dog(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """Difference of Gaussians for blob-like structures."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(float)
        g1 = gaussian_filter(gray, 1.0)
        g2 = gaussian_filter(gray, 1.6)
        dog = g1 - g2
        dog_masked = np.where(mask > 0, dog, 0)
        region = dog_masked[mask > 0]
        if region.size == 0:
            return {"blob_count": 0, "blob_density": 0.0, "blob_intensity_mean": 0.0}
        thresh = float(np.mean(region) + 1.5 * np.std(region))
        blobs = ((dog > thresh) & (mask > 0)).astype(np.uint8)
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(blobs)
        valid = [s for s in stats[1:] if 4 < s[cv2.CC_STAT_AREA] < 400]
        area = max(np.sum(mask) / 1000, 1e-6)
        return {
            "blob_count": len(valid),
            "blob_density": len(valid) / area,
            "blob_intensity_mean": float(np.mean(dog[blobs > 0])) if np.any(blobs) else 0.0,
        }

    def _detect_darkspots_hsv(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """HSV-based dark region detection."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2]
        region = v[mask > 0]
        if region.size == 0:
            return {"spot_count": 0, "spot_area_ratio": 0.0, "spot_contrast": 0.0}
        v_mean, v_std = float(np.mean(region)), float(np.std(region))
        v_thresh = v_mean - 1.5 * v_std
        dark = ((v < v_thresh) & (mask > 0)).astype(np.uint8)
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dark)
        valid = [s for s in stats[1:] if 20 < s[cv2.CC_STAT_AREA] < 2000]
        total = max(np.sum(mask), 1)
        contrast = v_mean - float(np.mean(v[dark > 0])) if np.any(dark) else 0.0
        return {
            "spot_count": len(valid),
            "spot_area_ratio": float(np.sum(dark)) / total,
            "spot_contrast": contrast,
        }

    def _analyze_pores_lbp(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """LBP texture (pore-like roughness)."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if not self._lbp_available:
            region = gray[mask > 0]
            return {
                "lbp_variance": float(np.var(region)),
                "high_freq_ratio": 0.1,
                "texture_uniformity": 4.0,
            }
        radius = 1
        n_points = 8 * radius
        lbp = local_binary_pattern(gray, n_points, radius, method="uniform")
        region = lbp[mask > 0]
        hist, _ = np.histogram(region, bins=256, range=(0, 256))
        hist = hist.astype(float) / (hist.sum() + 1e-10)
        high_freq = float(np.sum(hist[200:]))
        entropy = -float(np.sum(hist * np.log(hist + 1e-10)))
        return {
            "lbp_variance": float(np.var(region)),
            "high_freq_ratio": high_freq,
            "texture_uniformity": entropy,
        }

    def _detect_wrinkles_gabor(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """Gabor line strength (wrinkle-like)."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        responses = []
        for theta in [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]:
            kernel = cv2.getGaborKernel(
                (21, 21), sigma=5.0, theta=theta, lambd=10.0, gamma=0.5
            )
            resp = cv2.filter2D(gray, cv2.CV_32F, kernel)
            responses.append(resp)
        gabor_max = np.max(responses, axis=0)
        region = gabor_max[mask > 0]
        if region.size == 0:
            return {"line_density": 0.0, "line_strength": 0.0, "line_orientation_variance": 0.0}
        thresh = float(np.mean(region) + 2.0 * np.std(region))
        lines = (gabor_max > thresh) & (mask > 0)
        total = max(np.sum(mask), 1)
        strength = float(np.mean(gabor_max[lines])) if np.any(lines) else 0.0
        orient_var = float(np.var([np.sum(gr[lines]) for gr in responses]))
        return {
            "line_density": float(np.sum(lines)) / total,
            "line_strength": strength,
            "line_orientation_variance": orient_var,
        }

    def _analyze_dullness(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """Luminance (LAB L) for dullness."""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_ch = lab[:, :, 0]
        region = l_ch[mask > 0]
        if region.size == 0:
            return {"luminance_mean": 128.0, "luminance_std": 0.0, "dullness_raw": 50.0}
        l_mean = float(np.mean(region))
        dullness = 100.0 - (l_mean / 255.0 * 100.0)
        return {
            "luminance_mean": l_mean,
            "luminance_std": float(np.std(region)),
            "dullness_raw": float(np.clip(dullness, 0, 100)),
        }

    def _analyze_tone_variance(self, image: np.ndarray, mask: np.ndarray) -> dict:
        """RGB variance for uneven tone."""
        r = image[:, :, 2][mask > 0]
        g = image[:, :, 1][mask > 0]
        b = image[:, :, 0][mask > 0]
        if r.size == 0:
            return {"rgb_variance": 0.0, "r_std": 0.0, "g_std": 0.0, "b_std": 0.0, "uneven_raw": 50.0}
        rgb_var = float(
            np.sqrt(np.var(r) ** 2 + np.var(g) ** 2 + np.var(b) ** 2)
        )
        uneven = (rgb_var / 255.0) * 100.0
        return {
            "rgb_variance": rgb_var,
            "r_std": float(np.std(r)),
            "g_std": float(np.std(g)),
            "b_std": float(np.std(b)),
            "uneven_raw": float(np.clip(uneven, 0, 100)),
        }

    def _features_to_scores(self, features: dict) -> Dict[str, float]:
        """Map raw features to 0-100 scores. Heuristic until FeatureScorer is fitted."""
        scores = {
            "acne": self._map_acne(features["acne_dog"]),
            "dark_spot": self._map_darkspot(features["darkspot_hsv"]),
            "dark_circle": self._map_darkspot(features["darkspot_hsv"]),  # reuse; can specialize later
            "pores": self._map_pores(features["pores_lbp"]),
            "wrinkle": self._map_wrinkle(features["wrinkles_gabor"]),
            "dullness": features["dullness_luminance"]["dullness_raw"],
            "uneven_skintone": features["uneven_tone"]["uneven_raw"],
            "pigmentation": features["darkspot_hsv"]["spot_area_ratio"] * 100,
            "overall_skin_health": 0.0,  # computed below
        }
        scores["overall_skin_health"] = float(
            np.clip(np.mean([scores[k] for k in SKIN_PARAMETERS if k != "overall_skin_health"]), 0, 100)
        )
        return {k: float(np.clip(v, 0, 100)) for k, v in scores.items()}

    @staticmethod
    def _map_acne(f: dict) -> float:
        d = f.get("blob_density", 0) or 0
        return float(100 / (1 + np.exp(-0.5 * (d - 5))))

    @staticmethod
    def _map_darkspot(f: dict) -> float:
        ratio = f.get("spot_area_ratio", 0) or 0
        return float(np.clip(ratio * 150, 0, 100))

    @staticmethod
    def _map_pores(f: dict) -> float:
        hf = f.get("high_freq_ratio", 0) or 0
        return float(np.clip(hf * 200, 0, 100))

    @staticmethod
    def _map_wrinkle(f: dict) -> float:
        density = f.get("line_density", 0) or 0
        return float(np.clip(density * 500, 0, 100))
