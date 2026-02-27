"""
Preprocessing pipeline for ensemble skin analysis.

- Face detection, alignment, quality checks.
- When data is available: add labelling hooks, segmentation masks, and dataset builders here.
"""

from typing import Optional, Tuple
import cv2
import numpy as np


class PreprocessingPipeline:
    """
    Face detection, alignment, and quality assessment.
    Extend with labelling/segmentation when labeled data is available.
    """

    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def run(
        self, image: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], dict]:
        """
        Run full preprocessing: detect face, crop/align, build mask, quality metrics.

        Returns:
            face_region: Cropped/aligned face image, or None if no face.
            mask: Binary mask for skin region (same size as face_region), or None.
            quality_info: Dict with keys like 'blur_score', 'brightness', 'face_detected'.
        """
        face_region, mask = self.detect_and_mask_face(image)
        if face_region is None:
            return None, None, {"face_detected": False}

        quality_info = self.assess_quality(face_region, mask)
        quality_info["face_detected"] = True
        return face_region, mask, quality_info

    def detect_and_mask_face(
        self, image: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Detect largest face, return cropped region and a binary mask of the face area.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        if len(faces) == 0:
            return None, None

        x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
        # Slight padding
        pad = int(0.1 * max(w, h))
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(image.shape[0], y + h + pad)
        x2 = min(image.shape[1], x + w + pad)
        face_region = image[y1:y2, x1:x2]

        # Ellipse mask roughly for face
        mask = np.zeros((face_region.shape[0], face_region.shape[1]), dtype=np.float32)
        cx, cy = face_region.shape[1] // 2, face_region.shape[0] // 2
        axes = (int(face_region.shape[1] * 0.48), int(face_region.shape[0] * 0.55))
        cv2.ellipse(mask, (cx, cy), axes, 0, 0, 360, 1.0, -1)
        return face_region, mask

    def assess_quality(
        self, face_region: np.ndarray, mask: Optional[np.ndarray]
    ) -> dict:
        """Blur and brightness metrics. Used to reject low-quality inputs or weight results."""
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        region = gray[mask > 0] if mask is not None else gray.ravel()
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(region))
        return {
            "blur_score": laplacian_var,
            "brightness": brightness,
            "reject_for_blur": laplacian_var < 50,
        }

    def sharpen_image(self, image: np.ndarray) -> np.ndarray:
        """Light sharpening for classical CV pipeline."""
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]], dtype=np.float32)
        return cv2.filter2D(image, -1, kernel)
