from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """You are the editorial voice of LabelLooker 2.0 (LL2.0), a skincare ingredient analysis tool for SkinBB.

<role>
LL2.0 takes a user's skin profile and a product's ingredient list and produces a personalized match analysis. The numeric score and structural analysis are already done by a deterministic engine. You receive those results and translate them into warm, precise, editorial prose for a 5-tile result carousel.

You do not decide the match state, the score, or which ingredients matter - those are given. You write the prose that explains what the structural facts mean, in the voice described below.
</role>

<voice>
Write as a dermatologist who happens to be the user's smartest friend. Warm but precise. Confident but humble. Never alarmist.

Core principles:
1. Describe, don't prescribe. You are not telling the user what to do - you are helping them understand what they're looking at. The user decides whether to buy.
2. Name the specific thing. "Niacinamide at position 3" not "an active ingredient." "Ceramides at positions 7-9" not "barrier support."
3. Credit good formulation even in low matches. A well-built product for the wrong skin type is still well-built. Say so.
4. Attribute claims to evidence, never to yourself. "Clinically well-established" not "we think this works."
5. Never impugn brand motives. A gap between marketing hero and actual active is a story worth telling, but tell it neutrally - no sarcasm, no accusations.
6. Match tone to the match state. Great Match can feel warm and assured. Low Match should feel clarifying, never discouraging or condescending.
7. No jargon without a parenthetical on first use. "Comedogenic (pore-clogging)" - not just "comedogenic."
8. No emoji. No exclamation marks except in the rare celebration moment. No sarcasm.
9. Indian market cultural awareness: descriptive, not patronizing. The user is a skincare enthusiast who wants to learn, not a novice being lectured.
</voice>

<tile_specifications>
**verdict** - One sentence. 10-16 words. Quotable. This is the hardest-working copy in the product; it's what the user might screenshot. Format: a statement about fit, not a recommendation.
**works** - 1-2 sentences, 20-45 words. What in the formula actively contributes to this user's goals. Name the ingredient and its position.
**falls_short** - Two modes determined by the `falls_short_tone` field you emit:
- "caution" mode (Good Match, Low Match, anything with unmet needs): name the gap specifically. 1-2 sentences, 20-45 words.
- "positive" mode (Great Match with no unmet needs ONLY): reframe positively. Format: "No significant gaps - this formula addresses [summary]." 10-20 words.
**worth_knowing** - 1-3 sentences, 20-60 words. The nuance - a marketing-vs-formula note, introduction guidance, or formulation fact.
**covered_message** - Only emit when the user's match state is "great" AND the unmet_needs list is empty. 1-2 sentences, 15-30 words. Positive summary of what's covered. Null otherwise.
</tile_specifications>

<strict_rules>
1. Only name ingredients explicitly listed in the product data. Do not invent, infer, or substitute ingredient names.
2. Only reference positions that are given in the product data. Do not guess positions.
3. Do not recommend or dissuade. Describe. Let the user decide.
4. Do not use alarmist language.
5. Do not apologize on the brand's behalf. State facts neutrally.
6. Stay within stated word counts. Going long signals uncertainty.
7. Output valid JSON matching the output schema exactly. No commentary before or after.
8. When a triggered observation is provided, prefer its content for `worth_knowing`.
</strict_rules>

<output_schema>
Return a single JSON object, no other text:
{
  "verdict": "<10-16 word statement>",
  "works": "<20-45 word explanation>",
  "falls_short": "<20-45 word explanation, OR 10-20 word positive reframe>",
  "falls_short_tone": "caution" | "positive",
  "worth_knowing": "<20-60 word nuance>",
  "covered_message": "<15-30 words, or null>"
}
</output_schema>

Think carefully about the specific ingredients and positions before writing. The ingredients you name in the output must appear in the input. Output only the JSON object."""


USER_PROMPT_TEMPLATE = """<user_profile>
Age: {age}
Gender: {gender}
Profile mode: {profile_mode}
{type_label}: {profile_type}
{concerns_label} (priority order): {concerns}
Desired benefits: {benefits}
</user_profile>

<product>
Brand: {brand}
Name: {product_name}
Category: {category}
Declared for skin types: {declared_for}
Label claims:
{claims_list}

All ingredients (INCI order):
{all_ingredients_list}

Key ingredients (highlighted):
{key_ingredients_list}
</product>

<scoring_results>
State: {state}
Score: {score}
Band: {band}

Scoring breakdown:
{scoring_breakdown}

Unmet needs: {unmet_needs}
</scoring_results>

<triggered_observations>
{observations_block}
</triggered_observations>

<editorial_context>
{editorial_notes}

Generate the tile content as JSON per the schema.
</editorial_context>"""


def build_prompt(
    *,
    user: dict[str, Any],
    product: dict[str, Any],
    scoring: dict[str, Any],
    observations: list[dict[str, Any]] | None = None,
) -> str:
    observations = observations or []

    profile_mode = str(user.get("mode") or "skincare").strip().lower()
    if profile_mode not in {"skincare", "haircare", "lipcare"}:
        profile_mode = "skincare"
    concerns = ", ".join(user.get("concerns", [])) or "none declared"
    benefits = ", ".join(user.get("benefits", [])) or "none specified"
    if profile_mode == "haircare":
        type_label = "Hair type"
        concerns_label = "Hair concerns"
        profile_type = user.get("hair_type") or user.get("skin_type", "-")
    elif profile_mode == "lipcare":
        type_label = "Lip type"
        concerns_label = "Lip concerns"
        profile_type = user.get("lip_type") or user.get("skin_type", "-")
    else:
        type_label = "Skin type"
        concerns_label = "Skin concerns"
        profile_type = user.get("skin_type", "-")

    declared_for = ", ".join(product.get("declared_for_skin_types", [])) or "not specified"
    claims = product.get("claims", [])
    claims_list = "\n".join(f"- {claim}" for claim in claims) if claims else "- (no specific claims)"
    all_ingredients_list = _format_ingredients(product.get("ingredients", []))
    key_ingredients_list = _format_ingredients(product.get("key_ingredients", []))

    state = scoring.get("state", "unknown")
    score = scoring.get("score", "-")
    band = scoring.get("band", "-")
    unmet = scoring.get("unmet_needs", [])
    unmet_str = ", ".join(unmet) if unmet else "[none]"
    breakdown_str = _format_breakdown(scoring.get("breakdown", []))

    if observations:
        parts = []
        for observation in observations:
            oid = str(observation.get("id", "?")).strip() or "?"
            name = str(observation.get("name", "Unnamed observation")).strip()
            editorial_text = str(observation.get("editorial_text", "")).strip()
            parts.append(f"- {oid} ({name}): {editorial_text}")
        observations_block = "\n".join(parts)
    else:
        observations_block = "None triggered."

    editorial_notes = _build_editorial_notes(scoring=scoring, observations=observations)

    return USER_PROMPT_TEMPLATE.format(
        age=user.get("age", "-"),
        gender=user.get("gender", "-"),
        profile_mode=profile_mode,
        type_label=type_label,
        profile_type=profile_type,
        concerns_label=concerns_label,
        concerns=concerns,
        benefits=benefits,
        brand=product.get("brand", "-"),
        product_name=product.get("name", "-"),
        category=product.get("category", "-"),
        declared_for=declared_for,
        claims_list=claims_list,
        all_ingredients_list=all_ingredients_list,
        key_ingredients_list=key_ingredients_list,
        state=state,
        score=score,
        band=band,
        scoring_breakdown=breakdown_str,
        unmet_needs=unmet_str,
        observations_block=observations_block,
        editorial_notes=editorial_notes,
    )


def _format_ingredients(ingredients: list[dict[str, Any]]) -> str:
    if not ingredients:
        return "- (no enriched ingredient data available)"

    lines: list[str] = []
    for ingredient in sorted(ingredients, key=lambda row: row.get("position", 999)):
        position = ingredient.get("position", "?")
        name = ingredient.get("inci_name", "Unknown")
        functions = ingredient.get("functions", [])
        addresses = ingredient.get("addresses", [])
        declared_pct = ingredient.get("declared_percentage")

        details: list[str] = []
        if functions:
            details.append(" + ".join(str(item) for item in functions))
        if addresses:
            details.append(f"addresses: {', '.join(str(item) for item in addresses)}")
        if declared_pct is not None:
            details.append(f"declared {declared_pct}%")

        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- Position {position}: {name}{suffix}")

    return "\n".join(lines)


def _format_breakdown(breakdown: list[dict[str, Any]]) -> str:
    if not breakdown:
        return "- (no breakdown available)"

    lines: list[str] = []
    for entry in breakdown:
        label = _breakdown_label(entry)
        answer = str(entry.get("answer", "?")).upper()
        note = str(entry.get("note", "")).strip()
        weight = entry.get("weight")
        weight_str = f" (weight {int(weight * 100)}%)" if weight is not None else ""
        note_str = f" - {note}" if note else ""
        lines.append(f"- {label}{weight_str}: {answer}{note_str}")
    return "\n".join(lines)


def _breakdown_label(entry: dict[str, Any]) -> str:
    category = str(entry.get("category", ""))
    if category == "skin_type":
        return "Skin type match"
    if category.startswith("concern"):
        rank = category.replace("concern_", "").capitalize() or "Concern"
        concern_name = str(entry.get("concern", "")).strip()
        return f"{rank} concern ({concern_name!r})" if concern_name else f"{rank} concern"
    if category == "demographic":
        return "Demographic/age appropriateness"
    if category == "claims":
        return "Claims honesty"
    if category == "safety":
        return "Safety check"
    return category.replace("_", " ").capitalize()


def _build_editorial_notes(*, scoring: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    state = scoring.get("state", "unknown")
    unmet = scoring.get("unmet_needs", [])
    notes: list[str] = []

    if state == "great" and not unmet:
        notes.append("- This is a clean Great Match. falls_short should be positive mode; emit covered_message.")
    elif state == "great" and unmet:
        notes.append("- Great Match with unmet need(s). Use caution mode for falls_short. covered_message = null.")
    elif state == "good":
        notes.append("- Good Match with real gaps. Be honest without discouraging language. covered_message = null.")
    elif state == "low":
        notes.append("- Low Match. Credit what is well formulated; product may fit different users. covered_message = null.")

    if observations:
        notes.append("- A triggered observation is provided. Use its editorial_text as the basis for worth_knowing.")
    else:
        notes.append("- No triggered observations. Build worth_knowing from the most useful scoring nuance.")

    return "\n".join(notes)


async def generate_tile_content(
    *,
    inputs: dict[str, Any],
    client: Any,
    model: str = "claude-sonnet-4-6",
    temperature: float = 0.4,
    max_tokens: int = 800,
) -> dict[str, Any]:
    user_prompt = build_prompt(
        user=inputs["user"],
        product=inputs["product"],
        scoring=inputs["scoring"],
        observations=inputs.get("observations"),
    )

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        raise TileGenerationError(f"API call failed: {exc}") from exc

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    return parse_response(text=text, inputs=inputs)


def parse_response(*, text: str, inputs: dict[str, Any]) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TileGenerationError(f"Invalid JSON from API: {exc}") from exc

    required_keys = {"verdict", "works", "falls_short", "falls_short_tone", "worth_knowing"}
    missing = required_keys - parsed.keys()
    if missing:
        raise TileGenerationError(f"Response missing required keys: {missing}")

    if parsed["falls_short_tone"] not in {"caution", "positive"}:
        raise TileGenerationError(f"Invalid falls_short_tone: {parsed['falls_short_tone']}")

    state = inputs.get("scoring", {}).get("state")
    unmet = inputs.get("scoring", {}).get("unmet_needs", [])
    covered = parsed.get("covered_message")

    if covered and (state != "great" or unmet):
        parsed["covered_message"] = None

    return parsed


class TileGenerationError(Exception):
    pass


TEMPLATE_FALLBACKS: dict[str, dict[str, str]] = {
    "great": {
        "verdict_template": "Strong match on {top_concerns} - a good fit for your {skin_type} skin.",
        "works_template": "{top_ingredient} at position {top_position} targets your {top_concern}.",
        "falls_short_positive": "No significant gaps - this formula addresses your declared concerns.",
        "worth_knowing_template": "Introduce gradually to let your skin adjust to the active ingredients.",
    },
    "good": {
        "verdict_template": "Will help with {addressed} - just not {unmet_concern}.",
        "works_template": "{top_ingredient} at position {top_position} supports {addressed}.",
        "falls_short_template": "Doesn't address {unmet_concern} - no relevant active in the formula.",
        "worth_knowing_template": "Consider pairing with a product that targets {unmet_concern}.",
    },
    "low": {
        "verdict_template": "Built for {declared_type} - may not suit your {user_type} skin.",
        "works_template": "{top_ingredient} at position {top_position} offers some support.",
        "falls_short_template": "Formula is designed for {declared_type}, not {user_type}.",
        "worth_knowing_template": "A well-built product - just built for a different skin type than yours.",
    },
}


def build_fallback_tiles(*, inputs: dict[str, Any]) -> dict[str, Any]:
    scoring = inputs.get("scoring", {})
    user = inputs.get("user", {})
    product = inputs.get("product", {})

    state = scoring.get("state", "good")
    templates = TEMPLATE_FALLBACKS.get(state, TEMPLATE_FALLBACKS["good"])
    unmet = scoring.get("unmet_needs", [])

    concerns = user.get("concerns", [])
    top_concerns = ", ".join(concerns[:2]) or "your concerns"
    top_concern = concerns[0] if concerns else ""
    unmet_concern = unmet[0] if unmet else "a key concern"
    if top_concern and top_concern not in unmet:
        addressed = top_concern
    elif len(concerns) > 1:
        addressed = concerns[1]
    else:
        addressed = "some declared concerns"

    top_ingredient_row = (product.get("key_ingredients") or [{}])[0]
    top_ingredient = top_ingredient_row.get("inci_name", "The primary active")
    top_position = top_ingredient_row.get("position", "?")
    declared_type = ", ".join(product.get("declared_for_skin_types", ["certain types"]))
    user_type = str(user.get("skin_type", "")).lower() or "current"

    return {
        "verdict": templates["verdict_template"].format(
            top_concerns=top_concerns,
            skin_type=user_type,
            addressed=addressed,
            unmet_concern=unmet_concern,
            declared_type=declared_type,
            user_type=user_type,
        ),
        "works": templates["works_template"].format(
            top_ingredient=top_ingredient,
            top_position=top_position,
            top_concern=top_concern,
            addressed=addressed,
        ),
        "falls_short": (
            templates["falls_short_positive"]
            if state == "great" and not unmet
            else templates.get("falls_short_template", "").format(
                unmet_concern=unmet_concern,
                declared_type=declared_type,
                user_type=user_type,
            )
        ),
        "falls_short_tone": "positive" if state == "great" and not unmet else "caution",
        "worth_knowing": templates["worth_knowing_template"].format(unmet_concern=unmet_concern),
        "covered_message": (
            f"Your declared concerns - {top_concerns} - are covered by this formula."
            if state == "great" and not unmet
            else None
        ),
    }
