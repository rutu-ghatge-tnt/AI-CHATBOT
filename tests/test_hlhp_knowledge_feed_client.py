"""Knowledge Feed client normalization."""

from app.hlhp.services.knowledge_feed_client import normalize_knowledge_post


def test_normalize_knowledge_post_from_cms_shape():
    row = normalize_knowledge_post(
        {
            "_id": "abc123",
            "slug": "what-is-retinol",
            "title": "What is retinol?",
            "shortDescription": "A beginner guide to retinoids.",
            "category": {"slug": "jargons", "name": "Jargons"},
            "featuredImage": {"url": "https://cdn.example/retinol.jpg"},
            "tags": [{"slug": "anti-aging", "name": "Anti Aging"}],
        },
        fallback_category="jargons",
    )
    assert row is not None
    assert row["slug"] == "what-is-retinol"
    assert row["category_slug"] == "jargons"
    assert row["content_type"] == "Jargon Buster"
    assert row["thumbnail_url"] == "https://cdn.example/retinol.jpg"
    assert "anti-aging" in row["tag_slugs"]


def test_normalize_strips_html_from_excerpt():
    row = normalize_knowledge_post(
        {
            "slug": "retinol-peel",
            "title": "Retinol Peel",
            "content": "<h3><strong>Understanding Retinol Peels:</strong></h3><p>A retinol peel is gentle.</p>",
            "category": {"slug": "skinvestigators"},
        },
        fallback_category="skinvestigators",
    )
    assert row is not None
    assert "<" not in row["excerpt"]
    assert row["excerpt"].startswith("Understanding Retinol Peels:")
