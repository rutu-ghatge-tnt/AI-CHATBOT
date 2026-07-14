"""HLHP integration settings (hub, Node payments, storage)."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache
def get_hlhp_settings() -> "HlhpSettings":
    return HlhpSettings()


class HlhpSettings:
    """Environment-backed HLHP config."""

    def __init__(self) -> None:
        self.hub_url = (os.getenv("HLHP_HUB_URL") or "").rstrip("/")
        self.service_api_key = os.getenv("HLHP_SERVICE_API_KEY") or ""
        self.node_api_url = (
            os.getenv("HLHP_NODE_API_URL") or os.getenv("SKIN_BB_BASE_URL") or ""
        ).rstrip("/")
        self.selfie_storage_dir = os.getenv("HLHP_SELFIE_STORAGE_DIR") or "data/hlhp-selfies"
        self.default_plus_fee_inr = int(os.getenv("HLHP_PLUS_DEFAULT_FEE_INR") or "1499")

        # Daily log selfies → s3://skinbb-main/HLHP-LOG/{user}/{date}.jpg (prod path).
        # Override with HLHP_SELFIE_S3_BUCKET if needed. Local disk cache still
        # backs previews when GetObject / console credentials lack read access.
        self.selfie_s3_bucket = (
            os.getenv("HLHP_SELFIE_S3_BUCKET")
            or os.getenv("AWS_S3_BUCKET_PLATFORM_LOGOS")
            or "skinbb-main"
        ).strip()
        self.selfie_s3_prefix = (
            (os.getenv("HLHP_SELFIE_S3_PREFIX") or "HLHP-LOG").strip().strip("/")
        )
        self.selfie_s3_region = (
            os.getenv("HLHP_SELFIE_S3_REGION")
            or os.getenv("AWS_S3_REGION")
            or os.getenv("AWS_REGION")
            or "ap-south-1"
        ).strip()
        self.selfie_max_bytes = int(
            os.getenv("HLHP_SELFIE_MAX_BYTES") or str(5 * 1024 * 1024)
        )

    @property
    def hub_configured(self) -> bool:
        return bool(self.hub_url)

    @property
    def node_configured(self) -> bool:
        return bool(self.node_api_url)

    def hub_events_url(self) -> str:
        return f"{self.hub_url}/events"

    def hub_state_url(self) -> str:
        return f"{self.hub_url}/state"

    def node_hlhp_payments_base(self) -> str:
        return f"{self.node_api_url}/api/v1/hlhp/payments"
