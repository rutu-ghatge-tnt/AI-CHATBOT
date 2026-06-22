"""Knowledge Feed ranking for HLHP Explore."""

from datetime import datetime

from app.hlhp.composition.knowledge_feed_rank import rank_knowledge_feed_posts
from app.hlhp.core.bands import EnvironmentBands


def _post(
    slug: str,
    *,
    category: str = "jargons",
    title: str = "",
    excerpt: str = "",
    tags: list[str] | None = None,
) -> dict:
    return {
        "post_id": slug,
        "slug": slug,
        "category_slug": category,
        "content_type": "Jargon Buster",
        "title": title or slug.replace("-", " ").title(),
        "excerpt": excerpt,
        "thumbnail_url": None,
        "tag_slugs": tags or [],
    }


def test_rank_prefers_concern_and_uv_match():
    posts = [
        _post("generic-moisturizer", excerpt="How to pick a daily moisturizer."),
        _post(
            "spf-jargon",
            title="What broad-spectrum SPF really means",
            excerpt="UVA and UVB protection for Indian skin in summer.",
            tags=["spf"],
        ),
        _post(
            "acne-story",
            category="stories",
            excerpt="My breakout journey after humid Mumbai summers.",
            tags=["acne"],
        ),
    ]
    bands = EnvironmentBands(uvi="very_high", temperature="hot", humidity="high", aqi="moderate")
    ranked = rank_knowledge_feed_posts(
        posts,
        concern_id="acne",
        bands=bands,
        when=datetime(2026, 6, 18),
        user_id="u1",
        limit=3,
    )
    slugs = [row["slug"] for row in ranked]
    assert "acne-story" in slugs
    assert slugs[0] in {"acne-story", "spf-jargon"}


def test_rank_diversifies_categories():
    posts = [
        _post("jargon-1", category="jargons", excerpt="pollution particulate oxidative stress"),
        _post("story-1", category="stories", excerpt="pollution and dull skin in Delhi"),
        _post("investigator-1", category="skinvestigators", excerpt="we tested sunscreen under UV"),
    ]
    bands = EnvironmentBands(uvi="high", temperature="warm", humidity="comfortable", aqi="poor")
    ranked = rank_knowledge_feed_posts(
        posts,
        concern_id="dullness",
        bands=bands,
        when=datetime(2026, 6, 18),
        limit=3,
    )
    categories = {row["category_slug"] for row in ranked}
    assert len(ranked) == 3
    assert "skinvestigators" in categories
    assert "stories" in categories
    assert "jargons" in categories


def test_dullness_profile_does_not_match_melasma_title():
    from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile

    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.DULLNESS, SkinConcern.DEHYDRATION, SkinConcern.PORES],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    posts = [
        _post(
            "retinol-melasma",
            category="skinvestigators",
            title="Retinol Peel for Melasma",
            excerpt="Understanding melasma patches and retinol peels.",
        ),
        _post(
            "dull-skin-story",
            category="stories",
            excerpt="How dull dehydrated skin found its glow again with hydration.",
        ),
    ]
    ranked = rank_knowledge_feed_posts(
        posts,
        concern_id="dullness",
        bands=None,
        when=datetime(2026, 6, 18),
        profile=profile,
        limit=2,
    )
    for row in ranked:
        reason = (row.get("match_reason") or "").lower()
        assert "melasma" not in reason
        assert "pigmentation" not in reason


def test_rank_includes_match_reason():
    posts = [
        _post(
            "pollution-jargon",
            excerpt="AQI spikes and oxidative load on skin barriers.",
            tags=["pollution"],
        )
    ]
    bands = EnvironmentBands(uvi="moderate", temperature="comfortable", humidity="comfortable", aqi="poor")
    ranked = rank_knowledge_feed_posts(
        posts,
        concern_id="dullness",
        bands=bands,
        when=datetime(2026, 6, 18),
        limit=1,
    )
    assert ranked[0]["match_reason"]
