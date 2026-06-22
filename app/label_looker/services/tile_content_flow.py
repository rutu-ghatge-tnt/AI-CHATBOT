from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.label_looker.generation.tile_content import (
    TileGenerationError,
    build_fallback_tiles,
    generate_tile_content,
)

logger = logging.getLogger(__name__)


async def generate_tiles_with_fallback(
    *,
    inputs: dict[str, Any],
    client: AsyncAnthropic,
    model: str,
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta: dict[str, Any] = {"source": "claude", "model": model}
    try:
        tiles = await generate_tile_content(inputs=inputs, client=client, model=model)
        return tiles, meta
    except TileGenerationError as exc:
        logger.warning("%s tile generation failed, using template fallback: %s", context, exc)
        tiles = build_fallback_tiles(inputs=inputs)
        meta = {"source": "fallback", "model": model, "reason": "tile_generation_error"}
        return tiles, meta
    except Exception:
        logger.exception("%s tile generation unexpected error; using template fallback", context)
        tiles = build_fallback_tiles(inputs=inputs)
        meta = {"source": "fallback", "model": model, "reason": "unexpected_error"}
        return tiles, meta
