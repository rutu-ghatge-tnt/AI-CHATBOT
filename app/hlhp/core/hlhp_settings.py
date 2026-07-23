"""HLHP settings used by the Python Fun coach (selfies / storage).

Goals, chat, payments, and the realtime hub are owned by SkinBB Node —
do not add hub/Node proxy config here.
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache
def get_hlhp_settings() -> "HlhpSettings":
    return HlhpSettings()


class HlhpSettings:
    """Environment-backed HLHP config for Python-owned surfaces."""

    def __init__(self) -> None:
        self.selfie_storage_dir = os.getenv("HLHP_SELFIE_STORAGE_DIR") or "data/hlhp-selfies"

        # Daily log selfies → s3://skinbb-main/HLHP-LOG/{user}/{date}.jpg (prod path).
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
