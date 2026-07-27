"""
Dry-run Label Looker Active-dossier prompt for Continual-G Serum.

Uses caller-supplied product/profile data (product may live only in prod).
Writes a detailed verification log: candidate lookup, dossiers, full Claude
prompt, raw model response, parsed JSON.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from anthropic import AsyncAnthropic  # noqa: E402

from app.label_looker.core.settings import get_label_looker_settings  # noqa: E402
from app.label_looker.modules.product_analysis.analysis_service_impl import (  # noqa: E402
    _build_personalization_context,
    _normalize_analysis_payload,
)
from app.label_looker.prompts_controller import ingredient_analysis_user_message  # noqa: E402
from app.label_looker.services.active_ingredient_dossiers import (  # noqa: E402
    _find_branded_doc,
    _find_inci_doc,
    _is_active_category,
    format_active_dossiers_for_prompt,
    resolve_active_ingredient_dossiers,
)
from app.label_looker.text_extract import extract_first_json_object  # noqa: E402

# --- Continual-G Serum (prod PDP; not required in this Mongo) -----------------
PRODUCT_NAME = "Continual-G Serum"
PRODUCT_ID = "6a0c4108c279308586234325"
SPECIFIC_TYPE = "serum"
MAIN_BENEFIT = "Brightens And Evens Skin Tone"

KEY_INGREDIENTS = [
    "Glyteine",
    "Dimethicone/Vinyl Dimethicone Crosspolymer",
    "Vitamin E",
    "Tetrahydrocurcumin",
]

ALL_INGREDIENTS = [
    "Gamma-Glutamylcysteine",
    "Dimethicone/Vinyl Dimethicone Crosspolymer",
    "Caprylic/Capric Triglyceride",
    "Cyclopentasiloxane",
    "Tocopheryl Acetate",
    "Phenoxyethanol",
    "Ethylhexylglycerin",
    "Tetrahydrocurcumin",
    "Fragrance",
    "BHT",
]

# Alias map for marketing names → likely INCI / branded names in DB
NAME_ALIASES: dict[str, list[str]] = {
    "Glyteine": ["Glyteine", "Gamma-Glutamylcysteine", "Gamma Glutamylcysteine"],
    "Vitamin E": ["Vitamin E", "Tocopheryl Acetate", "Tocopherol"],
    "Gamma-Glutamylcysteine": ["Gamma-Glutamylcysteine", "Glyteine", "Gamma Glutamylcysteine"],
}

USER_DETAILS = {
    "_id": "6a32a241e7a6ac6299762a0c",
    "userId": "6a32a1ef9e214d0b3780c0c5",
    "age": 22,
    "gender": "female",
    "skinType": "combination",
    "skinConcerns": ["Dryness", "uneven-skintone", "dark-circles"],
    "skinTone": "#F1BF9A",
    "skinGoals": [],
    "hairType": [],
    "hairConcerns": [],
    "hairGoals": [],
    "scalpConcern": ["dandruff"],
}


def _log(lines: list[str], msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))
    lines.append(msg)


async def _probe_name(db, name: str) -> dict:
    """Detailed branded → INCI probe for one display name (incl. aliases)."""
    s = get_label_looker_settings()
    branded_coll = db[s.coll_branded_ingredient]
    inci_coll = db[s.coll_inci]
    variants = list(dict.fromkeys([name] + NAME_ALIASES.get(name, [])))
    result: dict = {"input": name, "variants_tried": variants, "branded": None, "inci": None}

    for variant in variants:
        branded = await _find_branded_doc(branded_coll, oid=None, name=variant)
        if branded:
            result["branded"] = {
                "matched_variant": variant,
                "_id": str(branded.get("_id")),
                "ingredient_name": branded.get("ingredient_name"),
                "original_inci_name": branded.get("original_inci_name"),
                "category_decided": branded.get("category_decided"),
                "is_active": _is_active_category(branded.get("category_decided")),
                "functional_category_ids_count": len(branded.get("functional_category_ids") or []),
                "chemical_class_ids_count": len(branded.get("chemical_class_ids") or []),
                "has_enhanced_description": bool(str(branded.get("enhanced_description") or "").strip()),
                "has_description": bool(str(branded.get("description") or "").strip()),
                "approved": branded.get("approved"),
                "isDeleted": branded.get("isDeleted"),
            }
            break

    for variant in variants:
        inci = await _find_inci_doc(inci_coll, oid=None, name=variant)
        if inci:
            result["inci"] = {
                "matched_variant": variant,
                "_id": str(inci.get("_id")),
                "inciName": inci.get("inciName"),
                "category": inci.get("category"),
                "is_active": _is_active_category(inci.get("category")),
                "functionality": inci.get("functionality"),
                "has_description": bool(str(inci.get("description") or "").strip()),
            }
            break

    return result


async def main() -> None:
    get_label_looker_settings.cache_clear()
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    lines: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = ROOT / "logs" / f"continual_g_active_prompt_{stamp}.log"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def L(msg: str = "") -> None:
        _log(lines, msg)

    L("=" * 80)
    L(f"Continual-G Active-dossier prompt test @ {stamp}")
    L("=" * 80)
    L(f"Product: {PRODUCT_NAME} (prod id={PRODUCT_ID})")
    L(f"Mongo database: {s.mongo_database}")
    L(f"Collections: branded={s.coll_branded_ingredient} inci={s.coll_inci}")
    L(f"             functional={s.coll_functional_categories} chemical={s.coll_chemical_classes}")
    L(f"Claude model: {s.anthropic_model}")
    L("")
    L("--- INPUT: All ingredients ---")
    for i, n in enumerate(ALL_INGREDIENTS, 1):
        L(f"  {i}. {n}")
    L("")
    L("--- INPUT: Key ingredients (marketing) ---")
    for i, n in enumerate(KEY_INGREDIENTS, 1):
        L(f"  {i}. {n}")
    L("")
    L("--- INPUT: Personalization profile ---")
    L(json.dumps(USER_DETAILS, indent=2))
    personalization = _build_personalization_context(USER_DETAILS)
    L("")
    L("--- Built personalization_context (sent to Claude when personalized=True) ---")
    L(personalization or "(empty)")

    # Synthetic product doc so resolver also walks keyIngredients / ingredients rows
    product = {
        "_id": PRODUCT_ID,
        "name": PRODUCT_NAME,
        "ingredients": [{"name": n} for n in ALL_INGREDIENTS],
        "keyIngredients": [{"name": n} for n in KEY_INGREDIENTS],
    }

    L("")
    L("=" * 80)
    L("STEP 1 - Per-name branded -> INCI probe (includes aliases)")
    L("=" * 80)
    probe_names = list(dict.fromkeys(KEY_INGREDIENTS + ALL_INGREDIENTS))
    probes = []
    for name in probe_names:
        probe = await _probe_name(db, name)
        probes.append(probe)
        L(f"\n[{name}]")
        L(f"  variants: {probe['variants_tried']}")
        if probe["branded"]:
            L(f"  BRANDED HIT: {json.dumps(probe['branded'], indent=2)}")
        else:
            L("  BRANDED: none")
        if probe["inci"]:
            L(f"  INCI HIT: {json.dumps(probe['inci'], indent=2)}")
        else:
            L("  INCI: none")

    L("")
    L("=" * 80)
    L("STEP 2 - resolve_active_ingredient_dossiers (production code path)")
    L("=" * 80)
    dossiers = await resolve_active_ingredient_dossiers(
        ingredient_names=ALL_INGREDIENTS,
        product=product,
        db=db,
    )
    L(f"Active dossiers resolved: {len(dossiers)}")
    L(json.dumps(dossiers, indent=2))
    dossiers_text = format_active_dossiers_for_prompt(dossiers)
    L("")
    L("--- Formatted dossiers block ---")
    L(dossiers_text or "(empty - dossiers block will be OMITTED from prompt)")

    L("")
    L("=" * 80)
    L("STEP 3 - Full Claude user prompt")
    L("=" * 80)
    prompt = ingredient_analysis_user_message(
        ingredients_text="\n".join(ALL_INGREDIENTS),
        specific_type=SPECIFIC_TYPE,
        main_benefit=MAIN_BENEFIT,
        langauge="English",
        personalization_context=personalization,
        active_dossiers_text=dossiers_text or None,
    )
    L(prompt)
    L("")
    L(f"Prompt char length: {len(prompt)}")
    L(f"Prompt approx tokens (~chars/4): {len(prompt) // 4}")

    L("")
    L("=" * 80)
    L("STEP 4 - Claude call")
    L("=" * 80)
    # Prefer env model; if Anthropic returns 404, retry a known-good Sonnet id.
    model_candidates = [
        s.anthropic_model,
        "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929",
        "claude-sonnet-5",
    ]
    # de-dupe preserving order
    seen_m: set[str] = set()
    models = []
    for m in model_candidates:
        m = (m or "").strip()
        if m and m not in seen_m:
            seen_m.add(m)
            models.append(m)

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    msg = None
    last_err: Exception | None = None
    used_model = None
    for model in models:
        L(f"Trying model: {model}")
        try:
            msg = await client.messages.create(
                model=model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            used_model = model
            break
        except Exception as exc:
            last_err = exc
            L(f"  FAILED: {type(exc).__name__}: {exc}")

    if msg is None:
        L(f"ALL MODELS FAILED. Last error: {last_err}")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote partial log (no Claude response) -> {out_path}")
        raise SystemExit(2) from last_err

    raw = "".join(getattr(b, "text", "") for b in msg.content)
    L(f"used_model: {used_model}")
    L(f"stop_reason: {msg.stop_reason}")
    L(f"usage: input={getattr(msg.usage, 'input_tokens', None)} output={getattr(msg.usage, 'output_tokens', None)}")
    L("")
    L("--- Raw Claude text ---")
    L(raw)

    L("")
    L("=" * 80)
    L("STEP 5 - Parsed / normalized analysis payload")
    L("=" * 80)
    try:
        parsed = extract_first_json_object(raw)
        L("--- extract_first_json_object ---")
        L(json.dumps(parsed, indent=2, ensure_ascii=False))
        analytic, ing_out = _normalize_analysis_payload(parsed, ALL_INGREDIENTS)
        L("")
        L("--- After _normalize_analysis_payload ---")
        L(json.dumps({"analyticDetail": analytic, "ingredients": ing_out}, indent=2, ensure_ascii=False))
    except Exception as exc:
        L(f"PARSE FAILED: {type(exc).__name__}: {exc}")

    L("")
    L("=" * 80)
    L("SUMMARY")
    L("=" * 80)
    active_names = [d.get("name") for d in dossiers]
    missing = [n for n in ALL_INGREDIENTS if not any(
        (p["input"] == n) and (p.get("branded") or p.get("inci")) for p in probes
    )]
    L(f"Actives sent to Claude: {active_names}")
    L(f"Ingredients with ZERO DB hit (branded+inci): {missing}")
    L(f"Dossiers block present: {bool(dossiers_text.strip())}")
    L(f"Personalized: True")
    L(f"Log file: {out_path}")

    # Data-quality flags for Continual-G
    L("")
    L("--- Data quality flags ---")
    for p in probes:
        if p["input"] in ("Glyteine", "Gamma-Glutamylcysteine"):
            L(
                f"{p['input']}: branded_active={bool(p.get('branded') and p['branded'].get('is_active'))} "
                f"inci_active={bool(p.get('inci') and p['inci'].get('is_active'))} "
                f"branded_category={((p.get('branded') or {}).get('category_decided'))} "
                f"inci_category={((p.get('inci') or {}).get('category'))}"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote full log -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
