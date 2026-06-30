#!/usr/bin/env python3
"""
export_evidence.py — flatten SkinBB_HLHP_Scenario_Library_v3_4.xlsx into one
static hlhp-evidence.json the frontend can read (browser + Next.js).

This turns the demo into a real library browser: every Master single-factor cell
(880), the compound scenarios, the locked band thresholds, the city→zone map +
per-zone weather, the cited Did-You-Know nuggets, and the nutrition/lifestyle
modifiers are exported with their REAL L0/L1/L2 text, risk, confidence, PMID
anchors and action clusters.

Usage:  python3 export_evidence.py <library.xlsx> <out.json>
"""
import sys, json, re
import openpyxl


def norm(v):
    if v is None:
        return ""
    return str(v).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", norm(s).lower()).strip("_")


def load(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    def sheet_rows(name):
        ws = wb[name]
        return [list(r) for r in ws.iter_rows(values_only=True)]

    # ---- 2. Bands Reference: factor -> [{label,range,points,key}] ----------
    bands = {}
    cur = None
    for r in sheet_rows("2. Bands Reference")[1:]:
        factor, label, rng, pts, key = (norm(r[0]), norm(r[1]), norm(r[2]),
                                        r[3], norm(r[4]))
        if factor and not label:
            cur = factor
            bands[cur] = []
        elif cur and label:
            bands[cur].append({"label": label, "range": rng,
                               "points": pts if isinstance(pts, (int, float)) else None,
                               "key": key})

    # ---- 10. Master Library: index by factor|bandkey|skin|concern ---------
    master = {}
    rows = sheet_rows("10. Master Library")
    hdr = rows[0]
    for r in rows[1:]:
        if not norm(r[0]):
            continue
        factor, band, rng, bkey = norm(r[1]), norm(r[2]), norm(r[3]), norm(r[4])
        skin, concern = norm(r[5]), norm(r[6])
        cell = {
            "id": norm(r[0]), "factor": factor, "band": band, "range": rng,
            "band_key": bkey, "skin": skin, "concern": concern,
            "risk": r[7], "risk_level": norm(r[8]), "confidence": norm(r[9]),
            "evidence": norm(r[10]), "pmids": [p.strip() for p in norm(r[11]).split("|") if p.strip()],
            "l0": norm(r[12]), "l1": norm(r[13]), "l2": norm(r[14]),
            "action": norm(r[15]), "zones": [z.strip() for z in norm(r[16]).split(",") if z.strip()],
            "season": norm(r[17]),
        }
        master[f"{slug(factor)}|{bkey}|{slug(skin)}|{slug(concern)}"] = cell

    # available skins / concerns / factors (for the selector)
    skins = sorted({c["skin"] for c in master.values() if c["skin"]})
    concerns = sorted({c["concern"] for c in master.values() if c["concern"]})
    factors = sorted({c["factor"] for c in master.values() if c["factor"]})

    # ---- 8. Compound Scenarios Index --------------------------------------
    compounds = []
    rows = sheet_rows("8. Compound Scenarios Index")
    for r in rows[1:]:
        if not norm(r[0]):
            continue
        compounds.append({
            "id": norm(r[0]), "name": norm(r[1]),
            "temp_band": norm(r[2]), "uv_band": norm(r[3]), "aqi_band": norm(r[4]), "rh_band": norm(r[5]),
            "drivers": [d.strip() for d in norm(r[6]).split(",") if d.strip()],
            "zones": [z.strip() for z in norm(r[7]).split(",") if z.strip()],
            "seasons": norm(r[8]), "mechanism": norm(r[9]), "cities": norm(r[10]),
        })

    # ---- 9. Compound Cell Library: index by scenario_name|skin|concern ----
    compound_cells = {}
    rows = sheet_rows("9. Compound Cell Library")
    for r in rows[1:]:
        if not norm(r[0]):
            continue
        name, skin, concern = norm(r[1]), norm(r[2]), norm(r[3])
        compound_cells[f"{slug(name)}|{slug(skin)}|{slug(concern)}"] = {
            "id": norm(r[0]), "scenario": name, "skin": skin, "concern": concern,
            "risk": r[4], "risk_level": norm(r[5]), "confidence": norm(r[6]),
            "evidence": norm(r[7]), "l0": norm(r[8]), "l1": norm(r[9]), "l2": norm(r[10]),
            "action": norm(r[11]),
        }

    # ---- 1. India Climatic Zones (+ build city->zone) ---------------------
    zones = {}
    city_zone = {}
    for r in sheet_rows("1. India Climatic Zones")[1:]:
        code, name, desc, stressors, cities, ncity = (norm(r[0]), norm(r[1]),
            norm(r[2]), norm(r[3]), norm(r[4]), r[5])
        if not code:
            continue
        clist = [c.strip() for c in re.split(r"[;,]", cities) if c.strip()]
        zones[code] = {"code": code, "name": name, "desc": desc,
                       "stressors": stressors, "cities": clist}
        for c in clist:
            city_zone[c.lower()] = code

    # representative "today" weather per zone (mirrors the engine ZONE_WEATHER
    # in engagement_api.py; used to drive the live SFI for any chosen city)
    zone_weather = {
        "HH": {"temperature_c": 32, "aqi": 120, "uv_index": 7,  "humidity_pct": 82},
        "CN": {"temperature_c": 34, "aqi": 210, "uv_index": 8,  "humidity_pct": 38},
        "HD": {"temperature_c": 40, "aqi": 130, "uv_index": 10, "humidity_pct": 18},
        "TP": {"temperature_c": 28, "aqi": 80,  "uv_index": 6,  "humidity_pct": 52},
        "CH": {"temperature_c": 6,  "aqi": 40,  "uv_index": 7,  "humidity_pct": 30},
        "TN": {"temperature_c": 29, "aqi": 60,  "uv_index": 5,  "humidity_pct": 90},
    }

    # ---- 16. Did-You-Know Nuggets -----------------------------------------
    nuggets = []
    rows = sheet_rows("16. Did-You-Know Nuggets")
    started = False
    for r in rows:
        c0 = norm(r[0])
        if c0 == "#":
            started = True
            continue
        if started and c0 and c0.isdigit():
            nuggets.append({"n": int(c0), "text": norm(r[1]), "factor": norm(r[2]), "source": norm(r[3])})

    # ---- 14 / 15 modifiers ------------------------------------------------
    def modifiers(name):
        out = []
        started = False
        for r in sheet_rows(name):
            if norm(r[0]) == "Modifier":
                started = True
                continue
            if started and norm(r[0]):
                out.append({"modifier": norm(r[0]), "effect": norm(r[1]),
                            "concerns": norm(r[2]), "direction": norm(r[3]),
                            "confidence": norm(r[4]), "evidence": norm(r[5]),
                            "source": norm(r[6])})
        return out

    return {
        "meta": {
            "source": "SkinBB_HLHP_Scenario_Library_v3_4.xlsx",
            "version": "3.4",
            "note": "Evidence library export — L0/L1/L2 alert text, risk, confidence, PMID anchors. Product-free; 'advice' not used.",
            "master_cell_count": len(master),
            "compound_cell_count": len(compound_cells),
        },
        "bands": bands,
        "skins": skins,
        "concerns": concerns,
        "factors": factors,
        "zones": zones,
        "zone_weather": zone_weather,
        "city_zone": city_zone,
        "master": master,
        "compounds": compounds,
        "compound_cells": compound_cells,
        "nuggets": nuggets,
        "nutrition": modifiers("14. Nutrition Modifiers"),
        "lifestyle": modifiers("15. Lifestyle Modifiers"),
    }


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2]
    data = load(src)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out}")
    print(f"  master cells   : {data['meta']['master_cell_count']}")
    print(f"  compound cells : {data['meta']['compound_cell_count']}")
    print(f"  skins          : {data['skins']}")
    print(f"  concerns       : {len(data['concerns'])}")
    print(f"  cities mapped  : {len(data['city_zone'])}")
    print(f"  nuggets        : {len(data['nuggets'])}")
