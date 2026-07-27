"""Shared ranked Knowledge Feed + Blog assembly for Learn / Explore."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.hlhp.composition.knowledge_feed_rank import rank_knowledge_feed_posts
from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.models.profile import UserProfile
from app.hlhp.services.blog_feed_client import fetch_blog_feed_pool
from app.hlhp.services.knowledge_feed_client import fetch_knowledge_feed_pool


async def assemble_ranked_content_feeds(
    *,
    concern_id: str | None,
    bands: EnvironmentBands | None,
    when: datetime,
    user_id: str | None = None,
    profile: UserProfile | None = None,
    knowledge_limit: int = 4,
    blog_limit: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    knowledge_pool, blog_pool = await asyncio.gather(
        fetch_knowledge_feed_pool(),
        fetch_blog_feed_pool(),
    )
    knowledge_feed = rank_knowledge_feed_posts(
        knowledge_pool,
        concern_id=concern_id,
        bands=bands,
        when=when,
        user_id=user_id,
        profile=profile,
        limit=knowledge_limit,
    )
    blogs = rank_knowledge_feed_posts(
        blog_pool,
        concern_id=concern_id,
        bands=bands,
        when=when,
        user_id=user_id,
        profile=profile,
        limit=blog_limit,
    )
    return knowledge_feed, blogs
