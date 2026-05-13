# Frontend ↔ Label Looker API — verification prompt

Canonical path reference: **`docs/LABEL_LOOKER_API_FRONTEND.md`**.

Copy everything below the line into your AI assistant or QA ticket so the **frontend** is checked against the **Python API** contracts.

---

You are verifying a client app (web or mobile) against the SkinBB FastAPI **Label Looker** backend.

## Base assumptions

- API may be mounted under **`/scanner`** (legacy) and/or **`/api/v1/scanner`** (v1). Paths below are **suffixes** — prepend the correct base the app uses.
- **Match My Profile** is always under **`/api/v1/match-my-profile`** (not under `/scanner`).
- Authenticated calls send **`Authorization: Bearer <token>`**.
- Successful JSON envelope: **`{ "success": true, "data": { ... }, "message": "...", "statusCode": 200 }`**.
- Errors from `ScannerApiError`: **`{ "success": false, "status": "error", "statusCode": N, "message": "..." }`** or **`errors`** array instead of `message` on some 400s.

## Checklist (execute in order)

### A. Bootstrap / env

1. Confirm the app’s API base URL matches where Label Looker is installed (same host as FastAPI `install_label_looker`).
2. If all scanner routes 404, confirm server logs do not show `Label Looker: skipped` (missing `SKIN_BB_BASE_URL`, `MONGODB_URI`, or `ANTHROPIC_API_KEY`).

### B. Auth

3. **Legacy `/scanner`**: confirm token works with SSO path; if 500 “Scanner auth is not configured”, backend needs `SKIN_BB_CLIENT_SECRET`.
4. **`/api/v1/scanner`**: confirm the access token succeeds on Node **`GET {SKIN_BB_BASE_URL}/api/v1/users/user-details`** (override path with **`SKIN_BB_USER_DETAILS_PATH`** if your stack differs). Python tries that first, then legacy SSO **`verify-token`** + HS256 if user-details returns 401/403.
5. On 401, confirm client sends Bearer header and does not strip it on redirects.

### C. Image scan flow

6. **POST** `.../image-conversion` with multipart file `image` (JPEG/PNG, &lt; 5 MB).
7. Parse **`data.scanDetail`** (Mongo ObjectId string) — this is the **`scanId`** for the next step (note: field name is **`scanDetail`**, not `scanId`).
8. Parse **`data.ingredientNames`** (string array).
9. Confirm image URL if shown: **`GET /product-scan-images/<basename>`** from `scanImageUrl` pattern returned elsewhere or from upload response conventions.
10. After daily limit: expect **429** with friendly copy; confirm UI handles it.

### D. Ingredient analysis (scan-based)

11. **POST** `.../analyze-product` with JSON body including **`scanId`** (same value as `scanDetail` from step 7).
12. Optional: **`productId`**, **`personalizedMatching`**: if true, user must be logged in or API returns **401**.
13. Response **`data`**: must include **`scanId`**, **`analyticDetail`** (object), **`ingredients`** (array). If user logged in, may include **`profileValidation`** — confirm UI shows prompts when present.
14. **`analyticDetail`**: confirm UI reads keys aligned with backend normalizer (`opinion`, `keyIngredients`, `benefitsOffered`, `importantConsiderations`, `productUsageTips`, `ingredientCategorization`, optional `profileMatchInsights` when personalized).
15. If **`analyticDetail.ll2TileContent`** exists, confirm tiles render; if missing, acceptable (fallback or inputs not built).
16. **Typo compatibility**: request body may use **`langauge`** (legacy spelling) — confirm client matches backend.

### E. Text analysis (no image)

17. **POST** `.../analyze-product/text` with **`ingredients`** array and/or **`ingredientsText`**, optional auth.
18. Same envelope expectations as analysis where applicable.

### F. Ingredient detail

19. **GET** `.../ingredient?name=<url-encoded name>` with auth — **`data`** shape matches ingredient detail screen.

### G. Quota and feedback

20. **GET** `.../scan-left` — **`data.scanLeft`**, **`data.totalScanPerDay`**.
21. **PUT** `.../feedback` — body matches backend `put_feedback` expectations; success envelope.

### H. User history

22. **GET** `.../user/analysis?skip=0&limit=20` — list; **GET** `.../user/analysis/{scan_id}` — detail; confirm **403/404** when accessing another user’s scan.

### I. Match My Profile

23. **POST** `/api/v1/match-my-profile/score` with **`productId`** (or `product_id`), profile fields or **`desiredBenefits`**, optional **`scanId`** in body to **re-fetch** an existing match.
24. On **400** with **`errors`** array, confirm UI surfaces missing fields (`profile` vs `request`).
25. On **402** `insufficient_credits`, confirm paywall or messaging.
26. Response includes both **snake_case** and **camelCase** duplicates for many fields (`scanId`/`scan_id`, `bandLabel`/`band_label`, etc.) — client should pick **one** convention project-wide and ignore the other to avoid double-binding.
27. **`triggeredObservations`**: must be a **list of objects** (with `id`, copy fields as returned by engine) on first score **and** when re-fetching the same scan by `scanId` (hydration path). If re-fetch returns only string ids, backend contract is broken — flag it.
28. **Gate** state: confirm **`gate`**, **`gate_severity`**, **`override_allowed`** UI when `state === "gate"`.
29. **PATCH** `/api/v1/match-my-profile/profile` — nested **`category_profiles`** / **`categoryProfiles`** and **`safety`** — confirm PATCH body matches what **GET** `/profile` returns.

### J. Admin (panel only)

30. Panel routes under `/scanner` with panel JWT — list/detail/analytics; confirm **403** without `scan-overview` permission.

## Report format

For each section A–J, report **Pass / Fail**, HTTP status, and **one sample `data` snippet** (redact tokens). List any field name mismatches between client and server.

---

## One-line smoke

`image-conversion` → take `scanDetail` → `analyze-product` with that `scanId` → render `analyticDetail` → optional `match-my-profile/score` with same `productId` if PDP-linked.
