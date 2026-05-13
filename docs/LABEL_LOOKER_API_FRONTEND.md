# Label Looker — frontend API reference (product analysis + match my profile)

This document is the **integration contract** for clients calling the SkinBB FastAPI **Label Looker** routers. Use it with OpenAPI (`/docs`) for full JSON Schema; this file focuses on **paths, auth, envelopes, and field semantics** so QA and frontend can verify behavior without spelunking Python.

**Related:** architecture overview in `LABEL_LOOKER_ARCHITECTURE.md`, checklist prompt in `LABEL_LOOKER_FRONTEND_VERIFICATION_PROMPT.md`.

---

## 1. Base URLs and prefixes

| Prefix | When to use | Auth |
|--------|----------------|------|
| **`/api/v1/scanner`** | Preferred app integration | V1: `authenticate_any_user` (Node user-details first, legacy SSO fallback). |
| **`/scanner`** | Legacy compatibility | Legacy SSO (`verify-token` + HS256) only on these routes. |
| **`/api/v1/match-my-profile`** | Match My Profile only | Same as v1 scanner: **`authenticate_any_user`**. |

Every path below is written **relative to one of these prefixes** (for example full URL: `https://<api-host>/api/v1/scanner/image-conversion`).

**Static uploads:** scanned images are served from **`GET /product-scan-images/<filename>`** (basename returned in scan flows).

If all Label Looker routes **404** and logs show `Label Looker: skipped`, required env is missing (`SKIN_BB_BASE_URL`, Mongo URI, Anthropic key) — see `core/settings.py`.

---

## 2. Auth headers (v1 app + match my profile)

Send the **same access token** that works on Node:

- **`GET {SKIN_BB_BASE_URL}{SKIN_BB_USER_DETAILS_PATH}`**  
  Default path: **`/api/v1/users/user-details`** (override with env **`SKIN_BB_USER_DETAILS_PATH`** if your gateway differs).

**Accepted headers** (first non-empty wins after normalizing `Bearer`):

- **`Authorization: Bearer <access_token>`** (recommended)
- **`access-token: <access_token>`**
- **`x-access-token: <access_token>`**

Repeated `Bearer Bearer` is stripped server-side; send a single raw JWT if in doubt.

**401** means user-details rejected the token **and** legacy SSO did not accept it either. Refresh tokens on **Node**, not Python.

**Legacy `/scanner`** (non-v1): **`Authorization: Bearer <token>`** only; validated via **`/api/v1/users/verify-token`** + JWT using **`SKIN_BB_CLIENT_SECRET`**. If that secret is missing, expect **500** `Scanner auth is not configured`.

Optional debugging: set **`LABEL_LOOKER_AUTH_DEBUG=1`** for auth request logging on the server.

---

## 3. Response envelopes

### 3.1 Success (`api_success`)

HTTP **200** (unless overridden). Body:

```json
{
  "success": true,
  "statusCode": 200,
  "message": "Success",
  "data": { }
}
```

`message` varies per route (e.g. image conversion uses `"Ingredient list"`).

### 3.2 Scanner errors (`ScannerApiError`)

HTTP status = `statusCode`. Body shape:

```json
{
  "success": false,
  "status": "error",
  "statusCode": 400,
  "message": "Human-readable message"
}
```

Some **400** responses use **`errors`** (array) **instead of** `message` for structured validation (notably match **`score`** missing inputs).

**422** validation (FastAPI) on scanner paths is wrapped similarly with `errors` listing field issues.

**401** responses omit traceback noise in `stack` even when stack traces are enabled for other errors.

---

## 4. Product analysis (scanner)

Canonical analysis endpoints (**no duplicates** on this service):

| Method | Relative path | Auth | Summary |
|--------|-----------------|------|---------|
| `POST` | **`/image-conversion`** | Required (per prefix) | Multipart image → ingredient list + creates scan row. |
| `POST` | **`/analyze-product`** | Required | Full LLM analysis for an **existing** scan (`scanId`). |
| `POST` | **`/analyze-product/text`** | Optional | Analysis from pasted text / INCI list (no prior image). |
| `GET` | **`/ingredient?name=...`** | Required | Single-ingredient detail aggregation. |
| `PUT` | **`/feedback`** | Required | Thumbs/text feedback on a scan. |
| `GET` | **`/scan-left`** | Required | Daily quota remaining. |
| `POST` | **`/profile-validation/submit`** | Required | Submit profile validation answers. |
| `POST` | **`/profile-validation/status`** | Required | Poll validation / prompt state. |
| `GET` | **`/user/analysis`** | Optional | List current user’s scans (empty list if unauthenticated). |
| `GET` | **`/user/analysis/{scan_id}`** | Optional | One scan; **404** if anonymous; **403** if not owner. |

> **Removed aliases (do not call):** `POST …/ingredients-analysis`, `POST …/text-ingredients-analysis` — use **`analyze-product`** and **`analyze-product/text`** only.

### 4.1 `POST …/image-conversion`

- **Content-Type:** `multipart/form-data`
- **Field:** `image` (file) — JPEG/PNG; size/MIME validated server-side.

**Success `data` (important names):**

| Field | Type | Notes |
|-------|------|--------|
| `scanDetail` | string | Mongo ObjectId string — use as **`scanId`** in `analyze-product`. |
| `ingredientNames` | string[] | Extracted INCI names. |

### 4.2 `POST …/analyze-product`

**Content-Type:** `application/json`

| Field | Required | Notes |
|-------|----------|--------|
| `scanId` | **Yes** | Same value as `scanDetail` from image conversion. |
| `productId` | No | When resolvable, server prefers PDP INCI list over weak LLM lists. |
| `ingredients` | No | If omitted or empty, uses scan doc `extractedIngredients`. |
| `personalizedMatching` | No | If `true`, **user must be authenticated** or **401**. |
| `specificType`, `mainBenefit` | No | Filled from product when possible. |
| `langauge` | No | **Typo is intentional** (legacy) — language hint for prompts; defaults from constants. |

**Success `data`:**

| Field | Notes |
|-------|--------|
| `scanId` | Echo of request. |
| `analyticDetail` | Structured analysis (opinion, keyIngredients, benefitsOffered, importantConsiderations, productUsageTips, ingredientCategorization, optional `profileMatchInsights`, optional `ll2TileContent` / `ll2TileContentMeta`). |
| `ingredients` | Final string list stored with analysis. |
| `profileValidation` | When user logged in: prompt payload for profile confirmation flow. |

### 4.3 `POST …/analyze-product/text`

**Content-Type:** `application/json`

| Field | Required | Notes |
|-------|----------|--------|
| `productId` | No | If set and product has INCI rows, those beat body text. |
| `ingredients` | One of | Non-empty string **array** OR use `ingredientsText`. |
| `ingredientsText` | One of | Free text; parsed into INCI list. |
| `personalizedMatching` | No | If `true`, user required — **401** if missing. |

Response shape aligns with scan-based analysis where applicable (`scanId`, `analyticDetail`, `ingredients`, `profileValidation`).

### 4.4 `GET …/ingredient?name=<inci>`

Query parameter **`name`** (URL-encoded). Returns **`data`** with ingredient detail payload from `get_ingredient_detail_response`.

### 4.5 `PUT …/feedback`

**JSON body:**

| Field | Required | Notes |
|-------|----------|--------|
| `scanId` | **Yes** | |
| `rating` | No | If set: **`good`**, **`okay`**, or **`bad`**. |
| `feedback` | No | Free text. |

Success `data`: `{}`.

### 4.6 `GET …/scan-left`

**Success `data`:** `totalScanPerDay` (e.g. **20**), `scanLeft` (remaining today for this user).

### 4.7 Profile validation

**`POST …/profile-validation/submit`** (auth required)

- **`answers`**: object, required — mode-specific validation answers.
- Optional: `productId`, `productFor`, `specificType`, `mainBenefit`, `mode` — used to resolve skincare vs haircare vs lipcare.

Returns mode, `finalized`, `finalValues`, `nextPrompt`.

**`POST …/profile-validation/status`** (auth required)

- Optional body keys as submit; optional `userId` must match caller or **403**.

Returns `missingFields`, `hasRequiredData`, `shouldPromptNow`, `prompt`, etc.

### 4.8 User analysis history

**`GET …/user/analysis?skip=0&limit=20`**

- Unauthenticated: **200** with empty list (or empty-shaped list per implementation).
- Authenticated: paginated scans for that user.

**`GET …/user/analysis/{scan_id}`**

- Requires owner; **403** / **404** as appropriate.

---

## 5. Match My Profile (`/api/v1/match-my-profile`)

All routes require **authenticated** user (same v1 auth as scanner).

| Method | Path | Summary |
|--------|------|---------|
| `POST` | **`/score`** | New score for `productId`, **or** hydrate prior result when `scanId` in body. |
| `GET` | **`/profile`** | Profile slice used for match + credits. |
| `PATCH` | **`/profile`** | Partial update of Mongo `user_details` match fields. |
| `POST` | **`/scan/{scan_id}/feedback`** | Post-score thumbs / note. |

### 5.1 `POST …/score`

**Two behaviors:**

1. **Hydrate** — body contains **`scanId`** or **`scan_id`** (non-empty string): returns stored match for that scan **without** re-scoring; **403** if not owner.
2. **New score** — body contains **`productId`** or **`product_id`** (required): runs engine, persists scan row, returns full result.

**New score — inputs:**

| Field | Required | Notes |
|-------|----------|--------|
| `productId` / `product_id` | **Yes** (unless hydrating) | PDP document id. |
| `desiredBenefits` (or `desiredBenefit`, `benefits`, `skinGoals` / `hairGoals`, `mainBenefit`) | Effectively **yes** | Must be present **on the request** for a new score (see **400** `errors` with `source: "request"` if missing). |
| `mode` | No | `skincare` / `haircare` hint; else inferred from product. |
| `pinCode` / `pin_code` | No | Climate context when supported. |
| `age`, `gender`, `skinType` / `hairType`, `skinConcerns` / `hairConcerns` | Fallback | If profile in Mongo is incomplete, body can supply; else **400** lists missing **`profile`** fields. |

**Success `data`:** large object with **both snake_case and camelCase** duplicates at top level (e.g. `scan_id` and `scanId`, `band_label` and `bandLabel`). **Pick one convention** in the client and ignore the other.

Important keys:

| Key(s) | Meaning |
|--------|---------|
| `state`, `band`, `score`, `bandLabel` | Match band and numeric score when not gated. |
| `safety`, `triggeredObservations` / `triggered_observations` | Safety engine + observation cards (list of objects with `id`, copy fields). |
| `tiles` | Claude tile copy (or gate template when `state === "gate"`). |
| `gate`, `gate_severity`, `override_allowed` | Present when safety gate applies. |
| `fullAnalysis` / `full_analysis` | Ingredients + optional `legacy_analytic_detail` from last product analysis. |
| `creditsRemaining` / `credits_remaining` | Free tier remaining (same daily pool as scanner). |

**402** — message `insufficient_credits` when daily free scans exhausted.

### 5.2 `GET …/profile`

Returns merged view: Mongo **`user_details`** plus scalar/list fallbacks from **Node user-details** (`age`, `gender`, `skinType`, concerns/goals, etc.) so empty Mongo rows still show usable defaults.

Response includes **`category_profiles`** and duplicate **`categoryProfiles`**, **`benefitsWanted`**, and **`credits`**.

### 5.3 `PATCH …/profile`

**JSON body** — all optional; only sent keys are updated:

- **`name`**, **`age`**, **`gender`**
- **`category_profiles`** or **`categoryProfiles`**: nested `{ skin: { type, concerns, benefits_wanted | benefitsWanted | skinGoals }, hair: { … } }`
- **`safety`**: `{ life_stages | lifeStages, allergies, conditions, medications }`

Returns same shape as **GET** (full profile after merge).

### 5.4 `POST …/scan/{scan_id}/feedback`

**JSON body:**

| Field | Required | Notes |
|-------|----------|--------|
| `sentiment` | **Yes** | **`up`** or **`down`**. |
| `category`, `note` | No | |
| `post_scan_action` / `postScanAction` | No | Stored on scan doc. |

---

## 6. Admin / panel (scanner prefix only)

Mounted under **`/scanner`** only (not under `/api/v1/scanner`):

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/analysis/list` | Panel JWT + scan-overview permission |
| `GET` | `/analysis/{scan_id}` | Same |
| `GET` | `/analytics` | Panel JWT |
| `GET` | `/user/total-scan` | Panel + scan-overview |
| `GET` | `/rating-count` | Panel + scan-overview |

---

## 7. Quick integration smoke (happy path)

1. `POST /api/v1/scanner/image-conversion` with `image` → read **`data.scanDetail`**.
2. `POST /api/v1/scanner/analyze-product` with `{ "scanId": "<scanDetail>", "productId": "<optional>" }` → render **`data.analyticDetail`**.
3. Optional: `POST /api/v1/match-my-profile/score` with `{ "productId": "<id>", "desiredBenefits": ["hydration"] }` → render tiles + band; store **`data.scanId`** for hydration.
4. Later: `POST /api/v1/match-my-profile/score` with `{ "scanId": "<stored>" }` → same UI without consuming a new score.

---

## 8. OpenAPI

With Label Looker installed, generate clients from FastAPI **`/docs`** or **`/openapi.json`** — tags include **Label Looker — v1 /api/v1/scanner** and **Match My Profile /api/v1/match-my-profile**.
