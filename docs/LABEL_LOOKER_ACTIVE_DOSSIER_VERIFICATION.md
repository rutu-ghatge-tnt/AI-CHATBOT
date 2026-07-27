# Label Looker — Active dossier enrichment (expert verification pack)

**Date:** 2026-07-27  
**Scope:** Ground Claude ingredient analysis in SkinBB Active ingredient DB (functionality + chemical class + description).  
**No new prompt files** — extensions live inside existing `ingredient_analysis_user_message`.

---

## 1. Product rules (locked)

| Rule | Decision |
|------|----------|
| Active filter | Branded: `category_decided == "Active"` · INCI: `category == "Active"` (case-insensitive) |
| Lookup order | `ingre_branded_ingredients` **first** → then `ingre_inci` |
| Description | Prefer `enhanced_description`, else `description` |
| Filters | Do **not** skip on `approved` / `isDeleted` |
| Volume | Send **all** Active hits (no 3–5 cap on dossiers) |
| Functionality | Branded: resolve `functional_category_ids` → `ingre_functional_categories.functionalName` · INCI: use string array `functionality` as-is |
| Chemical class | Branded: resolve `chemical_class_ids` → `ingre_chemical_classes.chemicalClassName` · INCI: usually empty (no class field on docs) |
| Branded hit but not Active | Do **not** fall through to INCI for that same candidate |
| Prompt | Extend existing analysis prompt only |
| **Match scoring** | Active dossiers also feed `build_product_benefit_signals` → `evaluate_suitability` (not prompt-only) |

---

## 2. Mongo collections used

| Collection | Role |
|------------|------|
| `ingre_branded_ingredients` | Primary Active source (`category_decided`, IDs, descriptions) |
| `ingre_inci` | Fallback Active source (`category`, `functionality[]`, `description`) |
| `ingre_functional_categories` | Resolve branded functionality names |
| `ingre_chemical_classes` | Resolve branded chemical class names |
| `products` | Candidate ingredient ObjectIds / names (`ingredients`, `keyIngredients`) |

Env overrides (optional): `LABEL_LOOKER_INCI_COLLECTION`, `LABEL_LOOKER_FUNCTIONAL_CATEGORIES_COLLECTION`, `LABEL_LOOKER_CHEMICAL_CLASSES_COLLECTION`, `LABEL_LOOKER_BRANDED_INGREDIENT_COLLECTION`.

---

## 3. Call path

```text
POST /api/v1/scanner/analyze-product
POST /api/v1/scanner/analyze-product/text
POST /api/v1/scanner/match-my-profile  (orchestration → text analysis)
batch analyze_catalog_product
        │
        ▼
product_analysis_engine.run_claude_product_analysis
        │
        ├─ resolve_active_ingredient_dossiers(ing_list, product)
        ├─ format_active_dossiers_for_prompt(...)
        └─ ingredient_analysis_user_message(..., active_dossiers_text=...)
                │
                ▼
          Claude messages.create (user message only; no separate system prompt)
```

---

## 4. Files to review

| File | Why |
|------|-----|
| `app/label_looker/prompts_controller.py` | Full analysis prompt + dossier block |
| `app/label_looker/services/active_ingredient_dossiers.py` | Active resolution + formatting |
| `app/label_looker/services/product_analysis_engine.py` | Wiring into Claude call |
| `app/label_looker/core/settings.py` | New collection settings |
| `tests/test_active_ingredient_dossiers.py` | Prompt/format unit tests |

---

## 5. Full prompt template (as sent to Claude)

Placeholders:

- `{specific_type}` — product type string (may be empty)
- `{main_benefit}` — main benefit string (may be empty)
- `{language}` — response language (default `English`)
- `{ingredients_text}` — newline-separated full INCI/name list
- `{active_dossiers_text}` — formatted Active dossiers (block omitted entirely if empty)
- `{personalization_context}` — optional; only when personalized matching is on

### 5.1 Base prompt (always)

```text
You must respond with ONLY valid JSON. Do not include any explanatory text before or after the JSON.
Analyze the following {specific_type} formula for {main_benefit}. Generate a response in {language}. Retain ingredient names in {language} and structure as follows:
 
        1.  Opinion on product efficacy in minimum 30 words. => with key "opinion" for json object       
 
        2. Key Ingredients: List top 3-5 active ingredients with names and one key benefit. => with key "keyIngredients" for json object       
           Prefer Active dossiers when present; phrase the key benefit from functionality / description.
 
        3. Benefits Offered: State 2-3 most important benefits offered by the whole formula. => with key "benefitsOffered" for json object
 
        4. Important Considerations: List 2 key points. => with key "importantConsiderations" for json object
 
        5. Product Usage Tips: Provide 3 specific tips. => with key "productUsageTips" for json object
 
        6. Ingredient Categorization: Group ingredients into: => with key "ingredientCategorization" for json object
 
           - Plant-Derived => with key "plant-derived"
 
           - Synthetic => with key "synthetic"
 
           - Marine => with key "marine-non-animal"
 
           - Animal-Origin => with key "animal-origin"
 
           - Unknown (if source cannot be confirmed or if multiple sources available) => with key "unknown"           
 
        Note: Do not include water in any category
 
        Ingredient list:  {ingredients_text}

{OPTIONAL_ACTIVE_DOSSIERS_BLOCK}

        IMPORTANT: Return ONLY valid JSON. Start your response with { and end with }. Do not include any text before or after the JSON object.
```

### 5.2 Optional Active dossiers block (inserted when ≥1 Active resolved)

```text
Authoritative Active ingredient dossiers from SkinBB DB (prefer these facts; do not contradict them).
These are Active-only ingredients resolved from branded ingredients first, then INCI.
When writing keyIngredients and formula commentary, ground claims in the functionality, chemical class, and description below - do not invent conflicting mechanisms or benefits.
Do not invent active percentages.

Active dossiers:
{active_dossiers_text}
```

### 5.3 Per-active dossier line format

```text
1. Name: {name}
   Functionality: {comma-separated functional names | n/a}
   Chemical class: {comma-separated class names | n/a}
   Description: {enhanced_description or description, plain text, max ~1200 chars}
```

### 5.4 Optional personalization appendix (unchanged; only if personalized)

```text
Personalization Context (apply for matching recommendations):
{personalization_context}

When personalization context is present, include this key in the same JSON:
"profileMatchInsights": {
  "worksForUser": "yes|no|partial",
  "matchScore": 0-100,
  "summary": "2-4 sentence decision on whether product suits this user profile",
  "whyItWorks": ["..."],
  "possibleRisks": ["..."],
  "forThisUserBestUse": ["..."],
  "betterAlternativeDirection": ["..."]
}
```

---

## 6. Example filled prompt (illustrative)

```text
You must respond with ONLY valid JSON. Do not include any explanatory text before or after the JSON.
Analyze the following serum formula for soothing. Generate a response in English. Retain ingredient names in English and structure as follows:
 
        1.  Opinion on product efficacy in minimum 30 words. => with key "opinion" for json object       
 
        2. Key Ingredients: List top 3-5 active ingredients with names and one key benefit. => with key "keyIngredients" for json object       
           Prefer Active dossiers when present; phrase the key benefit from functionality / description.
 
        3. Benefits Offered: State 2-3 most important benefits offered by the whole formula. => with key "benefitsOffered" for json object
 
        4. Important Considerations: List 2 key points. => with key "importantConsiderations" for json object
 
        5. Product Usage Tips: Provide 3 specific tips. => with key "productUsageTips" for json object
 
        6. Ingredient Categorization: Group ingredients into: => with key "ingredientCategorization" for json object
 
           - Plant-Derived => with key "plant-derived"
 
           - Synthetic => with key "synthetic"
 
           - Marine => with key "marine-non-animal"
 
           - Animal-Origin => with key "animal-origin"
 
           - Unknown (if source cannot be confirmed or if multiple sources available) => with key "unknown"           
 
        Note: Do not include water in any category
 
        Ingredient list:  Aqua
Cnidium Monnieri Fruit Extract
Carmine
Phenoxyethanol


Authoritative Active ingredient dossiers from SkinBB DB (prefer these facts; do not contradict them).
These are Active-only ingredients resolved from branded ingredients first, then INCI.
When writing keyIngredients and formula commentary, ground claims in the functionality, chemical class, and description below - do not invent conflicting mechanisms or benefits.
Do not invent active percentages.

Active dossiers:
1. Name: Cnidium Monnieri Fruit Extract
   Functionality: Antimicrobial, Skin conditioning
   Chemical class: Mixtures
   Description: Valued for antimicrobial and calming effects on irritated skin.
2. Name: Carmine
   Functionality: Colorant
   Chemical class: n/a
   Description: Natural red pigment derived from cochineal.

        IMPORTANT: Return ONLY valid JSON. Start your response with { and end with }. Do not include any text before or after the JSON object.
```

---

## 7. Expected Claude JSON keys (unchanged schema)

- `opinion`
- `keyIngredients`
- `benefitsOffered`
- `importantConsiderations`
- `productUsageTips`
- `ingredientCategorization` (`plant-derived`, `synthetic`, `marine-non-animal`, `animal-origin`, `unknown`)
- optional `profileMatchInsights` when personalized

Post-processing may still overwrite `keyIngredients` names from product DB key-ingredient list (`_apply_db_key_ingredients`).

---

## 8. Expert verification checklist

- [ ] Only `Active` branded/INCI rows appear in dossiers (excipients like Phenoxyethanol must not appear unless categorized Active)
- [ ] Branded Active preferred over INCI when both could match
- [ ] Branded non-Active does not fall through to INCI
- [ ] Functionality / chemical class come from taxonomy collections for branded (not free-invented)
- [ ] Description prefers `enhanced_description`
- [ ] `approved: false` / `isDeleted: true` Actives are still included
- [ ] All Actives on the formula are sent (not capped at 3–5); Claude may still list only top 3–5 in `keyIngredients` per prompt item 2
- [ ] Empty Active set → dossiers block omitted; rest of prompt unchanged aside from the new keyIngredients guidance line
- [ ] Personalized path still appends `profileMatchInsights` instructions
- [ ] Restart backend after deploy (`get_label_looker_settings` is process-cached)

---

## 9. How to reproduce a live prompt locally

```python
# After backend env is loaded:
from app.label_looker.services.active_ingredient_dossiers import (
    resolve_active_ingredient_dossiers,
    format_active_dossiers_for_prompt,
)
from app.label_looker.prompts_controller import ingredient_analysis_user_message
import asyncio

async def main():
    names = ["Aqua", "Cnidium Monnieri Fruit Extract", "Carmine", "Phenoxyethanol"]
    dossiers = await resolve_active_ingredient_dossiers(ingredient_names=names, product=None)
    text = format_active_dossiers_for_prompt(dossiers)
    print(ingredient_analysis_user_message(
        ingredients_text="\n".join(names),
        specific_type="serum",
        main_benefit="soothing",
        langauge="English",
        active_dossiers_text=text or None,
    ))

asyncio.run(main())
```
