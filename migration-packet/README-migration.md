# Label Looker (`productIngredientScan`) — Node → Python migration packet

Use this document as the **single source of truth** for Cursor (or any engineer) porting the feature **with behavior parity**. Do not change API shapes, field names, or business rules until parity is proven.

**Source repo:** `skinbb-productdb-backend` (this Node/Fastify service).

---

## 1. Scope: what “entire feature” means

### Public / app scanner (must match)

| Method | Path (legacy) | Path (v1 app) | Auth |
|--------|----------------|-----------------|------|
| `POST` | `/scanner/image-conversion` | `/api/v1/scanner/image-conversion` | Legacy: `scannerAuthSSO`. V1: `authenticateAppUser`. |
| `POST` | `/scanner/analyze-product` | `/api/v1/scanner/analyze-product` | Same split. **Node legacy** used `/ingredients-analysis`; Python exposes only `analyze-product`. |
| `POST` | `/scanner/analyze-product/text` | `/api/v1/scanner/analyze-product/text` | Optional auth (`authenticate_any_user_optional`). Node may have used `text-ingredients-analysis`; Python only mounts `analyze-product/text`. |
| `POST` | `/scanner/ingredient` | `/api/v1/scanner/ingredient` | Same split. **Query:** `name` (not body). |
| `GET` | `/scanner/scan-left` | `/api/v1/scanner/scan-left` | Same split. |

### Admin / panel analytics (legacy only — not registered under v1)

Mounted under `/scanner` with panel auth + permission where noted:

| Method | Path | Middleware |
|--------|------|------------|
| `GET` | `/scanner/analysis/list` | `verifyJWTForPanelAuth` + `authorizeUser('scan-overview', 'view')` |
| `GET` | `/scanner/analysis/:id` | same |
| `GET` | `/scanner/analytics` | `verifyJWTForPanelAuth` only |
| `GET` | `/scanner/user/total-scan` | panel + `authorizeUser('scan-overview', 'view')` |
| `GET` | `/scanner/rating-count` | panel + `authorizeUser('scan-overview', 'view')` |

**Routing references:** `src/routes/productIngredientScan.js`, `src/routes/v1/productIngredientScan.routes.js`, `src/routes/v1.routes.js` (prefix `/scanner` under `/api/v1`), `src/app.js` (legacy `/scanner`).

---

## 2. Success / error response envelopes (must match)

### Success (`ApiResponse`)

HTTP status is the same as `statusCode` in the body (typically 200).

```json
{
  "data": { },
  "statusCode": 200,
  "message": "Success",
  "success": true
}
```

Implementation: `src/utils/ApiResponse.js`.

### Error (`errorHandler`)

```json
{
  "status": "error",
  "success": false,
  "statusCode": 400,
  "message": "…",
  "stack": "…"
}
```

If `errors` array is present on the error object, `message` is omitted and `errors` is included instead.

Implementation: `src/utils/ApiError.js`.

---

## 3. Environment variables

| Variable | Used for |
|----------|-----------|
| `ANTHROPIC_API_KEY` | Anthropic client (`src/anthropic-config.js`) |
| `ANTHROPIC_MODEL` | Passed to `anthropic.messages.create` |
| `SKIN_BB_BASE_URL` | Base URL for SkinBB user/auth HTTP calls |
| `SKIN_BB_CLIENT_SECRET` | **Legacy scanner only:** JWT verify after `verify-token` (`scannerAuthSSO`) |
| `MONGODB_URI` | Mongo connection |
| `MONGODB_DATABASE` | DB name (as used by this app’s DB bootstrap) |
| `SERVER_URL` | Used elsewhere in aggregations / image URLs in ingredient detail flow (see controller) |

Optional app runtime: `HOST`, `PORT` (not scanner-specific).

---

## 4. External HTTP dependencies (auth)

All use `Authorization: Bearer <token>` on the outbound request.

| Middleware | Outbound call |
|------------|----------------|
| `scannerAuthSSO` | `GET {SKIN_BB_BASE_URL}/api/v1/users/verify-token` → then `jwt.verify(token, SKIN_BB_CLIENT_SECRET)` |
| `authenticateAppUser` | `GET {SKIN_BB_BASE_URL}/api/v1/users/verify-app-token` — response shape: `{ data: { user, role } }`; handler sets `req.user = data.user`, `req.role = data.role` |
| `verifyJWTForPanelAuth` | `GET {SKIN_BB_BASE_URL}/api/v1/users/verify-panel-token` — sets `req.user`, `req.role`, `req.permissions` |

Files: `src/middlewares/scannerAuthSSO.middleware.js`, `src/middlewares/authenticateAppUser.middleware.js`, `src/middlewares/panelAuth.middleware.js`.

### Legacy scanner user shape (used by controller)

`scanImageToText` / quota logic expects at least:

- `req.user.profileUrl`
- `req.user.firstName`, `req.user.lastName`
- `req.user._id` or `req.user.id`

### Panel permission check

`authorizeUser('scan-overview', 'view')` requires `req.role` and `req.permissions` where some entry has `permission.page === page` and `permission.action` includes `action`.

File: `src/middlewares/authorizeUser.middleware.js`.

---

## 5. Multipart upload (`image-conversion`)

- **Field name:** `image` (single file).
- **Max size:** 5 MiB.
- **Allowed MIME types:** see `src/middlewares/productScanMulter.middleware.js` (jpeg, png, gif, webp, bmp, tiff, heif/heic, svg, ico, avif, dng, etc.).
- **Disk directory:** `./public/product-scan-images` (relative to process cwd).
- **Filename pattern:** sanitized basename + timestamp/random + extension from `mimetype` (see multer storage in same file).

Static files: `src/app.js` registers `@fastify/static` with `root: ../public`, `prefix: '/'` — so uploaded files are reachable at paths like `/product-scan-images/<filename>` when clients use `SERVER_URL` + path (verify how mobile/web builds URLs).

---

## 6. Anthropic usage

Client: `src/anthropic-config.js` (`@anthropic-ai/sdk`).

### `scanImageToText`

- `anthropic.messages.create` with `model: process.env.ANTHROPIC_MODEL`, `max_tokens: 2000`.
- One user message: image block (`base64` + `media_type` from upload) + fixed text prompt asking for ingredient list in array form.
- Response text: regex `\[\s*([\s\S]*?)\s*\]` to extract array; split on `,`; strip quotes; filter empty.

### `ingredientAnalysis` / `promptAITogetIngredientDetails`

- Text-only user messages; strip markdown fences; `text.match(/\{[\s\S]*\}/)` then `JSON.parse`.
- On parse failure, Node logs and throws; `ingredientAnalysis` catches and stores `ingredientAnalysisError` and returns generic 500 message to client.

**Prompt bodies:** copy verbatim from `src/controllers/productIngredientScan.controller.js` (`ingredientAnalysis`, `promptAITogetIngredientDetails`).

---

## 7. Business rules (must match)

### Daily scan quota

Constant: `totalScanIngedientPerDay = 20` in `src/constants.js`.

Count documents in `ScanAnalysis` where:

- `createdAt` in **[start of local calendar day, now)** (midnight via `setHours(0,0,0,0)` on server local time),
- `userProfileUrl` equals `req.user.profileUrl`,
- `scanImageError` is **`null`** (counts only successful scans).

If count ≥ 20 before a new scan: **429** with message:  
`You've used up your scans for today. Check back later to explore more with Label Looker!`

On create, `scansLeft` is set to `max(0, 20 - count - 1)` (see `scanImageToText`).

### `ingredientAnalysis` body

- **Required:** `scanId`.
- **Optional:** `ingredients` (array). If missing/empty, load `extractedIngredients` from `ScanAnalysis` by `scanId`.
- **Also read:** `productFor`, `specificType`, `mainBenefit`, `langauge` (typo preserved — default `'English'`).

On any error after validation, DB update sets `ingredientAnalysisError` to error message; client always gets **500** with message:  
`There's no data available right now. Please try again later.`

### `getIngredientDetailByNameForScanner`

- **Query param:** `name` (trimmed; leading/trailing non-alphanumeric stripped).
- Slash handling and regex branch logic: copy from controller.
- If no ingredient resolved: **create** `Ingredient` with `approved: true`, `isLocked: true`, `source: "Cluade-AI"` (typo preserved).
- Resolve `parentIngredientId` for article lookup.
- If no approved `Article`: call AI (`promptAITogetIngredientDetails`) then `createArticleByAI`.
- `createArticleByAI` requires a `User` with `role: "ai-assistant"` for `authorId` / `reviewerId`.

### `putAFeedBack`

Body: `{ scanId, rating?, feedback? }`.  
`rating` enum on model: `"good" | "okay" | "bad"`.

### `numberOfScanLeft`

Response `data`:

```json
{
  "totalScanPerDay": 20,
  "scanLeft": "<number; same formula as Node>"
}
```

Node uses `scanLeft: totalScanIngedientPerDay - count` (not clamped with `Math.max` in the payload — match Node if you want byte-for-byte parity).

---

## 8. MongoDB / Mongoose models touched

Implement against the **same database** (recommended for migration) so collection names and indexes stay identical.

| Logical entity | Mongoose model / file |
|----------------|------------------------|
| Scan records | `Scan_Analysis` → `src/models/scanAnalysis.model.js` |
| Ingredients | `Ingredient` → `src/models/ingredient.model.js` |
| Articles | `Article` → `src/models/article.model.js` |
| Categories | `Category` → `src/models/category.model.js` |
| Skin benefits | `Skin_Benefit` / `SkinBenefit` → `src/models/skinBenefit.model.js` |
| Naturality | `Naturality` → `src/models/naturality.model.js` |
| Users (AI author) | `User` → `src/models/user.model.js` |

**Important:** `Ingredient` has a **partial unique index** on `name` when `isDeleted: false` (`ingredient_name_partial_index`). Preserve in Python migrations or accept duplicate-key behavior differences.

**Aggregation:** `getIngredientDetails` and admin list/analytics handlers are large pipelines in `src/controllers/productIngredientScan.controller.js` — port as literal pipeline stages for parity.

---

## 9. Endpoint contracts (response `data` shapes)

### `POST …/image-conversion`

**Success `data`:**

```json
{
  "scanDetail": "<ObjectId string>",
  "ingredientNames": ["…"]
}
```

Message: `"Ingredient list"`.

On failure after `ScanAnalysis` create, document is updated with `scanImageError: <message>`.

### `POST …/analyze-product`

(Former Node path: `POST …/ingredients-analysis` — not registered on this FastAPI app; call `analyze-product` only.)

**Success `data`:**

```json
{
  "scanId": "<same as body>",
  "analyticDetail": { },
  "ingredients": [ ]
}
```

### `POST …/ingredient?name=…`

**Success `data`:**

```json
{
  "ingredientDetail": [ ]
}
```

(Array from aggregation; empty → 404 path in Node.)

### `PUT …/feedback`

**Success `data`:** `{}`  
Message: `"Feedback added successfully"`.

### `GET …/scan-left`

**Success `data`:** `{ "totalScanPerDay": 20, "scanLeft": <number> }`

---

## 10. Suggested Python stack (equivalents)

| Node | Python |
|------|--------|
| Fastify | FastAPI |
| fastify-multer | `python-multipart` + manual size/MIME checks |
| mongoose | Motor / PyMongo |
| axios | httpx |
| jsonwebtoken | PyJWT |
| @anthropic-ai/sdk | `anthropic` (official Python SDK) |
| sanitize-html (Article fields) | bleach (if you port article writes) |

---

## 11. Implementation order (for Cursor)

1. FastAPI app + global exception handler matching `ApiResponse` / error JSON.
2. Config + env validation.
3. Mongo connection (same URI/DB).
4. Auth dependencies (`verify-app-token`, `verify-token`+JWT, `verify-panel-token`) + `authorizeUser` equivalent.
5. Multipart `image-conversion` + disk save + Anthropic image path + regex parse + `ScanAnalysis` writes.
6. `analyze-product` + JSON cleanup + `ScanAnalysis` update.
7. `ingredient` query handler + AI article path + `getIngredientDetails` aggregation.
8. `feedback`, `scan-left`.
9. Admin routes + aggregations.
10. Parity tests: same requests against Node vs Python, diff JSON (allow ordering where unspecified).

---

## 12. “Do not change” checklist

- [ ] Route paths match the Python surface (canonical: `analyze-product`, `analyze-product/text`; legacy Node `ingredients-analysis` aliases are not mounted here).
- [ ] Request field names unchanged (`image`, body keys, query `name`, typo `langauge`).
- [ ] Response envelope (`ApiResponse` / error handler) unchanged.
- [ ] Mongo field names and enum values unchanged (`rating`, `source: "Cluade-AI"`, article `status: "approved"`, etc.).
- [ ] Quota math and `scanImageError: null` filter unchanged.
- [ ] Anthropic prompts and post-processing (regex / JSON extraction) unchanged.

---

## 13. Files to attach or copy into the Python repo

See **`FILE-MANIFEST.md`** in this folder for a path list. Minimum: controller + all middleware + models listed + `anthropic-config.js` + `constants.js` + `ApiResponse.js` + `ApiError.js` + `escapeRegex.js` + route files + `app.js` (mount/static behavior).

When opening the Python project in Cursor, **@ mention** this `README-migration.md` and the copied Node files (or this whole `migration-packet` folder) in the first prompt.
