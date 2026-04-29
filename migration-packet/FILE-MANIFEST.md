# Files to copy or @-reference for Python migration

Paths are relative to the **Node repo root** (`skinbb-productdb-backend`).

## Routes

- `src/routes/productIngredientScan.js`
- `src/routes/v1/productIngredientScan.routes.js`
- `src/routes/v1.routes.js`
- `src/app.js` (static files, CORS, multer, route prefixes)

## Controller (core logic + aggregations)

- `src/controllers/productIngredientScan.controller.js`

## Middleware

- `src/middlewares/productScanMulter.middleware.js`
- `src/middlewares/scannerAuthSSO.middleware.js`
- `src/middlewares/authenticateAppUser.middleware.js`
- `src/middlewares/panelAuth.middleware.js`
- `src/middlewares/authorizeUser.middleware.js`

## Models (schemas + indexes + any hooks)

- `src/models/scanAnalysis.model.js`
- `src/models/ingredient.model.js`
- `src/models/article.model.js`
- `src/models/category.model.js`
- `src/models/skinBenefit.model.js`
- `src/models/naturality.model.js`
- `src/models/user.model.js`
- `src/models/scanDetail.model.js` (legacy / unused routes; still referenced in controller)

## Config / constants / utils

- `src/anthropic-config.js`
- `src/constants.js`
- `src/utils/ApiResponse.js`
- `src/utils/ApiError.js`
- `src/utils/escapeRegex.js`
- `src/utils/asyncHandler.js` (pattern for middleware)

## DB bootstrap (for env + connection pattern)

- `src/db/index.js` (if present)
- `src/index.js`

## Optional

- `package.json` (dependency list for parity notes)
