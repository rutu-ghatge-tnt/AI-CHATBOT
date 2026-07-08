# Patterns Tab — Rules Spec v1 (DRAFT)

**Product:** SkinBB HLHP · **Scope:** unlock logic, degradation logic, confidence math, edge scenarios
**Status:** proposal for review · 7 Jul 2026

---

## 1. Principles

1. **Two gates, not one.** Consistency (did you log enough?) + Exposure (did the environment give us anything to learn from?). Either alone can produce an empty or misleading Patterns screen.
2. **Rolling window, not from-signup.** A fixed 30-days-from-signup window permanently punishes a slow start. Any rolling 30-day window that meets the gates unlocks.
3. **Decay, never re-lock.** Once unlocked, the tab never goes back behind a lock. Irregularity degrades freshness, and recovery is deliberately cheap.
4. **The tab is never dead.** Even fully locked it shows a progress meter + one generic city-level pattern from the scenario library, so visiting always pays something.

---

## 2. Definitions

| Term | Definition |
|---|---|
| **Log-day** | A calendar day with ≥1 saved log. Max 1 per day (binge-logging doesn't accelerate unlock). |
| **Window** | Rolling 30 calendar days, evaluated daily. |
| **Adverse day (driver D)** | A day where driver D (Temp / UV / Humidity / AQI) sat in an adverse band per the v3.5 band tables. |
| **Exposure E(D)** | Adverse-D days in the window **that have a log**. |
| **Hits H(D,S)** | Exposure days where symptom S was logged within 24h of the adverse band. |
| **Baseline B(S)** | Rate of symptom S on non-adverse (calm) logged days. |
| **Pattern candidate** | A (driver-band × symptom) pair being tracked. |

---

## 3. Tab states

### 3.1 Pre-unlock

| State | Condition | What the user sees |
|---|---|---|
| **LOCKED** | < 5 log-days | Progress meter ("X/25 logs in your 30-day window"), 1 generic city-level pattern from the library ("In Pune, humidity spikes precede breakout reports"), explainer of what's coming. |
| **EARLY SIGNALS** | ≥ 5 log-days | Candidate patterns shown, clearly ribboned "Early signal · low confidence". Meter continues toward full unlock. |

### 3.2 Unlock (both gates in the same rolling window)

- **Consistency gate:** ≥ **25 log-days / 30**.
- **Exposure gate:** ≥ **5 exposure days** (any driver) with logs.

**Consistency met, exposure not:** do not fail the user. Message: *"Your skin's had a calm month — we need a few rough-weather days to learn your triggers."* Unlock the **Stability pattern** instead ("Your baseline held through 30 days"), keep watching for adverse days. Full unlock completes automatically at 5 exposure days.

**Unlock moment:** celebration screen + push ("Your first patterns are ready") + badge. This is a major milestone — treat it like the 30-day streak.

### 3.3 Post-unlock freshness (answer to "what if they turn irregular?")

Evaluated daily on the rolling window:

| State | Log-days in window | Behaviour |
|---|---|---|
| **ACTIVE** | ≥ 20 | Full patterns, live confidence %, new-pattern detection ON. |
| **FADING** | 12–19 | Confidence bars grey, delta arrows frozen at last-known. Banner: *"Your patterns are fading — 4 logs this week keeps them live."* Detection of NEW patterns paused. |
| **PAUSED** | < 12 | Existing patterns dimmed with "paused" ribbon. Hero card replaced by a **reactivation challenge**: *"Log 3 of the next 5 days to reactivate."* No detection, no confidence updates. |

- Data is **never deleted**; confidence resumes from where it left off once reactivated (with freshness re-weighting, §4).
- Reactivation is intentionally cheap (3-of-5) — it's a re-engagement hook, not a punishment.
- Notification hooks: entering FADING triggers one (and only one) "patterns fading" push; entering PAUSED triggers one "reactivation challenge" push. No nagging repeats.

---

## 4. Confidence math (what "83% match" means)

For each pattern candidate (D → S):

```
match%   = H(D,S) / E(D)                  ← the number on the ribbon
lift     = (H/E) / max(B(S), 0.05)        ← must be ≥ 1.5 to promote
freshness = share of E days falling in the last 30 days (recency weight)
```

**Promotion rule:** candidate → displayed pattern when `E ≥ 5` AND `lift ≥ 1.5`.

**Confidence label** (aligned with the scenario-library vocabulary):

| Label | Rule |
|---|---|
| HIGH | E ≥ 10 and lift ≥ 2.0 |
| MODERATE | E ≥ 7 and lift ≥ 1.5 |
| EARLY | E = 5–6 (only shown pre-unlock as "early signal" or as "emerging" post-unlock) |

**Display cap:** top 3 patterns by (label, then match%). Others listed under "Emerging" as one-liners.

**Anti-patterns to avoid:** never show match% with E < 5 (small-sample nonsense); never let match% and the library's clinical confidence (PMID-backed) share one visual scale — personal pattern confidence is behavioural, library confidence is clinical. Keep them visually distinct.

---

## 5. Scenarios

| # | Scenario | Behaviour |
|---|---|---|
| 1 | **Perfect user** — logs daily from signup | Early signals at day 5, unlock at day 25–30 (when exposure gate also met). |
| 2 | **Slow starter** — 25 log-days reached on day 42 | Rolling window unlocks on day 42. Progress meter always shows the *best current window*, so it can tick down as old days fall out — copy must explain: "logs older than 30 days age out." |
| 3 | **Binge logger** — 10 logs in one evening | Counts as 1 log-day. Optional later: AM/PM = 2 slots for finer lag analysis, still 1 log-day for gates. |
| 4 | **Streak breaks day 20, returns day 23** | Window slides; they lose ≤3 days of progress, not everything. Pairs with streak shield. Meter never visibly "resets to zero." |
| 5 | **Unlocked, then silent 2 weeks** | ACTIVE → FADING (~day 10 of silence) → PAUSED (~day 18). One push at each transition. Reactivation = 3 logs in 5 days. |
| 6 | **Calm-weather month** — 25/30 logged, no adverse days | Stability pattern unlocked; full unlock auto-completes when 5 adverse days accumulate. Positive framing, never "insufficient data." |
| 7 | **Always logs "Normal"** | Counts fully. Enables resilience patterns ("your barrier held through 6 humidity surges") — arguably the best marketing story in the app. |
| 8 | **City change / travel mid-window** | Logs tagged with that day's city. Coverage counts globally; exposure/patterns computed per city. Travel days appear in the Travel journey, excluded from home-city pattern math if < 5 days in that city. |
| 9 | **Profile change (skin type / concern)** | Patterns kept, marked "Recalibrating" for 7 days; confidence recomputed against new profile weights. Never delete. |
| 10 | **> 3 strong patterns** | Top 3 displayed, rest under "Emerging". Swap-in when confidence overtakes. |
| 11 | **Contradictory data** — symptom on calm days, not adverse days | Lift < 1.5 → candidate never promoted. If a previously promoted pattern's lift drops below 1.2 for 2 consecutive weeks, demote to "Emerging" with copy "this link is weakening — we're watching it." |
| 12 | **Day-1 user visits Patterns** | LOCKED state: generic city pattern + meter at 0/25 + "here's what this screen becomes" illustration. |

---

## 6. Prompts & copy (Copy Bank additions — per lifecycle state)

Voice rules: plain hook + caring verdict; reads, never scores/grades; always state the exact number of logs remaining; never frame missed days as failure (the rolling window means nothing resets).

### 6.1 New user, just signed up (LOCKED, days 0–4)
| Surface | Copy |
|---|---|
| Patterns tab empty state | "This screen learns you. Log most days for a month — 25 of 30 — and your personal skin patterns unlock. Until then, here's what your city's data already shows." (+ generic city pattern card) |
| Coach bubble | "Patterns need history. Every log you save is a piece of the picture." |
| Push (evening, day 2) | "Two logs in. Keep going — your skin starts explaining itself at 25." |

### 6.2 Regular logger, on track (pre-unlock)
| Surface | Copy |
|---|---|
| Progress meter | "18 of 25 logs — ahead of pace. Your patterns unlock around {projected_date}." *(always show a projected date, not just a fraction)* |
| Coach bubble | "You're logging like clockwork. {n} more and this tab comes alive." |
| Push (7 days out) | "One week to your patterns. Your streak is doing the heavy lifting." |
| Early-signal ribbon | "Early signal — it settles as your logs grow." |

### 6.3 Irregular logger nearing day 30, data insufficient
| Surface | Copy |
|---|---|
| Patterns tab | "You're at {x} of 25 logs. No reset, no penalty — your window moves with you. {n} more logging days and this unlocks." |
| Coach bubble | "Missed days don't erase progress, they just stretch the wait. Tonight's log counts the moment you save it." |
| Push (**max 1/week in this state**) | "Your patterns are {n} logs away — the window rolls with you, so tonight still counts." |

### 6.4 Unlock — congratulations
| Surface | Copy |
|---|---|
| Full-screen moment | "Your skin has patterns." / "30 days. {logs} logs. {n} patterns found. Most people never learn this about themselves." / CTA "Meet them →" |
| Push | "It's ready. Your skin's first patterns are in." |
| Coach (first visit after) | "This is what a month of showing up looks like. From here, every log makes these sharper." |

### 6.5 Post-unlock — sustaining regularity
| Surface | Copy |
|---|---|
| Coach (ACTIVE, tied to real deltas) | "Your {driver} pattern got sharper this week — two more days confirmed it." |
| Weekly digest push | "This week strengthened one pattern and put a new one on watch." |
| New-pattern tease | "Something new is emerging in your logs. Two more confirmations and we can name it." |
| FADING banner | "Patterns fade when logs stop — four logs this week keeps them live." |
| PAUSED / reactivation | "Your patterns are paused, not lost. Three logs in five days brings them back." |
| Demotion (scenario 11) | "This link is weakening — we're watching it." |
| Exposure-gate wait | "Calm month so far — patterns need a bit of rough weather." |

## 7. Decisions (RESOLVED — Ajit, 7 Jul 2026)

1. **30-day hard floor:** unlock can never happen before day 30 counted from the user's **first log** (not signup). Even a perfect logger waits till day 30.
2. **25/30 confirmed** (not softened to 20). Evaluated on a rolling 30-day window ending today.
3. **Gaps delay, never reset:** if the current rolling window has < 25 log-days, unlock is simply delayed until some rolling window reaches 25/30. Up to 5 missed days are absorbable; each miss beyond 5 pushes the unlock date out.
4. **Data maximisation during the ramp** is an explicit product goal — progress meter with projected unlock date, morning check-in loop, streak + shield, and prompt set §6 all serve it. Log richness (symptoms + areas) improves pattern quality but never changes the gates (still max 1 log-day/day).
5. **Post-unlock fading approved:** ACTIVE / FADING / PAUSED decay model as specified in §3.3. No re-locking.

Still open (later versions): AM/PM dual logging; whether forecast personalisation shares these gates (recommended: yes).
