# LL2.0 Gap Checklist (Spec vs Current Implementation)

This checklist maps LL2.0 spec/backend-guide expectations against the current codebase status.

Status legend:
- `DONE` = implemented and wired
- `PARTIAL` = implemented in MVP form; needs hardening/parity
- `PENDING` = not yet implemented

---

## 1) API Surface

- `DONE` `POST /ll2/score`
- `DONE` `POST /ll2/scan/{scan_id}/feedback`
- `DONE` `GET /ll2/profile`
- `DONE` `PATCH /ll2/profile`
- `PENDING` `POST /ll2/auth/otp/send`
- `PENDING` `POST /ll2/auth/otp/verify`
- `PENDING` `POST /ll2/credits/purchase`
- `PENDING` `DELETE /ll2/profile`

Notes:
- Both `/ll2/*` and `/api/v1/ll2/*` are currently wired.
- Score/profile responses include snake_case + camelCase compatibility aliases.

---

## 2) Deterministic Engines

- `DONE` Suitability MVP:
  - type match (exact/adjacent/opposite)
  - weighted score composition
  - score ceiling
  - banding
- `DONE` Safety MVP:
  - severity ladder (`block`/`hard`/`soft`/`clear`)
  - gate state behavior
- `DONE` Observational MVP:
  - M/U/F/C priority model
  - band-aware amplification
  - top 1-2 selection
- `PENDING` Full rule-DSL + DB-backed observation library triggers
- `PENDING` Full dermatology-authored safety ruleset from template

---

## 3) Generation Layer

- `DONE` Claude tile generation with structured prompt/parser
- `DONE` template fallback on generation failure
- `PARTIAL` retry ladder
  - current: primary + fallback template
  - pending: primary -> retry variant -> fallback model -> template
- `PENDING` strict timeout budget + latency SLO instrumentation

---

## 4) Scan Logs / Observability

- `DONE` ll2 score envelope persisted:
  - `state`, `score`, `band`
  - `engine_breakdown`
  - `generation_meta`
  - `tile_content`
  - `triggered_obs`
  - normalized `feedback`
  - `post_scan_action`
- `PARTIAL` schema parity with master spec names/types
- `PENDING` product analytics dashboards tied to new LL2 fields
- `PENDING` Sentry + trace conventions specific to LL2 score path

---

## 5) Auth / Credits / Payments

- `PARTIAL` auth via existing upstream token verification (platform-level)
- `PENDING` WhatsApp OTP-native auth flow inside LL2 boundary
- `PARTIAL` credit gating behavior (`402 insufficient_credits` via daily limit)
- `PENDING` dedicated credits ledger (`free_used/free_limit/paid_remaining`)
- `PENDING` Razorpay order + webhook reconciliation flow

---

## 6) Data Layer / Infra Alignment

- `PARTIAL` Mongo-first implementation for LL2 MVP
- `PENDING` Postgres + SQLAlchemy + Alembic schema rollout from backend guide
- `PENDING` Redis usage for OTP/session/rate-limit/cache in LL2 module
- `PENDING` AWS deployment posture from guide (ECS/RDS/ElastiCache specific checklist)

---

## 7) Compliance / Retention

- `PENDING` DPDP consent flow surfaces (analytics/sensitive toggles)
- `PENDING` export/delete account endpoints and operational workflow
- `PENDING` anonymization lifecycle jobs

---

## 8) Testing

- `DONE` deterministic unit tests authored for LL2 engines (module present)
- `PARTIAL` local runtime missing `pytest` in current environment
- `PENDING` integration tests for `/ll2/score` happy/gate/no-credit paths
- `PENDING` CI contract checks on seed scenarios

---

## 9) Immediate Next Execution Order

1. Install/enable test runtime (`pytest`) and run LL2 unit tests in CI.
2. Introduce full retry ladder in generation service with explicit metadata.
3. Replace MVP safety rules with authored `safety_data.py` clinical rules.
4. Implement credits ledger and purchase initiation endpoint.
5. Add OTP-native LL2 auth endpoints (or formally document continued upstream-auth strategy).
6. Start Postgres dual-write plan if migration is approved.

