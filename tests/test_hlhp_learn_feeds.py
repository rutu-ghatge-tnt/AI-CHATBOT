"""Learn content feeds: knowledge + blogs ranking assembly."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.hlhp.composition.content_feeds import assemble_ranked_content_feeds
from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.models.engagement import LearnResponse
from app.hlhp.models.v4_api import V4LearnResponse


def _kf(slug: str, *, title: str = "", tags: list[str] | None = None, category: str = "jargons") -> dict:
    return {
        "post_id": slug,
        "slug": slug,
        "category_slug": category,
        "content_type": "Jargon Buster",
        "title": title or slug,
        "excerpt": title or slug,
        "thumbnail_url": None,
        "tag_slugs": tags or [],
    }


def _blog(slug: str, *, title: str = "", tags: list[str] | None = None) -> dict:
    return {
        "post_id": slug,
        "slug": slug,
        "category_slug": "blogs",
        "content_type": "Blog",
        "title": title or slug,
        "excerpt": title or slug,
        "thumbnail_url": None,
        "tag_slugs": tags or [],
    }


def test_assemble_ranked_content_feeds_keeps_arrays_separate():
    knowledge = [
        _kf("spf-jargon", title="What SPF means", tags=["spf"], category="jargons"),
        _kf("acne-story", title="Acne story", tags=["acne"], category="stories"),
    ]
    blogs = [
        _blog("routine-blog", title="Skincare routine for acne", tags=["acne"]),
        _blog("diet-blog", title="Sugar and skin", tags=["diet"]),
    ]
    bands = EnvironmentBands(uvi="very_high", temperature="hot", humidity="high", aqi="moderate")

    with (
        patch(
            "app.hlhp.composition.content_feeds.fetch_knowledge_feed_pool",
            new=AsyncMock(return_value=knowledge),
        ),
        patch(
            "app.hlhp.composition.content_feeds.fetch_blog_feed_pool",
            new=AsyncMock(return_value=blogs),
        ),
    ):
        kf, bl = asyncio.run(
            assemble_ranked_content_feeds(
                concern_id="acne",
                bands=bands,
                when=datetime(2026, 6, 18),
                user_id="u1",
                knowledge_limit=4,
                blog_limit=4,
            )
        )

    assert all(item["content_type"] != "Blog" for item in kf)
    assert all(item["content_type"] == "Blog" for item in bl)
    assert any(item["slug"] == "routine-blog" for item in bl)
    assert len(kf) >= 1


def test_assemble_learn_includes_feeds():
    from app.hlhp.services.engagement_service import assemble_learn

    with (
        patch("app.hlhp.services.engagement_service.load_user_profile", new=AsyncMock(return_value=None)),
        patch(
            "app.hlhp.services.engagement_service.fetch_selected_symptoms",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "app.hlhp.services.engagement_service.assemble_ranked_content_feeds",
            new=AsyncMock(
                return_value=(
                    [_kf("spf-jargon", title="SPF", tags=["spf"])],
                    [_blog("routine-blog", title="Routine", tags=["acne"])],
                )
            ),
        ),
    ):
        result = asyncio.run(assemble_learn("user-1", city="Pune", concern_id="acne"))

    assert isinstance(result, LearnResponse)
    assert len(result.knowledge_feed) == 1
    assert result.knowledge_feed[0]["slug"] == "spf-jargon"
    assert len(result.blogs) == 1
    assert result.blogs[0]["content_type"] == "Blog"


def test_assemble_learn_v4_passes_feeds():
    from app.hlhp.services.v4_api_service import assemble_learn_v4

    base = LearnResponse(
        explainers=[],
        nuggets=[],
        knowledge_feed=[_kf("spf-jargon", title="SPF")],
        blogs=[_blog("routine-blog", title="Routine")],
        concern_id="acne",
        city="Pune",
        symptom_keywords=[],
    )
    with patch(
        "app.hlhp.services.v4_api_service.assemble_learn",
        new=AsyncMock(return_value=base),
    ):
        result = asyncio.run(assemble_learn_v4("user-1", city="Pune", concern_id="acne"))

    assert isinstance(result, V4LearnResponse)
    assert len(result.knowledge_feed) == 1
    assert len(result.blogs) == 1
    assert result.blogs[0]["slug"] == "routine-blog"
