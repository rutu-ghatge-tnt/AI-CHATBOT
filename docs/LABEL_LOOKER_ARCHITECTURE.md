# Label Looker — architecture and feature guide

This document explains how **Label Looker** is wired into the SkinBB API, what each major feature does, the order of operations for the main flows, and where errors usually come from. It is meant to be read before stepping through the code line by line.

---

## 1. What Label Looker is

Label Looker is a **FastAPI sub-system** for:

1. **Product / label scanning** — upload an image; Claude extracts an ingredient list; results are stored in MongoDB.
2. **Ingredient analysis** — send a `scanId` (and optional `productId`, personalization flags); Claude returns structured JSON analysis; optional **LL2 tile** copy is generated.
3. **Text-based analysis** — same analysis idea without a prior image scan (ingredients list or pasted text).
4. **Single-ingredient lookup** — fetch or generate ingredient detail (Mongo + Claude).
5. **Profile validation** — lightweight state machine tied to `user_details` to prompt users to confirm profile fields after scans.
6. **Admin / panel** — list scans, analytics, ratings (panel JWT + permissions).
7. **Match My Profile** — separate API prefix: deterministic **safety + suitability scoring**, optional Claude **tiles**, credits tied to daily scan counts on the same scan collection.

It is **not** a separate service process: it mounts routers and static files on the main `FastAPI` app (`app/main.py`).

---

## 2. How it gets installed at runtime

```text
app/main.py
  └─> try: install_label_looker(app)
        └─> app/label_looker/bootstrap.py
```

### 2.1 `install_label_looker(app)`

Defined in `app/label_looker/bootstrap.py`:

1. Calls `get_label_looker_settings()` from `app/label_looker/core/settings.py`.
2. If that raises **`RuntimeError`** (missing required env), it **prints** `Label Looker: skipped (...)` and **returns without registering anything**.
3. Otherwise it:
   - Registers **`ScannerApiError`** → JSON error envelope (`api_error_response`).
   - Registers **`RequestValidationError`** for paths under `/scanner` or `/api/v1/scanner` only → wrapped as `ScannerApiError(422, ...)`.
   - Ensures `./public/product-scan-images` exists and mounts **`/product-scan-images`** as static files.
   - Imports auth dependencies from `app/label_looker/core/deps_auth.py`.
   - Mounts routers (see section 3).

### 2.2 Outer try/except in `main.py`

If `install_label_looker` raises **any** other exception, `main.py` catches it and prints:

`Warning: Label Looker not installed (...): ...`

So you can have **silent partial failure** (skipped for missing env) or **logged failure** (unexpected exception).

---

## 3. URL layout and routers

For **request/response field tables** and auth details aimed at frontend and Postman, see **`docs/LABEL_LOOKER_API_FRONTEND.md`**.

All routes are registered in `bootstrap.py`.

| Prefix | Auth pattern | Purpose |
|--------|----------------|---------|
| `/scanner/...` | Legacy SSO: `scanner_auth_sso` / optional / panel | Backward-compatible paths |
| `/api/v1/scanner/...` | App token first, then SSO fallback: `authenticate_any_user` | Preferred v1 scanner API |
| `/api/v1/match-my-profile/...` | `authenticate_any_user` | Match My Profile |

**Product analysis routes** (`app/label_looker/modules/product_analysis/routes.py`):

| Method | Path (relative to prefix) | Summary |
|--------|---------------------------|---------|
| POST | `/image-conversion` | Upload image → OCR-style ingredient list via Claude; creates scan row |
| POST | `/analyze-product` | Full analysis for existing scan |
| GET | `/ingredient?name=...` | Single ingredient detail |
| PUT | `/feedback` | Scan feedback |
| GET | `/scan-left` | Daily quota remaining |
| POST | `/analyze-product/text` | Analysis from text/list (optional auth) |
| POST | `/profile-validation/submit`, `/profile-validation/status` | Profile validation flow |
| GET | `/user/analysis`, `/user/analysis/{scan_id}` | User’s saved analyses |

**Admin routes** (same `/scanner` prefix, different router): `/analysis/list`, `/analysis/{scan_id}`, `/analytics`, `/user/total-scan`, `/rating-count` — use **panel** JWT (`verify_jwt_panel`).

**Match My Profile** (`app/label_looker/modules/match_my_profile/routes.py`):

| Method | Path | Summary |
|--------|------|---------|
| POST | `/score` | Score product (or hydrate prior scan if `scan_id` in body) |
| POST | `/scan/{scan_id}/feedback` | Thumbs / note on a match scan |
| GET/PATCH | `/profile` | Read/update match profile slice in `user_details` |

---

## 4. Configuration (`core/settings.py`)

`get_label_looker_settings()` is **`@lru_cache`** — first successful load wins for the process lifetime.

**Hard requirements** (else `RuntimeError` → Label Looker skipped):

| Variable | Role |
|----------|------|
| `SKIN_BB_BASE_URL` (or `CREDITS_API_BASE_URL` / `SERVER_URL`) | SkinBB API base for auth verify endpoints |
| `MONGODB_URI` or `MONGO_URI` | Mongo connection |
| `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` | Claude |

**Important optional / derived:**

- `SKIN_BB_CLIENT_SECRET` — required for **legacy scanner SSO** (`scanner_auth_sso`); without it, scanner SSO returns **500** “not configured”.
- Collection names default to `scan_analyses`, `scan_details`, `ingredients`, `products`, `user_details`, etc., overridable with `LABEL_LOOKER_*_COLLECTION` env vars (see `LabelLookerSettings`).
- `LABEL_LOOKER_INCLUDE_STACK` — whether error JSON includes Python stack trace.

---

## 5. Authentication (`core/deps_auth.py`)

Three families of callers:

1. **`scanner_auth_sso`** — `Authorization: Bearer <jwt>`. Calls `GET {SKIN_BB_BASE_URL}/api/v1/users/verify-token`, then decodes JWT with `SKIN_BB_CLIENT_SECRET` (HS256).
2. **`authenticate_app_user`** — `GET .../verify-app-token`; user in JSON `data.user`.
3. **`authenticate_any_user`** — tries app token first; on 401/403 falls back to scanner SSO. Used for `/api/v1/scanner` and `/api/v1/match-my-profile`.

**Panel:** `verify_jwt_panel` → `GET .../verify-panel-token`; permissions checked for `scan-overview` / `view` for admin list/detail.

---

## 6. Data layer (`core/db.py`)

- Single **Motor** client (`AsyncIOMotorClient`), cached with `lru_cache`.
- `get_scanner_db()` returns `client[mongo_database]`.

Most flows read/write **`scan_analyses`** (and **`scan_details`** for image conversion audit). User personalization uses **`user_details`**. Product enrichment uses **`products`**, **`ingre_branded_ingredients`**, **`ingredients`**.

---

## 7. Response shape

**Success** (`api_success` in `core/responses.py`):

```json
{
  "data": { ... },
  "statusCode": 200,
  "message": "...",
  "success": true
}
```

**Error** (`ScannerApiError` → `api_error_response`):

```json
{
  "status": "error",
  "success": false,
  "statusCode": 400,
  "message": "...",
  "errors": [ ... ],
  "stack": "..."
}
```

On scanner paths, **FastAPI validation errors** are forced into the same style (see `bootstrap.py`).

---

## 8. Feature walkthroughs

### 8.1 Image → ingredient list (`scan_service_impl.scan_image_to_text`)

**Route:** `POST .../image-conversion`

1. **`validate_upload`** (`upload_utils.py`) — MIME allowlist, max 5 MB.
2. **`save_scan_image`** — writes file under `public/product-scan-images/`, returns basename.
3. **Rate limit:** counts today’s docs in `scan_analyses` for `userProfileUrl` with `scanImageError: None`. If ≥ `totalScanIngedientPerDay` → **429**.
4. **Insert** `scan_analyses` row: empty `extractedIngredients`, `scansLeft`, etc.
5. **Claude** vision call with prompt from `prompts_controller.scan_image_to_text_prompt()` — model asked for array-format list.
6. **`extract_bracket_string_array`** (`text_extract.py`) — parses bracketed list from model text.
7. **Update** scan with ingredient names; **insert** `scan_details` companion doc.
8. On failure: set `scanImageError`, still insert detail, raise **`ScannerApiError(500, ...)`**.

**Return:** `{ "scanDetail": "<ObjectId string>", "ingredientNames": [...] }` inside the usual `data` envelope.

**Static URL:** client can show image via `/product-scan-images/<basename>`.

---

### 8.2 Full ingredient analysis (`analysis_service_impl._ingredient_analysis_impl`)

**Routes:** `POST .../analyze-product`

**Body expectations (minimum):**

- **`scanId`** (required) — must be valid ObjectId string; must exist in `scan_analyses`.

**Optional / behavior-changing:**

- **`ingredients`** — if omitted or empty, uses `extractedIngredients` from scan doc, or resolves from **`productId`** via product + branded ingredient collections.
- **`productId`** — enriches `specificType` / `main_benefit` from PDP; pulls INCI rows for DB key ingredients overlay.
- **`personalizedMatching`** — if true, **requires logged-in user**; loads `user_details` and appends personalization block to Claude prompt; also affects caching and `profileValidation` payload.
- **`langauge`** — intentional legacy spelling in code; defaults to `DEFAULT_LANGUAGE` if missing.

**Flow:**

1. Load scan; resolve ingredient list and optional product document.
2. If **not** personalized: try **`_find_cached_non_personalized_analysis`** — reuse another scan’s `analyticDetail` for same product to save tokens.
3. Build **`ingredient_analysis_user_message`** (`prompts_controller.py`) — strict JSON schema instructions; if personalized, adds `profileMatchInsights` keys Claude must fill.
4. Claude **`messages.create`** → concatenate text blocks → **`extract_first_json_object`**.
5. **`_normalize_analysis_payload`** — maps model output + ordered ingredient list.
6. **`_apply_db_key_ingredients`**, **`_ensure_profile_match_insights`**.
7. **`_maybe_attach_ll2_tile_content`** — if inputs build succeeds, **`generate_tiles_with_fallback`** (Claude tile copy, or template fallback on error).
8. **`$set`** on scan: `analyticDetail`, `ingredients`, `productId`, cache flags, clear `ingredientAnalysisError`.
9. If user logged in: **`_upsert_validation_state`** + **`_build_prompt_payload`** → returned as **`profileValidation`**.

**Failure:** generic user message `GENERIC_ANALYSIS_FAIL` as **500** `ScannerApiError`; DB stores `ingredientAnalysisError`.

---

### 8.3 Text-based analysis (`_ingredient_analysis_from_text_impl`)

**Routes:** `POST .../analyze-product/text`

- Does **not** require a prior image scan in the same way; can create/update scan rows from **`ingredients`**, product-derived list, or **`ingredientsText`** (parsed into names).
- Optional auth: if unauthenticated, logic paths that need `user_id` are skipped or constrained (see implementation for personalized branches).
- Similar Claude + normalize + tiles + profile validation pattern as above.

---

### 8.4 Single ingredient (`ingredient_service_impl.get_ingredient_detail_response`)

**Route:** `GET .../ingredient?name=...`

- Mongo aggregation / lookup (`aggregations.py`) plus possible Claude call (`prompt_ai_to_get_ingredient_details`).
- Raises **`ScannerApiError`** for missing name, not found, etc.

---

### 8.5 Feedback & scan quota

- **`PUT .../feedback`** — `put_feedback` updates scan doc (implementation in `analysis_service_impl`).
- **`GET .../scan-left`** — uses same daily counter as image flow (`number_of_scan_left` in `scan_service_impl`).

---

### 8.6 Profile validation

**Submit / status** routes call **`submit_profile_validation`** / **`profile_validation_status`** — they maintain structured state on `user_details` (modes: skincare / haircare / lipcare inferred in analysis helpers) and may call SkinBB user service to sync profile (`httpx` in `_sync_profile_to_user_service`).

Used so the app can **prompt** users to confirm age, type, concerns after repeated scans.

---

### 8.7 User analysis history

- **`GET .../user/analysis`** — paginated list for authenticated user.
- **`GET .../user/analysis/{scan_id}`** — one doc, ownership checked.

---

### 8.8 Admin / panel

- Depends on **`verify_jwt_panel`** and permission **`scan-overview` / `view`** (or `panel_auth_only` for analytics).
- Read-only listing and summaries over Mongo.

---

### 8.9 Match My Profile (`match_my_profile/service_impl.py`)

**`POST /api/v1/match-my-profile/score`**

Two modes:

1. **Hydrate existing scan** — if body contains **`scan_id`** / **`scanId`**, delegates to **`get_scan_result`** (re-fetch stored match from `scan_analyses`).
2. **New score** — **`_score_product_impl`**:
   - Requires **`product_id`** / **`productId`**.
   - Loads product; normalizes **mode** (skincare vs haircare) from body + product.
   - Loads **`user_details`**; merges **age, gender, skin/hair type, concerns**; **`desiredBenefits`** can come from body or profile goals.
   - Validates required fields; if missing → **400** with structured **`errors`** list (`missing_inputs`).
   - **Credits:** same daily scan count as Label Looker scans (`profileUrl`); if over limit → **402** `insufficient_credits`.
   - Builds **`tile_product`** (normalized INCI rows, claims, etc.).
   - **`resolve_runtime_context`** — season/climate hints from pin code + user flags.
   - **`derive_base_formula_record`** — heuristic record (texture, fragrance tier, comedogenic drivers, …).
   - **`evaluate_safety`** — retinoid / pregnancy / rosacea / fragrance / alcohol gates → may set **gate** state.
   - If not gated: **`evaluate_suitability`** — combines profile match matrix, benefits matching, **`score_base_formula`**, **`apply_overrides`**.
   - **Tiles:** either gate template or **`generate_tiles_with_fallback`** with structured `tile_inputs`.
   - **Inserts** a new `scan_analyses` document representing this “match” (reuses collection).
   - Returns large **`result`** object plus snake_case + camelCase duplicates for client compatibility.

**`GET/PATCH /profile`** — read/update **`user_details`** with nested `category_profiles` / `categoryProfiles` and `safety`.

---

## 9. Engines (deterministic logic)

### 9.1 Base formula (`engines/base_formula/`)

**Purpose:** Turn INCI list + light product text into a **`BaseFormulaRecord`** (hydration state, continuous phase, fragrance/alcohol levels, comedogenic/fungal-acne hints, texture, finish).

**Pipeline (package `__init__.py`):**

- `resolve_runtime_context` — YAML-driven matrices loaded via `matrices.py` / `context.py`.
- `derive_base_formula_record` — `derive.py` heuristics.
- `score_base_formula` — `score.py` weighted axes (texture, carrier, fragrance, alcohol, optional finish).
- `apply_overrides` — `overrides.py` adjusts scores from record + flags.

YAML configs live under `engines/base_formula/configs/` (e.g. `texture_x_skin.yaml`, `fragrance_x_sensitivity.yaml`).

### 9.2 Profile match (`engines/profile_match_impl.py`)

**Exports** (re-exported from `engines/profile_match.py`):

- `evaluate_safety` — rule-based triggers and overall severity.
- `evaluate_suitability` — concerns, benefits, declared skin types, product signals, **`RuntimeContext`**, **`BaseFormulaRecord`** → score, band, breakdown, unmet lists.
- `evaluate_observations` — structured bullet points for tiles / UI.
- `skin_type_match`, `score_to_band` — helpers.

This engine is **deterministic**; Claude only formats **tiles**, not the numeric score.

---

## 10. Tile generation (`services/tile_content_flow.py` + `generation/`)

- **`generate_tiles_with_fallback`** wraps **`generate_tile_content`** (implementation in `generation/tile_content_impl.py`).
- On **`TileGenerationError`** or any unexpected error → **`build_fallback_tiles`** so the API still returns something.
- **`LL2_TILE_ANTHROPIC_MODEL`** env can override the model **only** for analyze-product LL2 tiles.

---

## 11. Supporting utilities

| Module | Role |
|--------|------|
| `text_extract.py` | Parse first JSON object, bracket arrays from model output |
| `escape_regex.py` | Safer regex for ingredient name matching |
| `aggregations.py` | Mongo pipelines for ingredient detail |
| `core/constants.py` | e.g. daily scan cap constant |
| `core/errors.py` | `ScannerApiError` + envelope `to_body()` |

---

## 12. When things go wrong (practical debugging)

### 12.1 Label Looker “not there”

- Check startup logs for **`Label Looker: skipped`** → fix **`SKIN_BB_BASE_URL`**, **`MONGODB_URI`**, **`ANTHROPIC_API_KEY`**.
- Or **`Warning: Label Looker not installed`** → unexpected import/runtime error during `install_label_looker`.

### 12.2 401 / 403 on scanner or match routes

- Missing **`Authorization: Bearer ...`** header.
- App token invalid → fallback SSO invalid → combined **401**.
- Panel routes: wrong token or missing **`scan-overview`** permission → **403**.

### 12.3 500 “Scanner auth is not configured”

- **`SKIN_BB_CLIENT_SECRET`** empty while using **legacy SSO** routes.

### 12.4 429 scan limit

- Daily scans for `userProfileUrl` hit **`totalScanIngedientPerDay`** (`core/constants.py`).

### 12.5 400 validation

- Missing **`scanId`** on analyze-product.
- Invalid ObjectId.
- Match My Profile: missing **`product_id`**, profile fields, or **`desiredBenefits`** when not inferable — see **`errors`** array in response.

### 12.6 500 on analysis with generic message

- Claude returned non-JSON or malformed JSON → `extract_first_json_object` / normalize fails; scan gets **`ingredientAnalysisError`**.

### 12.7 Mongo / network

- Timeouts from Motor → often surface as 500 with connection errors; check URI, IP allowlist, and `serverSelectionTimeoutMS` in `db.py`.

### 12.8 Local development

- **`public/product-scan-images`** is under **process cwd** (`os.getcwd()`), not necessarily the repo root — if you start Uvicorn from another directory, files may land somewhere unexpected.

---

## 13. Suggested reading order in the repo

1. `app/label_looker/bootstrap.py` — what gets registered.
2. `app/label_looker/modules/product_analysis/routes.py` — API map.
3. `app/label_looker/modules/product_analysis/scan_service_impl.py` — image flow.
4. `app/label_looker/modules/product_analysis/analysis_service_impl.py` — analysis + validation + user history (large file; use outline in section 8).
5. `app/label_looker/modules/match_my_profile/service_impl.py` — match flow.
6. `app/label_looker/engines/base_formula/` then `engines/profile_match_impl.py`.
7. `app/label_looker/core/deps_auth.py`, `core/settings.py`.

---

## 14. Next step: code review with you

Once this mental model matches what you expect from the product:

1. Pick one vertical (e.g. **image → analyze** or **match score only**).
2. Trace that path in the files above with breakpoints or logs.
3. For any **specific error** (status code + response JSON + route), share that payload — the handler and the raise site can then be matched quickly.

If you paste the **exact error message or response body** you are seeing, the next pass can name the **line** that raises it and what input to change.
