from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class LabelLookerSettings:
    skin_bb_base_url: str
    skin_bb_client_secret: str
    anthropic_api_key: str
    anthropic_model: str
    mongo_uri: str
    mongo_database: str
    server_url: str
    coll_scan_analysis: str
    coll_scan_detail: str
    coll_ingredient: str
    coll_article: str
    coll_category: str
    coll_skin_benefit: str
    coll_naturality: str
    coll_user: str
    coll_user_details: str
    coll_products: str
    coll_branded_ingredient: str
    coll_inci: str
    coll_functional_categories: str
    coll_chemical_classes: str
    coll_product_analysis: str
    aws_bucket_name: str
    aws_region: str
    aws_scan_images_prefix: str
    include_error_stack: bool

    @property
    def skin_bb_base_url_norm(self) -> str:
        return self.skin_bb_base_url.rstrip("/")


@lru_cache
def get_label_looker_settings() -> LabelLookerSettings:
    base = (os.getenv("SKIN_BB_BASE_URL") or os.getenv("CREDITS_API_BASE_URL") or os.getenv("SERVER_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("SKIN_BB_BASE_URL (or CREDITS_API_BASE_URL/SERVER_URL fallback) is required for Label Looker routes")

    mongo_uri = (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI or MONGO_URI is required for Label Looker routes")

    mongo_db = (os.getenv("MONGODB_DATABASE") or os.getenv("DB_NAME") or "skin_bb").strip()
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip()
    if not anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is required for Label Looker routes")

    return LabelLookerSettings(
        skin_bb_base_url=base,
        skin_bb_client_secret=(
            os.getenv("SKIN_BB_CLIENT_SECRET")
            or os.getenv("ACCESS_TOKEN_SECRET")
            or ""
        ).strip(),
        anthropic_api_key=anthropic_key,
        anthropic_model=(os.getenv("ANTHROPIC_MODEL") or os.getenv("CLAUDE_MODEL") or "claude-sonnet-4-20250514").strip(),
        mongo_uri=mongo_uri,
        mongo_database=mongo_db,
        server_url=(os.getenv("SERVER_URL") or "").strip().rstrip("/"),
        coll_scan_analysis=os.getenv("LABEL_LOOKER_SCAN_COLLECTION", "scan_analyses"),
        coll_scan_detail=os.getenv("LABEL_LOOKER_SCAN_DETAIL_COLLECTION", "scan_details"),
        coll_ingredient=os.getenv("LABEL_LOOKER_INGREDIENT_COLLECTION", "ingredients"),
        coll_article=os.getenv("LABEL_LOOKER_ARTICLE_COLLECTION", "articles"),
        coll_category=os.getenv("LABEL_LOOKER_CATEGORY_COLLECTION", "categories"),
        coll_skin_benefit=os.getenv("LABEL_LOOKER_SKIN_BENEFIT_COLLECTION", "skin_benefits"),
        coll_naturality=os.getenv("LABEL_LOOKER_NATURALITY_COLLECTION", "naturalities"),
        coll_user=os.getenv("LABEL_LOOKER_USER_COLLECTION", "users"),
        coll_user_details=os.getenv("LABEL_LOOKER_USER_DETAILS_COLLECTION", "user_details"),
        coll_products=os.getenv("LABEL_LOOKER_PRODUCTS_COLLECTION", "products"),
        coll_branded_ingredient=os.getenv("LABEL_LOOKER_BRANDED_INGREDIENT_COLLECTION", "ingre_branded_ingredients"),
        coll_inci=os.getenv("LABEL_LOOKER_INCI_COLLECTION", "ingre_inci"),
        coll_functional_categories=os.getenv(
            "LABEL_LOOKER_FUNCTIONAL_CATEGORIES_COLLECTION", "ingre_functional_categories"
        ),
        coll_chemical_classes=os.getenv("LABEL_LOOKER_CHEMICAL_CLASSES_COLLECTION", "ingre_chemical_classes"),
        coll_product_analysis=os.getenv("LABEL_LOOKER_PRODUCT_ANALYSIS_COLLECTION", "product_analyses"),
        aws_bucket_name=os.getenv("AWS_BUCKET_NAME", "sbb-dev-media").strip(),
        aws_region=os.getenv("AWS_REGION", "ap-south-1").strip(),
        aws_scan_images_prefix=os.getenv("AWS_SCAN_IMAGES_PREFIX", "product-scan-images/").strip(),
        include_error_stack=os.getenv("LABEL_LOOKER_INCLUDE_STACK", "true").lower() in ("1", "true", "yes"),
    )

