"""
Deep learning skin analysis model (EfficientNet backbone + regression/classification heads).

Define architecture only; weights are loaded when available (trained when labeled data exists).
Inference stub returns neutral scores until a trained checkpoint is provided.
"""

from typing import Dict, Optional, Tuple
import numpy as np

from .constants import SKIN_PARAMETERS, SKIN_TYPE_CLASSES

try:
    import torch
    import torch.nn as nn
    from torchvision import models
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None
    models = None


if TORCH_AVAILABLE:

    class SkinAnalysisModel(nn.Module):
        """EfficientNet-B2 backbone + shared FC + per-parameter score heads + age + skin type."""

        def __init__(self, num_score_params: int = 9):
            super().__init__()
            self.backbone = models.efficientnet_b2(weights=models.EfficientNet_B2_Weights.IMAGENET1K_V1)
            feature_dim = 1408
            self.backbone.classifier = nn.Identity()
            self.shared_fc = nn.Sequential(
                nn.Linear(feature_dim, 512),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(512, 256),
                nn.ReLU(),
                nn.Dropout(0.3),
            )
            self.score_heads = nn.ModuleDict({
                param: nn.Sequential(
                    nn.Linear(256, 64),
                    nn.ReLU(),
                    nn.Linear(64, 1),
                    nn.Sigmoid(),
                )
                for param in SKIN_PARAMETERS
            })
            self.age_head = nn.Sequential(
                nn.Linear(256, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )
            self.skin_type_head = nn.Sequential(
                nn.Linear(256, 64),
                nn.ReLU(),
                nn.Linear(64, len(SKIN_TYPE_CLASSES)),
            )

        def forward(self, x: "torch.Tensor") -> Tuple[Dict[str, "torch.Tensor"], "torch.Tensor", "torch.Tensor"]:
            features = self.backbone(x)
            shared = self.shared_fc(features)
            scores = {
                param: head(shared).squeeze(-1) * 100
                for param, head in self.score_heads.items()
            }
            age = self.age_head(shared).squeeze(-1)
            skin_type_logits = self.skin_type_head(shared)
            return scores, age, skin_type_logits

else:
    SkinAnalysisModel = None  # type: ignore


def run_deep_inference(
    image: np.ndarray,
    model: Optional[object] = None,
    device: Optional[str] = None,
) -> Dict[str, float]:
    """
    Run deep model inference. Returns neutral scores if model is None or not loaded.
    When a trained checkpoint is available, load it and pass the model here.
    """
    if not TORCH_AVAILABLE or model is None:
        return {p: 50.0 for p in SKIN_PARAMETERS}

    import torch
    from torchvision import transforms
    from PIL import Image

    model.eval()
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((384, 384)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])
    if image.ndim == 2:
        image = np.stack([image] * 3, axis=-1)
    if image.shape[2] == 4:
        image = image[:, :, :3]
    tensor = transform(image).unsqueeze(0).to(device)
    with torch.no_grad():
        scores, _age, _skin_type = model(tensor)
    return {
        param: float(scores[param].cpu().item())
        for param in SKIN_PARAMETERS
    }
