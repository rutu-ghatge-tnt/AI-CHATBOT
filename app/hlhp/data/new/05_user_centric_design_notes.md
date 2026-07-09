# HLHP — User-Centric Design Notes

The "fab" part of the design isn't the animations. It's the deliberate decisions that put the user (an Indian skincare consumer with real skin concerns and limited time) ahead of the product. This doc captures those decisions per screen so the Figma file isn't just pretty — it's defensible.

---

## Onboarding overlay

**User truth:** They've installed dozens of wellness apps. They expect the next one to demand 12 fields, push a paywall, and ask for selfies.

**Design decision:** Show ONE screen. ONE button. ONE skip option. The mascot is the first thing they see, not a form. The message is *what the coach IS* — not *how to use it*. They learn the value proposition (quiet by default, vocal when it matters) before they learn the navigation. Skip path is intentional and friction-free; over-aggressive onboarding loses 30 % of installs.

**Tradeoff:** We forgo the chance to collect Fitzpatrick type, top concern, and AQI sensitivity upfront. We earn it back via the chips in the Log tab — they ARE the onboarding, but disguised as the daily ritual.

---

## Hello tab

**User truth:** They open the app at 7 AM, half-awake, holding a coffee. Two seconds of cognitive load is too much.

**Design decision:** The mood orb tells the day's vibe with colour alone — orange-amber means warm, indigo-blue means humid, deep-purple means humidity surge. No reading required. The greeting line uses their name and a single warmth-loaded word (*summer-warm* / *humidity-heavy* / *dust-laden* / *clean-air*). The CTA is one verb (*Check in*) — not two (*Log your symptoms*) which feels like work.

**Tradeoff:** We give up immediate dashboard data on the Hello screen. That's deliberate — the dashboard moment is the *reward* for tapping the CTA, not the entry hall.

---

## Log tab

**User truth:** They feel something specific ("my forehead is itchy") but they don't know if it counts, where to start, or whether the app will judge them for not knowing skin science.

**Design decision:** **Chips not questions.** They tap one of 7 plain English words (itchy, dry, oily…). The app *then* asks the smart follow-up *because of what they tapped* — not as a fixed form. This is concern-aware branching: breakout asks face zone + count, itchy asks body location, dry asks severity. The captured-data card fills in beside them, visually proving their tap mattered. The closing card is a small reward ("Your engine learned something new") — not a confirmation toast.

**Why floating emojis on each tap:** Most logging apps feel like data-entry. The +1/heart/star floating up is borrowed from social apps — it makes the user feel they *gave* something, not *gave up* something. Five logs in 30 days becomes plausible.

---

## Streak tab

**User truth:** They've broken streaks in other apps and they remember the pain. Showing "23 days" without context risks reminding them.

**Design decision:** The flame physically flickers (not just sits there) and embers rise continuously. Streaks visualised as alive — not as a counter waiting to break. The 30-day badge milestone is shown as 7 days *to go*, not 23 days *done* — forward orientation. The "Only 3% of users reach this" social-proof line gives the streak external value, not just personal vanity.

**Why confetti on the milestone card itself, not just on completion:** Daily reinforcement is more habit-forming than rare jackpots. The trophy card SHIMMERS continuously — they see it every visit, and that scarcity-of-3% sits in their head between visits.

---

## Surge tab

**User truth:** Sudden alerts are anxiety-inducing. Most weather apps just shout *"!!!"* and run.

**Design decision:** The push banner *slides in with a single bounce, then settles* — not a panic. The frame shakes once and stops. The score-dip is animated SLOWLY (1400ms) so the user sees the *story* of the drop, not just the new number. The mascot has worried eyebrows — emotion is acknowledged, not denied. The message "*This is a test, not a setback*" reframes alarm as agency.

**Why the spike chart appears AFTER the alert, not with it:** Cognitive load. First, raise alarm. Then, give the evidence (the bars). Then, give the plan. Sequenced disclosure prevents overwhelm.

---

## Recap tab

**User truth:** Looking back at a month of data should feel like reading a postcard from your past self, not auditing tax returns.

**Design decision:** The walker mascot literally walks across the timeline — turning data into a story with a protagonist. Day marks are colour-coded by environment (not by SFI score) so the user sees what their *city* did to them, not what they did wrong. Callouts pop at the specific events that mattered — June 12 surge, June 19 humidity wave, June 23 streak — making the month *narrative*, not numeric.

**Why "Stronger than May" is the verdict:** Comparison to self, not to peers or to an ideal. The brain rewards relative improvement faster than absolute milestones. "Avg SFI 68 (was 61)" is the proof, not the headline.

---

## Patterns tab

**User truth:** "Patterns" sounds like a feature you have to *use*. They want to be *shown* something they didn't already know.

**Design decision:** The hero says **"We noticed"** — passive, observational, *we did the work*. Each pattern leads with a plain-English headline ("Itchy days cluster on high-humidity afternoons") — not a chart that requires interpretation. The 83% / 71% / 68% match ribbons give scientific weight without being intimidating. Every card ends in ONE CTA that *acts* on the insight — alert me, set reminder, plan routine. Not "learn more." Not "see details." DO something.

**Why three patterns, not ten:** Cognitive limit. Three is the magic number for human pattern recognition. After ten, the user disengages. We pick the three with highest correlation × highest user agency, then bench the rest.

---

## Share (Weekly Card) tab

**User truth:** They share what makes them look smart, kind, or interesting — never what makes them look needy or sick.

**Design decision:** The card is *Spotify-Wrapped beautiful* on purpose. Big number "72/100" reads like a score, not a confession. The chart is abstract enough that no one viewing the Story can diagnose anything specific. The "+4 from last week" trend is the brag. The HLHP logo + Pune footer gives it credibility-without-pity. Story is the first share button because Instagram Stories has the highest 24-hour reach (a Pune teen sees a friend's HLHP card before lunch — that's the viral atom).

**Why no "share to feed":** Stories vanish in 24h, removing the long-term self-judgment risk. Feed posts last forever and become a vulnerability. We default to ephemeral.

---

## Good Day tab

**User truth:** Most apps notify you about failures. Almost none celebrate good stretches. The brain learns the app = bad news.

**Design decision:** When 3+ consecutive good days fire, this screen TAKES OVER. Confetti rain (60 pieces). Headline letter-cascade animation. Mascot literally jumps. Three stat cards count up the metrics that drove the good week. **"Bottle this routine"** card converts celebration into a saved recipe the user can replicate. The brain now learns: HLHP = celebration *and* science.

**Why the trigger is rare (3+ consecutive 75+ days), not daily:** Variable-ratio reinforcement. If celebration is daily, it becomes wallpaper. Rare celebrations carry weight. We pair this with the Streak tab so users see *both* the long-game (streak) and the rare-jackpot (good day).

---

## Persistent coach voice bubble

**User truth:** They don't want a chatbot. They want a quiet, smart friend who only speaks when they have something useful to say.

**Design decision:** The bubble is anchored *under the badge strip*, not over the content. It's visible without being intrusive. The avatar is a single letter "C" — not a face, not a name, not a personality. The voice is **directive, not observational** ("Set a 9 PM reminder — you've got this"), and screen-specific. The "YOUR COACH" tag in gold-bright is a quiet brand cue — the user reads "coach" subconsciously every screen.

**Why directive over observational:** Observational ("Your skin reading is warm") is what every other app does. Directive ("Light routine today — heavy products will feel sticky") is what a friend does. The mascot is a coach, not a thermometer.

---

## Badge strip

**User truth:** They want to feel they're progressing without having to dig.

**Design decision:** Earned badges + locked badges *always visible* under the tabs. The collection grows quietly across weeks; users notice their own progress without opening a separate "Achievements" screen. Hover reveals badge name + unlock condition — turns the locked ones into goals rather than mysteries.

**Why 4 earned + 3 locked:** A 1.33:1 earned-to-locked ratio. Enough earned to feel rewarded. Enough locked to feel curious. Tested in games — anything over 2:1 feels too easy; anything under 0.5:1 feels punishing.

---

## What we deliberately DID NOT design

**No dark mode** for v1. Cream-warm is the brand voice; dark mode is a perception of clinical-tech that fights the *trusted-friend* positioning. Add later if user research demands.

**No skin-tone customisation slider** for the mascot. Universal sheep avoids the trap of forcing users to declare Fitzpatrick type. Customisation is a v1.1 conversation.

**No social leaderboards.** Compete only with your past self. Comparison to others is the fastest path to body-image distress in skincare apps. We never go there.

**No streaks longer than 30 days in v1.** Longer streaks create unhealthy pressure. After 30 days, we celebrate and reset the counter as "Month 2 of consistent care" — different language, same data.

**No notifications by default.** Notifications are earned by demonstrated trust. The user enables them per pattern (e.g., humidity surge alerts) — they're not opt-out, they're opt-in per case. This is the trust-building layer that turns first-month users into year-three loyalists.

These omissions are as important as the inclusions. The Figma file should reflect them — every NOT shown is a deliberate choice.
