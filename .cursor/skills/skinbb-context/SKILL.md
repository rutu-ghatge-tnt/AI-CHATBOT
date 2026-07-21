---
name: skinbb-context
description: >-
  SkinBB multi-repo workspace map, write permissions, frontend component reuse rules,
  and expert edge-case-proof coding standards. Use when working on SkinBB, skinbb,
  Skinbb_Web_Industry, skinbb-main-website, skinbb-main-backend, AI-Tools Python backend,
  admin panel, or when the user mentions website / python backend / node backend /
  admin frontend / frontend components for SkinBB.
---

# SkinBB Context

Apply this skill whenever the task touches SkinBB products, repos, or frontends.

## Repo map (absolute paths)

| Surface | Path | Agent access |
|---------|------|--------------|
| Website | `D:\skinbb-main-website` | Read + write |
| Python backend | `D:\AI-Tools` | Read + write |
| Node backend | `D:\skinbb-main-backend` | **Read only — never write, edit, create, or delete files** |
| Admin panel frontend | `D:\Skinbb_Web_Industry` | Read + write |

### Path rules

1. Open and edit only the repo that matches the task surface above.
2. Cross-repo work: read from other repos for context; write only in the allowed writeable repo for that surface.
3. **Node backend hard rule**: `D:\skinbb-main-backend` is reference-only. Do not modify it. If a change is required there, describe the needed change for the user instead of applying it.
4. Prefer absolute Windows paths when referencing these roots in tools and commands.

## Frontend rules

1. **Reuse first**: Always use existing components, hooks, utilities, tokens, and layout patterns from the target frontend repo unless the user explicitly asks to replicate an exact theme/design from a given reference.
2. **Exact theme exception**: Only when the user says to match a reference design/theme exactly — then mirror that visual system (colors, typography, spacing, motion) while still preferring existing primitives where they fit.
3. Before inventing a new component: search the target repo for an equivalent pattern and extend or compose it.
4. Match local conventions (folder structure, naming, state, styling approach). Do not introduce a parallel design system.

## Coding standard (expert, edge-case proof)

Write production-grade code. Prefer correctness and clarity over cleverness.

### Required habits

- Validate inputs at boundaries (API handlers, form submit, file/upload, env, query params).
- Handle empty, null/undefined, missing keys, wrong types, and partial payloads explicitly.
- Fail safely: clear errors, no silent swallow; no leaking secrets in logs or responses.
- Idempotent writes where retries are possible; avoid double-submit / race hazards.
- Timezones and dates: be explicit (prefer UTC at storage/API boundaries).
- AuthZ: check permission on every mutating path; never trust client-only flags.
- Concurrency: guard shared state; use transactions or optimistic locking where data integrity matters.
- Resources: close files/connections; cancel timers/subscriptions; avoid leaks.
- Match existing project patterns (error types, logging, API shape, tests) before inventing new ones.

### Do not

- Leave TODOs for edge cases that are easy to handle now.
- Widen types or cast away null checks to silence the typechecker.
- Write to `D:\skinbb-main-backend`.
- Rebuild UI from scratch when an existing component already covers the need.

## Task routing quick check

Before coding, answer:

1. Which surface is this? → pick the path from the table.
2. Am I about to write in node backend? → stop; read only.
3. Is this frontend? → search existing components first (unless exact-theme instruction).
4. What edge cases apply at this boundary? → handle them in the change.

## Extra detail

- Deeper coding checklist: [coding-standards.md](coding-standards.md)
