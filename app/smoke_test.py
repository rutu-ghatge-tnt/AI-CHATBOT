"""
Unified engine smoke test.

Runs the same Delhi peak-summer day through five profiles and prints the
full output of each. Demonstrates:

  - SFI shifts with profile (normal user sees a higher score than a
    melasma-prone user on the same day)
  - L1 is identical across profiles (universal)
  - L2 changes per skin type / concern
  - L3 is identical (technique applies to everyone)
  - Science tip is relevance-picked from the day's condition tags

Run from the hl_engine_unified/ directory:
    python smoke_test.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from hl_engine import (
    evaluate,
    EnvironmentalData,
    UserProfile,
    SkinType,
    SkinConcern,
)


def show(label: str, env, profile):
    r = evaluate(env, profile)
    print("\n" + "=" * 78)
    print(f"  {label}")
    print(f"  profile : {r.profile_summary}")
    print("=" * 78)
    print(f"  Skin Friendliness Index : {r.skin_friendliness_index}/100")
    print(f"  Band                    : {r.band}  ({r.band_color})")
    print(f"  Personalised?           : {r.is_personalized}")
    print(f"  Factor breakdown        : "
          f"UV={r.factor_breakdown.uv}  "
          f"T={r.factor_breakdown.temperature}  "
          f"AQI={r.factor_breakdown.aqi}  "
          f"H={r.factor_breakdown.humidity}")
    print(f"  Scenario                : {r.scenario_code} · {r.scenario_name}")
    print("")
    print(f"  L1  (universal)         : {r.alert.l1}")
    print(f"  L2  (skin-type/concern) : {r.alert.l2}")
    print(f"  L3  (technique)         : {r.alert.l3}")
    print("")
    print(f"  Science tip             : {r.science_tip.fact}")
    print(f"  Source                  : {r.science_tip.source}")


# A single shared day — Delhi peak summer
delhi = EnvironmentalData(
    location="Delhi",
    uv_index=9.0,
    temperature_c=41.0,
    aqi=230,
    humidity_pct=22,
)

PROFILES = [
    ("ANONYMOUS",           None),
    ("NORMAL · NO CONCERN", UserProfile(skin_type=SkinType.NORMAL)),
    ("OILY · MELASMA",      UserProfile(skin_type=SkinType.OILY,      concerns=[SkinConcern.MELASMA])),
    ("DRY · DEHYDRATION",   UserProfile(skin_type=SkinType.DRY,       concerns=[SkinConcern.DEHYDRATION])),
    ("SENSITIVE · REDNESS", UserProfile(skin_type=SkinType.SENSITIVE, concerns=[SkinConcern.REDNESS])),
]


def main():
    print(f"\nShared day — {delhi.location}: "
          f"UVI {delhi.uv_index} · {delhi.temperature_c}°C · "
          f"AQI {delhi.aqi} · RH {delhi.humidity_pct}%")
    for label, profile in PROFILES:
        show(label, delhi, profile)


if __name__ == "__main__":
    main()
