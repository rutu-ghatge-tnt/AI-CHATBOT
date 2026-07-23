# HLHP seeker website integration (Jul 2026)

Seeker HLHP on `skinbb-main-website` talks to **SkinBB Node** (`NEXT_PUBLIC_API_URL`), not the Python SFI engine, for goals / chat / Plus.

## Live Node contract (verified)

| Surface | Path |
|---------|------|
| Goals | `GET/POST /api/v1/consult/goals` (+ assignment / inbox / accept / approve-plan) |
| Consult chats | `GET/POST /api/v1/consult/chats*` (events, media, devices, audit) |
| Payments / Plus | `/api/v1/consult/subscriptions/*`, `/api/v1/consult/payments*` |
| Admin / ops | `/api/v1/consult/overview`, reviews, qc, … |
| Realtime | Socket.IO on Node (`/consult` namespace) |

Do **not** hub-write goal/payment/accept/approval from the client — Node publishes those after REST.

## Website files

- `src/services/hlhp-goals.service.ts` — Node goals + Razorpay
- `src/services/hlhp-chat.service.ts` — consult chats + events/media
- `src/hooks/hlhp/useHlhpHubSocket.ts` — Socket.IO
- `src/hooks/hlhp/useHlhpConsultChat.ts` — cold-load + live chat
- Goals chat overlay uses **assigned** `selectedDoctorId` only (no hardcoded doctor)

## Ownership

- **Node owns:** goals persistence, payments, Socket.IO, consult-chats, admin/QC
- **Python owns:** SFI engine, Fun coach APIs (`/api/hlhp/*`, `/api/v2/*` today/logs/streak/recap/patterns/share/learn/cities/selfies), weather, evidence runtime
- **Removed from AI-Tools:** goals/chat/payment/doctor hub proxies (`/api/v2/goals*`, `/api/v2/chats*`, `/api/v2/plus*`, `/api/hlhp/doctor/*`) and bus client helpers — call Node directly from the website
- **Do not edit** `D:\skinbb-main-backend` from agents

## Python Phase 2 (Fun / evidence only)

| Item | Status |
|------|--------|
| Scenario snapshot Suite **v3.6** + guest_mode / age_rules | Done |
| Wire `age_rules` → `age_risk_delta` in `sfi_unified.py` | Done |
| Hindi evidence loader | Missing (if product wants EN/हिं alerts) |
| Product routine / `in_routine` in scoring models | Needs change |
| Multi-factor Patterns Spec v2 + log chips | Needs change |
| SFI W_DOM vs additive V4 | Done (intentional — do not port) |
| Fun `/api/v2/*`, weather, selfies, patterns v1 | Done |

## Hard rules (website ↔ Node)

- `doctorId` = doctor's **User._id**
- Never send `seekerId` in seeker bodies
- Chat images = HTTPS URLs only (upload first)
- Payments only via Node subscriptions/payments + Razorpay SDK
