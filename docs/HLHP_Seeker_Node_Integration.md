# HLHP seeker website integration (Jul 2026)

Seeker HLHP on `skinbb-main-website` talks to **SkinBB Node** (`NEXT_PUBLIC_API_URL`), not the Python SFI engine, for goals / chat / Plus.

## Live Node contract (verified)

| Surface | Path |
|---------|------|
| Goals | `GET/POST /api/v1/hlhp/goals`, `PATCH /api/v1/hlhp/goals/doctor` |
| Consult | `GET /api/v1/consult-chats?doctorId=&format=simple&asRole=seeker` |
| Hub write | `POST /api/v1/hlhp/hub/events` (+ Socket.IO publish) |
| Media | `POST /api/v1/hlhp/hub/media` (`files` multipart) |
| Payments | `POST /api/v1/hlhp/payments/{checkout,verify,cancel,resume,renew}` |
| Realtime | Socket.IO `https://<API_HOST>/hlhp-hub` path `/socket.io` |

Do **not** use removed `/hlhp/hub/stream` or raw `/ws`. Do **not** hub-write `hlhp_goal_setup_v1` / accept / approval from the client — Node publishes those after REST.

## Website files

- `src/services/hlhp-goals.service.ts` — Node goals + Razorpay
- `src/services/hlhp-chat.service.ts` — consult-chats + hub events/media
- `src/hooks/hlhp/useHlhpHubSocket.ts` — Socket.IO
- `src/hooks/hlhp/useHlhpConsultChat.ts` — cold-load + live chat
- `src/components/hlhp/shared/Vybie.tsx` — reusable character (`Mascot` re-exports it)
- Goals chat overlay uses **assigned** `selectedDoctorId` only (no hardcoded `kavya`)

## Seeker UI Phase 1 (V8 Light) — shipped

- Settings slide-in (`SettingsPanel`) + toolbar gear
- My routine builder + WDT “IN-YOUR-ROUTINE” chip
- Streak-lost popup + push preview banners (Settings preview pills)
- Patterns staged cards **1–6** (compound / behavioural / confounder)
- Goals hub: who-it’s-for carousel, plan explainer, plain-language hero, Plus status strip
- Today Halo orb polish (cool V8 Light glow) + Vybie on SFI ring
- CSS: `slideInR` / `slideDn` in `hlhp-fun.css`

## Python Phase 2 — deferred (do after UI sign-off)

Do **not** start this until Phase 1 seeker UI is signed off. Node remains SoT for goals/chat/payments.

| Item | Status |
|------|--------|
| Scenario snapshot **v3.5 → Suite v3.6** (`hlhp-evidence.json`) | Needs change |
| Guest cell shape (`guest_mode` + `guest_compounds`) | Needs change |
| Wire `age_rules` → `age_risk_delta` in `sfi_unified.py` | Needs change |
| Hindi evidence loader | Missing |
| Product routine / `in_routine` in scoring models | Needs change |
| Multi-factor Patterns Spec v2 + log chips | Needs change |
| `bus_contract.py` — remove seeker write ACL for goal/payment | Needs change |
| Deprecate raw `/ws` helper; Socket.IO is SoT | Needs change |
| SFI W_DOM vs additive V4 | Done (intentional — do not port) |
| Fun `/api/v2/*`, weather, selfies, patterns v1 | Done |

### Ownership

- **Node owns:** goals persistence, payments, Socket.IO, consult-chats SoT
- **Python owns:** SFI engine, Fun coach APIs, weather, evidence runtime
- **Do not edit** `D:\skinbb-main-backend` from agents

## Python (AI-Tools) alignment already done

- `goal_service.py` proxies Node goals REST (no hub goal publishes)
- `GET/PATCH /api/v2/goals*` still available for older callers; prefer Node from the website
- `chat_service.get_chat_state` prefers `GET /api/v1/consult-chats` when Node + bearer + doctorId are set

## Hard rules

- `doctorId` = doctor's **User._id**
- Never send `seekerId` in seeker bodies
- Always `asRole=seeker` on hub when dual-role is possible
- Chat images = HTTPS URLs only (upload first)
- Payments only via `/hlhp/payments/*` + Razorpay SDK
