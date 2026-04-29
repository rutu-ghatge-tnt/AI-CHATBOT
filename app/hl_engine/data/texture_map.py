from app.hl_engine.models.profile import SkinType

TEXTURE_MAP = {
    "sunscreen": {
        SkinType.OILY: {"prefix": "Oil-free mattifying", "suffix": "avoid heavy cream textures"},
        SkinType.DRY: {"prefix": "Hydrating", "suffix": "with extra barrier support"},
        SkinType.COMBINATION: {"prefix": "Lightweight fluid", "suffix": "balance T-zone and cheeks"},
        SkinType.NORMAL: {"prefix": "", "suffix": ""},
        SkinType.SENSITIVE: {"prefix": "Mineral", "suffix": "fragrance-free and low-irritant"},
    },
    "serum": {
        SkinType.OILY: {"prefix": "Water-based", "suffix": "non-comedogenic only"},
        SkinType.DRY: {"prefix": "Nourishing", "suffix": "pair with occlusive layer"},
        SkinType.COMBINATION: {"prefix": "Lightweight", "suffix": ""},
        SkinType.NORMAL: {"prefix": "", "suffix": ""},
        SkinType.SENSITIVE: {"prefix": "Fragrance-free", "suffix": "minimal actives"},
    },
    "moisturizer": {
        SkinType.OILY: {"prefix": "Oil-free gel", "suffix": "skip dense creams"},
        SkinType.DRY: {"prefix": "Rich cream", "suffix": "barrier-first finish"},
        SkinType.COMBINATION: {"prefix": "Light lotion", "suffix": "customize by zone"},
        SkinType.NORMAL: {"prefix": "", "suffix": ""},
        SkinType.SENSITIVE: {"prefix": "Barrier cream", "suffix": "ceramide-led and fragrance-free"},
    },
    "cleanser": {
        SkinType.OILY: {"prefix": "Gentle gel", "suffix": ""},
        SkinType.DRY: {"prefix": "Cream", "suffix": "avoid stripping foam"},
        SkinType.COMBINATION: {"prefix": "Low-pH gel", "suffix": ""},
        SkinType.NORMAL: {"prefix": "Gentle", "suffix": ""},
        SkinType.SENSITIVE: {"prefix": "Ultra-gentle", "suffix": "soap-free"},
    },
}


def get_textured_product(product_category: str, skin_type: SkinType, generic_action: str) -> str:
    texture = TEXTURE_MAP.get(product_category, {}).get(skin_type)
    if not texture:
        return generic_action

    prefix = texture.get("prefix", "").strip()
    suffix = texture.get("suffix", "").strip()
    updated = generic_action

    if prefix:
        updated = f"{prefix} {generic_action.lower()}"
    if suffix:
        updated = f"{updated} - {suffix}"
    return updated
