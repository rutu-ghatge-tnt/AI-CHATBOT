_BASE = {
    "whats_happening": "Conditions in {location} increase stress from {dominant_threat}.",
    "compact_headline": "Hyperlocal alert: protect your barrier today.",
    "alert_body": "UV {uv}, temp {temp}C, AQI {aqi}, humidity {humidity}% indicate elevated skin stress.",
    "steps": [
        {
            "action": "Apply broad-spectrum SPF50 and reapply every {spf_interval} min",
            "reason": "UV and heat reduce sunscreen persistence outdoors",
            "product_category": "sunscreen",
        },
        {
            "action": "Use an antioxidant/niacinamide support serum",
            "reason": "Helps defend against oxidative load from UV and pollution",
            "product_category": "serum",
        },
        {
            "action": "Use texture-matched moisturizer (gel in humidity, cream in dryness)",
            "reason": "Supports barrier while minimizing congestion risk",
            "product_category": "moisturizer",
        },
    ],
    "key_dont": "Do not skip SPF or barrier support when conditions are unstable.",
    "evening_recovery": "Gentle cleanse -> targeted treatment -> barrier moisturizer.",
    "weekly_boost": "Use one recovery mask and one gentle exfoliation session weekly.",
}

SCENARIOS = {
    i: {
        **_BASE,
        "name": f"Scenario {i}",
        "code": code,
    }
    for i, code in {
        1: "HT-HA-HU-LH",
        2: "HT-LA-HU-LH",
        3: "HT-HA-HU-HH",
        4: "HT-LA-HU-HH",
        5: "LT-HA-HU-LH",
        6: "LT-LA-HU-LH",
        7: "LT-HA-HU-HH",
        8: "LT-LA-HU-HH",
        9: "LT-HA-LU-LH",
        10: "LT-LA-LU-LH",
        11: "LT-HA-LU-HH",
        12: "LT-LA-LU-HH",
        13: "HT-HA-LU-LH",
        14: "HT-LA-LU-LH",
        15: "HT-HA-LU-HH",
        16: "HT-LA-LU-HH",
    }.items()
}

