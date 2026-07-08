# HLHP Patterns — Backend README

Reference backend for the SkinBB **HLHP Patterns tab**: unlock gating, pattern
detection, decay/reactivation, and the AI-narration contract.

This README orients a backend developer picking up `hlhp_patterns_engine.py`. It
explains what the module does, how it fits the existing app, how to run it, and
what still has to be built.

---

## 1. What this is

The Patterns tab shows a user the environmental triggers behind their skin
symptoms (e.g. "humid days → breakouts"). Today it is **not real** — the
front-end (`hlhp-interactive.html`) hardcodes the charts in `animSP()`. This
engine replaces that fake data with a deterministic pipeline:

```
user logs  ─▶  gate check (unlock?)  ─▶  detection (find patterns)  ─▶  JSON payload  ─▶  front-end
                                                     │
                                                     └─▶  AI narration (story only, cached)
```

**Detection is deterministic. AI only narrates.** The algorithm finds and scores
patterns; the LLM writes the human sentence around numbers the algorithm already
computed. The AI never invents a pattern or a number. This is a hard rule — see
§6 and the numeral validator.

---

## 2. Files in this feature

| File | What it is |
|---|---|
| `hlhp_patterns_engine.py` | **This module.** Runnable reference engine + optional Flask surface. |
| `hlhp_patterns_prompts.py` | AI-narration prompts: system prompt, voice rules, few-shot example, output schema, `build_messages()`, plus all templated lifecycle/notification copy. |
| `patterns-tab-rules-v1.md` | Product rules, states, and the 12 scenarios. Signed off. |
| `patterns-implementation-spec-v1.md` | Build contract: constants, data model, API, acceptance tests. |
| `patterns-lifecycle-ui-v4.html` | Front-end prototype of all 8 states (what the payload renders into). |
| `hlhp-interactive.html` | The current main app (reference for how data is wired today). |

Read order for a new dev: this README → `patterns-tab-rules-v1.md` →
`patterns-implementation-spec-v1.md` → the code.

---

## 3. Run it now

No dependencies for the core engine (Python 3.10+ stdlib only).

```bash
python hlhp_patterns_engine.py
```

This runs `_demo()`, which synthesises 30 days of logs + environment and prints a
real payload:

```
STATE: UNLOCKED_ACTIVE | log_days: 26 | exposure_days: 19
PATTERNS FOUND: 3
{ "state": "UNLOCKED_ACTIVE", "meter": {...}, "patterns": [ ... ] }
```

The optional Flask layer needs Flask:

```bash
pip install flask
```

---

## 4. The two things a user must do to unlock

Both gates must be true in the **same rolling 30-day window**:

1. **30-day floor** — at least 30 days since the user's *first log* (not signup).
   A perfect logger still waits 30 days.
2. **Consistency** — ≥ **25 log-days** in the window (max 1 log-day per calendar
   day; binge-logging doesn't help).
3. **Exposure** — ≥ **5 logged days** where the weather was adverse (else there's
   nothing to learn). Calm month → a "stability" partial unlock, never a failure.

Gaps **delay** unlock; they never reset progress (rolling window). After unlock
the tab **never re-locks** — it decays instead (§5).

All thresholds live in `class Config` and should be served/config-driven, not
hardcoded in the client.

---

## 5. States the engine emits

`evaluate_state()` returns one of these in `payload["state"]`; the front-end
switches screens on it.

| State | Meaning | Front-end screen |
|---|---|---|
| `LOCKED` | < 5 log-days | Gate checklist + progress ring + generic city pattern |
| `EARLY_SIGNALS` | ≥ 5 logs, pre-unlock (also the calm-month stability case) | Candidate cards, "still checking" |
| `UNLOCKED_ACTIVE` | ≥ 20 log-days in window | Full live patterns |
| `UNLOCKED_FADING` | 12–19 log-days | Greyed confidence, one nudge, new-detection paused |
| `UNLOCKED_PAUSED` | < 12 log-days | Dimmed patterns + 3-of-5 reactivation challenge |

`payload["freshness"]` gives `active|fading|paused` for the toolbar pill.

---

## 6. How the AI narration boundary works

`build_narration_packet()` assembles **only computed numbers** (pattern stats +
library L1 text + PMIDs + a month summary) — no raw logs, no PII, city only. The
LLM returns story text. Then, before anything is shown:

- `validate_narration(output, packet)` — **blocking.** Every numeral in the AI
  output must appear in (or be derivable from) the packet. Fail → regenerate once
  → fall back to a template.
- `narration_fallback(pattern)` — deterministic template so the screen always
  renders, even with the AI provider down. **Never block the UI on the LLM.**

Narration is generated on unlock, on a weekly batch, and on promote/demote — then
**cached**. Never call the LLM on tab open.

---

## 7. How it plugs into the current app

The front-end already loads its evidence library via
`fetch("hlhp-evidence.json") → EV`. Patterns should load the same way:

```js
// replaces the hardcoded TL / WK / HR / 83% arrays in animSP()
fetch(`/v1/patterns?user=${uid}`).then(r => r.json()).then(renderPatterns);
fetch(`/v2/patterns/narration?user=${uid}`).then(r => r.json()).then(applyNarration);
```

Card field names in the payload match the v4 prototype exactly (`color_var`,
`w_icon`, `w_label`, `s_icon`, `s_label`, `say`, `plain`, `cc_note`, `conf`,
`chart:[{lvl,sym}]`, `pmids`, `score_line`) so they feed straight into the
existing `eqCard()` / `corrChart()` renderers. Section 7 of the .py file is a
line-by-line OLD→NEW map.

### Endpoints (Flask example in the module)

| Method | Route | Returns |
|---|---|---|
| `GET` | `/v1/patterns/state` | state + meter + freshness |
| `GET` | `/v1/patterns` | full payload (state, meter, patterns, emerging, reactivation) |
| `GET` | `/v2/patterns/narration` | cached AI text |
| `POST`| `/v1/logs` | save a log, then return the recomputed payload |

`/v1/*` = engine, `/v2/*` = engagement — matching the app's existing split.

---

## 7a. When prompts fire + token control

Two clocks (full detail in `hlhp_patterns_prompts.py` §7 `TRIGGER_MAP` and §8):

**AI prompts (LLM, cost tokens) — fire ONLY on data-changing events, then cache:**

| Event | Regenerates |
|---|---|
| Unlock (one-time) | unlock headline + identity + all cards |
| Weekly job (Sun 02:00, ACTIVE only) | weekly digest (+ dirty cards) |
| Pattern promoted | the one new card |
| Pattern demoted | the one demoted card |
| Profile change | affected cards (marked recalibrating) |

Between events the tab serves cached text. **Never call the LLM on tab open.**

**Templates (free string-fill) — render on demand / on scheduled push:**
pre-unlock screens fill live from `pattern_state`; pushes fire on transitions
with rate limits (behind-pace **max 1/week**; one push per decay episode).

**Token reduction (no quality loss)** — five levers, coded as helpers:
1. **Dirty-check** (`should_regenerate` / `input_hash`) — skip any card whose
   numbers didn't change since last generation. Removes ~90% of calls.
2. **Delta only** (`slim_packet`) — on promote/demote, send just the affected
   card, not the whole set.
3. **Prompt caching** — the system prompt + few-shot prefix is identical every
   call; cache it provider-side so you pay for it once. Drop the few-shot
   (`include_example=False`) once tuned.
4. **Batch the weekly refresh** — one call for all of a user's active cards
   shares the prefix once.
5. **Small model + tight caps** — grounded narration needs only a Haiku-class
   model, `max_tokens≈220`, `temp≈0.4`. Reserve a bigger model for unlock only.

Steady-state cost ≈ (new patterns/week) + (1 weekly digest) per active user.

---

## 7b. "Warn me next time" flow

The button on each pattern card is a real feature. Tapping it subscribes the user
to a **pre-emptive push for that pattern's driver** — when tomorrow's forecast
shows (say) humidity climbing back into its adverse band, they're warned *before*
the breakout. A confirmed pattern becomes a pre-symptom alert. Reuses the app's
existing surge/push plumbing — no new channel.

| Step | Where |
|---|---|
| Tap toggles subscription | UI `toggleWarn()` → `POST /v2/patterns/alert {user, pattern_id, on}` |
| Store opt-in | `PatternAlert` (UNIQUE user_id+pattern_id) via `subscribe_alert()` |
| Card reflects on/off | payload `subscribed` flag per card → button `.on` state |
| Forecast job fires push | `check_pattern_alerts(alerts, forecast_env, notif_prefs, today)` |
| Render the push | `prompts.pattern_alert_copy(driver, symptom, when)` |

Guards: respects the global `surge` notif pref (off → no push); **de-dupes** via
`last_fired_on` so a multi-day surge warns once; 2-day forecast horizon. Copy is
templated (a factual heads-up needs no LLM). To wire up: implement
`repo.get_alerts` / `save_alerts` / `get_patterns`, and call `check_pattern_alerts`
in the existing forecast/surge job.

## 8. What you still have to build (this module stops at the boundary)

1. **Persistence.** Implement the `repo` adapter (see `make_flask_app` docstring)
   against your DB: `get_state`, `get_logs`, `get_env`, `get_profile`,
   `ev_master`, `save_log`, `narration`. Data-model dataclasses (§2 of the code)
   map to your tables.
2. **Persist logs on save.** Today `HLHP.saveLog()` only does `state.logCount++`
   in the browser. Wire it to `POST /v1/logs`.
3. **Store `first_log_date`** per user — the 30-day floor counts from it.
4. **Nightly job** (local midnight): `evaluate_state()` → `detect_patterns()` →
   refresh narration cache → fire transition notifications.
5. **Sync the vocabulary.** `ADVERSE_BANDS` and the `band_to_lvl` map in
   `_build_chart()` must match the real `EV.bands` in `hlhp-evidence.json`.
6. **Notifications** with the rate limits in `patterns-implementation-spec-v1.md`
   §8 (e.g. behind-pace nudge max 1/week; one push per decay transition).
7. **Analytics events** (spec §9) and the **acceptance tests** (spec §10) — the
   given/when/then cases are ready to turn into a test suite.

---

## 9. Tuning knobs (all in `class Config`)

`UNLOCK_LOG_DAYS` (25), `EXPOSURE_MIN_DAYS` (5), `PROMOTE_MIN_LIFT` (1.5),
`ACTIVE_MIN_LOG_DAYS` / `FADING_MIN_LOG_DAYS`, `MAX_DISPLAYED` (3),
`CHART_DAYS` (14). Change here, not in the client.

---

## 10. Glossary

- **Log-day** — a calendar day with ≥1 saved log (multiple saves collapse to one).
- **Exposure (E)** — adverse-driver days that were logged.
- **Hit (H)** — exposure days where the linked symptom appeared within 24h.
- **Lift** — how much more often the symptom occurs on adverse days vs calm days;
  must be ≥ 1.5 to promote a pattern (guards against coincidence).
- **Promote / Emerging / Demote** — display tiers; top 3 shown, rest "emerging".
