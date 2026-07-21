# SkinBB coding standards (detail)

Use when implementing non-trivial features, APIs, or UI flows. Keep changes scoped to the active writeable repo.

## Boundary checklist

At every external boundary (HTTP, queue, file, DB, third-party, user input):

- [ ] Schema/type validation before business logic
- [ ] AuthN present; AuthZ checked for the resource
- [ ] Rate / size limits where abuse is possible
- [ ] Structured error responses; no stack traces to clients in prod
- [ ] Sensitive fields redacted in logs

## Edge cases to cover by default

| Area | Cover |
|------|--------|
| Collections | empty list, single item, large N, duplicates |
| Strings | empty, whitespace, unicode, max length |
| Numbers | zero, negative, NaN/Infinity (reject), overflow |
| IDs | missing, malformed, wrong tenant, soft-deleted |
| Time | DST, UTC vs local, expired tokens, clock skew |
| Network | timeout, 4xx/5xx, retry with backoff, partial success |
| Concurrency | double click, parallel tab, stale read then write |
| Files | wrong MIME, oversized, empty, path traversal |
| Permissions | unauthenticated, wrong role, cross-tenant access |

## Python backend (`D:\AI-Tools`)

- Follow existing module layout, error helpers, and API conventions in the touched package.
- Prefer explicit exceptions and typed returns over bare `except` / loose dicts.
- DB: parameterize queries; transactions for multi-step writes; handle integrity errors.
- Env/config: fail fast on missing required secrets; never hardcode credentials.

## Website / admin frontend

- Website: `D:\skinbb-main-website`
- Admin: `D:\Skinbb_Web_Industry`
- Compose existing components; do not fork styles unless exact-theme was requested.
- Loading / empty / error / success states for every async UI path.
- Disable or debounce destructive / submit actions while in flight.
- Accessible labels, keyboard paths, and focus for interactive controls.

## Node backend (`D:\skinbb-main-backend`)

- Read for contracts, types, routes, and behavior only.
- Propose diffs or patch notes in chat; do not apply file changes.

## Review before done

- [ ] Correct repo + write permission respected
- [ ] Existing patterns/components reused
- [ ] Edge cases at the changed boundary handled
- [ ] No secrets committed; no unnecessary new deps
- [ ] Behavior matches nearby code style
