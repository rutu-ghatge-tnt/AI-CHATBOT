from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.label_looker.engines.base_formula.matrices import load_config
from app.label_looker.engines.base_formula.types import BaseFormulaRecord

_FRAGRANCE_MARKERS = {"parfum", "fragrance", "perfume", "aroma", "essential oil"}
_ALCOHOL_HIGH_MARKERS = {"alcohol denat", "ethanol", "sd alcohol", "isopropyl alcohol"}
_SILICONE_MARKERS = ("dimethicone", "cyclo", "siloxane")
_LIPID_MARKERS = ("oil", "butter", "wax")
_WATER_MARKERS = {"aqua", "water", "eau"}
_POLYOL_MARKERS = {"glycerin", "propylene glycol", "butylene glycol", "pentylene glycol"}


def derive_base_formula_record(
    *,
    inci_list: list[dict[str, Any]] | None = None,
    brand_declared: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
    tile_product: dict[str, Any] | None = None,
) -> BaseFormulaRecord:
    """
    Spec-native signature: inci_list + brand_declared.
    Backward-compatible input is also supported via product + tile_product.
    """
    derived_inci_list = inci_list
    derived_brand_declared = dict(brand_declared or {})
    if derived_inci_list is None:
        derived_inci_list = list(((tile_product or {}).get("ingredients") or []))
    if not derived_brand_declared:
        p = product or {}
        p_name = _to_text(p.get("productName") or p.get("name"))
        p_category = _to_text(p.get("productType") or p.get("category"))
        derived_brand_declared = {
            "texture": _derive_texture(p_name, p_category),
            "is_oilfree": ("oil-free" in p_name or "oil free" in p_name),
            "finish": _derive_finish(p_name, p_category),
        }

    inci_names = _inci_list(derived_inci_list if isinstance(derived_inci_list, list) else [])
    top5 = inci_names[:5]
    top7 = inci_names[:7]
    texture = str(derived_brand_declared.get("texture") or "lotion")
    name_text = _to_text((product or {}).get("productName") or (product or {}).get("name"))
    category_text = _to_text((product or {}).get("productType") or (product or {}).get("category"))
    hydration_state = _derive_hydration_state(inci_names)
    continuous_phase = _derive_continuous_phase(top7)
    fragrance_level = _derive_fragrance_level(inci_names)
    alcohol_level = _derive_alcohol_level(top5, inci_names)
    finish = derived_brand_declared.get("finish")
    if finish is None:
        finish = _derive_finish(name_text, category_text)
    comedogenic_risk, comedogenic_drivers = _derive_comedogenic(inci_names)
    fungal_acne_safe, fungal_acne_triggers = _derive_fungal_acne(inci_names)

    return BaseFormulaRecord(
        texture=texture,
        is_oilfree=bool(derived_brand_declared.get("is_oilfree", False)),
        finish=finish,
        hydration_state=hydration_state,
        continuous_phase=continuous_phase,
        fragrance_level=fragrance_level,
        alcohol_level=alcohol_level,
        comedogenic_risk=comedogenic_risk,
        comedogenic_drivers=comedogenic_drivers,
        fungal_acne_safe=fungal_acne_safe,
        fungal_acne_triggers=fungal_acne_triggers,
        derivation_version="ll2.0.v1",
        last_validated_at=datetime.now(timezone.utc).isoformat(),
    )


def _to_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _inci_list(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _to_text(row.get("inci_name") or row.get("ingredient_name") or row.get("name"))
        if name:
            out.append(name)
    return out


def _derive_hydration_state(inci_names: list[str]) -> str:
    top3 = inci_names[:3]
    if any(x in _WATER_MARKERS for x in top3):
        return "hydrous"
    if top3 and top3[0] in _POLYOL_MARKERS and not any(x in _WATER_MARKERS for x in inci_names):
        return "hydrous"
    return "anhydrous"


def _derive_texture(name_text: str, category_text: str) -> str:
    text = f"{name_text} {category_text}"
    if "gel cream" in text or "gel-cream" in text:
        return "gel_cream"
    if "gel" in text:
        return "gel"
    if "rich cream" in text:
        return "rich_cream"
    if "balm" in text:
        return "balm"
    if "cream" in text:
        return "cream"
    if "oil" in text:
        return "oil"
    if "foam" in text:
        return "foam"
    return "lotion"


def _derive_continuous_phase(top7: list[str]) -> str:
    if any(any(marker in inci for marker in _SILICONE_MARKERS) for inci in top7):
        return "silicone"
    if any(any(marker in inci for marker in _LIPID_MARKERS) for inci in top7):
        return "lipidic"
    return "aqueous"


def _derive_fragrance_level(inci_names: list[str]) -> str:
    if not inci_names:
        return "none"
    hits = [x for x in inci_names if any(marker in x for marker in _FRAGRANCE_MARKERS)]
    if not hits:
        return "none"
    if any(x in inci_names[:5] for x in hits):
        return "standard"
    return "low"


def _derive_alcohol_level(top5: list[str], inci_names: list[str]) -> str:
    if any(any(marker in inci for marker in _ALCOHOL_HIGH_MARKERS) for inci in top5):
        return "high"
    if any(any(marker in inci for marker in _ALCOHOL_HIGH_MARKERS) for inci in inci_names[:10]):
        return "medium"
    if any("benzyl alcohol" in inci for inci in inci_names):
        return "low"
    return "none"


def _derive_finish(name_text: str, category_text: str) -> str | None:
    if category_text not in {"sunscreen", "primer", "makeup"} and "spf" not in name_text:
        return None
    if "matte" in name_text:
        return "matte"
    if "dewy" in name_text:
        return "dewy"
    if "luminous" in name_text or "glow" in name_text:
        return "luminous"
    return "natural"


def _derive_comedogenic(inci_names: list[str]) -> tuple[str, list[str]]:
    try:
        cfg = load_config("comedogen_tiers.yaml")
    except FileNotFoundError:
        cfg = load_config("comedogenic_tiers.yaml")
    tier_map = cfg.get("tier_map", {})
    high = _match_terms(inci_names, tier_map.get("high", []))
    moderate = _match_terms(inci_names, tier_map.get("moderate", []))
    if high:
        return "high", high[:4]
    if moderate:
        return "moderate", moderate[:4]
    return "low", []


def _derive_fungal_acne(inci_names: list[str]) -> tuple[str, list[str]]:
    cfg = load_config("fungal_acne_triggers.yaml")
    triggers = _match_terms(inci_names, cfg.get("trigger_ingredients", []))
    if not triggers:
        return "yes", []
    if any(x in inci_names[:7] for x in triggers):
        return "no", triggers[:4]
    return "caution", triggers[:4]


def _match_terms(inci_names: list[str], terms: list[Any]) -> list[str]:
    out: list[str] = []
    normalized_terms = [str(t).strip().lower() for t in terms if str(t).strip()]
    for term in normalized_terms:
        if any(term in inci for inci in inci_names):
            out.append(term)
    return list(dict.fromkeys(out))

