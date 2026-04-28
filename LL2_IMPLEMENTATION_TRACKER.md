# LabelLooker 2.0 Implementation Tracker

This tracker is the execution bridge between the LL2.0 master specification and current implementation reality.

## Goal

Ship the highest-value, lowest-risk LL2.0 capabilities first, while explicitly documenting deferred scope that will be implemented later.

## Working Model

- Build what is immediately feasible in current architecture.
- Avoid blocking on external dependencies where possible.
- For anything deferred, document:
  - why it is deferred,
  - what dependency is missing,
  - what unlocks it later.

---

## Current Baseline (Already Present)

- LabelLooker module and routes under `app/label_looker`.
- Claude-backed analysis and LL2 tile generation support.
- Basic scan persistence, history retrieval, and feedback write path.
- Token verification integration with upstream SkinBB auth endpoints.
- LL2 endpoints now live under `/ll2/*` and `/api/v1/ll2/*`:
  - `POST /score`
  - `POST /scan/{scan_id}/feedback`
  - `GET /profile`
  - `PATCH /profile`
- Deterministic LL2 MVP scoring now wired:
  - Safety severity (`block`/`hard`/`soft`/`clear`) with gate behavior.
  - Suitability score with type match, weighted concerns/benefits, ceiling, and band.
  - Basic observational selector (M/U/F/C priority; top 1-2).
- Structured LL2 scan envelope now persisted in Mongo:
  - `state`, `score`, `band`, `engine_breakdown`, `generation_meta`, `tile_content`, `triggered_obs`, normalized `feedback`.

---

## Phase A - Do Now (Easy / High ROI)

## A1. LL2 API surface (compatible-first)

**Status:** Implemented (v1 adapter + deterministic payload)  
**Priority:** P0

Implemented LL2-named endpoints (backed by current Mongo + service layer):

- `POST /ll2/score`
- `POST /ll2/scan/:scan_id/feedback`
- `GET /ll2/profile`
- `PATCH /ll2/profile`

**Why now:** Gives frontend/API contract stability quickly.

---

## A2. Deterministic Suitability Engine MVP

**Status:** Implemented (MVP)  
**Priority:** P0

Implemented deterministic scoring core:

- Type match with EXACT/ADJ/OPP.
- Weighted score composition (type/concerns/benefits/baseline).
- Ceiling rule: `final = min(raw_score, type_ceiling)`.
- Banding: Great / Good / Low.

**Why now:** Core product trust depends on deterministic scoring.

---

## A3. Safety Engine MVP (Fail-fast gates)

**Status:** Implemented (MVP ruleset)  
**Priority:** P0

Implemented initial safety checks with severity output:

- Severity outcomes: `block`, `hard`, `soft`, `clear`.
- Gate behavior for `block` and `hard`.
- Carry `soft` signal into tile context.

**Why now:** Safety must run before suitability for correct user outcomes.

---

## A4. Structured scan log envelope (Mongo-first)

**Status:** Implemented (v1 envelope), needs field parity polish  
**Priority:** P1

Current scan write payload includes LL2 fields:

- `score`, `band`, `state`
- `engine_breakdown`
- `generation_meta`
- `post_scan_action`
- normalized `feedback`

**Why now:** Enables observability and iterative tuning immediately.

---

## A5. Post-scan CTA decision payload

**Status:** Implemented (band-based)  
**Priority:** P1

Deterministic CTA payload by band is now returned:

- Great/Good -> add-to-cart oriented CTA
- Low -> explore better matches
- Gate -> safer alternatives

**Why now:** Closes product loop between score and user action.

---

## Phase B - Do Soon (Moderate Effort)

## B1. Observational Engine (M/U/F/C priority model)

**Status:** Implemented (MVP); needs DSL + library-backed rules  
**Priority:** P1

Implemented top 1-2 selection with family priority and band-aware amplification.
Still pending: config/DB-backed `trigger_config` DSL and editorial authoring workflow.

---

## B2. Credits Ledger (without full payment automation)

**Status:** Planned  
**Priority:** P1

Implement:

- `free_used/free_limit`
- `paid_remaining`
- transactional decrement logic

Keep purchase top-up initially controllable via internal/admin path if payment integration is not ready.

---

## B3. Generation reliability ladder

**Status:** Partial  
**Priority:** P1

Current: Claude primary + template fallback metadata.
Pending: explicit multi-step retry ladder (primary -> shorter prompt -> fallback model -> template).

---

## Phase C - Deferred (Not Immediate)

## C1. WhatsApp OTP-native auth inside LL2 service

**Status:** Deferred  
**Reason:** Current platform already relies on upstream token verification endpoints; duplicating auth in LL2 now increases risk.
**Later unlock:** Dedicated LL2 auth boundary decision + WhatsApp provider lifecycle ownership.

---

## C2. Full payment integration (`₹99 for 10`) with Razorpay webhook lifecycle

**Status:** Deferred  
**Reason:** Requires payment order lifecycle, webhook idempotency, reconciliation, and support tooling.
**Later unlock:** Stable credits ledger + webhook infra readiness.

---

## C3. Full Postgres migration to exact spec schema

**Status:** Deferred  
**Reason:** Current system is Mongo-backed; immediate migration is high-risk for ongoing flows.
**Later unlock:** Migration plan, dual-write window, and data backfill strategy.

---

## C4. Long-horizon DPDP automation (progressive anonymization jobs)

**Status:** Deferred  
**Reason:** Requires policy alignment, legal signoff, and production retention workflow.
**Later unlock:** Compliance sprint with scheduled data lifecycle jobs.

---

## Execution Rules (Team Agreement)

- No large-bang rewrites.
- Every new LL2 feature ships behind additive routes and backward-compatible payloads.
- Every deferred item stays documented with reason and unlock condition.
- Update this file at the end of each implementation PR.

---

## Immediate Next Build Slice

1. Tighten response field parity against master/backend guide contracts (naming + optional blocks).
2. Move deterministic engines into dedicated modules (`app/engines/*`) for cleaner testing and versioning.
3. Add pytest runtime to environment and run LL2 unit tests in CI.
4. Add credits ledger and deterministic 402 responses aligned with spec economics.

