"""Blog feed client normalization + unwrap."""

from app.hlhp.services.blog_feed_client import (
    _unwrap_blogs,
    clear_blog_feed_cache,
    normalize_blog_post,
)


def test_normalize_blog_from_api_shape():
    row = normalize_blog_post(
        {
            "_id": "69cbbdadcc5524a6cf84f972",
            "slug": "simple-effective-skincare-routine",
            "title": "How to Build a Simple, Effective Skincare Routine",
            "description": "A calm morning and night routine for Indian skin.",
            "status": "published",
            "isDeleted": False,
            "categories": ["Skincare Basics"],
            "tag": ["Acne", "Routine"],
            "featuredImage": "https://cdn.example/routine.jpg",
            "publishedDate": "2026-03-30T14:27:00.000Z",
        }
    )
    assert row is not None
    assert row["slug"] == "simple-effective-skincare-routine"
    assert row["content_type"] == "Blog"
    assert row["category_slug"] == "skincare-basics"
    assert row["thumbnail_url"] == "https://cdn.example/routine.jpg"
    assert "acne" in row["tag_slugs"]
    assert "routine" in row["tag_slugs"]
    assert "calm morning" in row["excerpt"].lower()


def test_normalize_blog_strips_html_content_fallback():
    row = normalize_blog_post(
        {
            "slug": "spf-basics",
            "title": "SPF Basics",
            "content": "<p>Wear <strong>broad-spectrum SPF</strong> every day.</p>",
            "status": "published",
            "tag": [{"slug": "spf", "name": "SPF"}],
        }
    )
    assert row is not None
    assert "<" not in row["excerpt"]
    assert "broad-spectrum SPF" in row["excerpt"]
    assert "spf" in row["tag_slugs"]


def test_normalize_skips_non_published():
    assert normalize_blog_post({"slug": "x", "title": "X", "status": "draft"}) is None
    assert normalize_blog_post({"slug": "x", "title": "X", "status": "published", "isDeleted": True}) is None


def test_unwrap_blogs_api_response():
    blogs = _unwrap_blogs(
        {
            "statusCode": 200,
            "data": {
                "blogs": [{"slug": "a", "title": "A"}],
                "pagination": {"currentPage": 1},
            },
        }
    )
    assert len(blogs) == 1
    assert blogs[0]["slug"] == "a"


def test_clear_blog_feed_cache():
    clear_blog_feed_cache()
