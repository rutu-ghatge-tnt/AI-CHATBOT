TEMP_THRESHOLDS = [
    (-50, 5, 0, "Extreme Cold", "Critical", "Barrier stress from cold and dehydration risk."),
    (5, 15, 5, "Cold", "High", "Low sebum output and tighter skin barrier."),
    (15, 20, 12, "Cool", "Moderate", "Mild dryness and reduced comfort."),
    (20, 27, 25, "Optimal", "None", "Best window for skin comfort and routine efficacy."),
    (27, 34, 12, "Warm", "Moderate", "Higher oil output and sweat onset."),
    (34, 42, 5, "Hot", "High", "Sweat and oil increase clogging and SPF loss risk."),
    (42, 60, 0, "Extreme Heat", "Critical", "Severe heat stress with safety concerns."),
]

AQI_THRESHOLDS = [
    (0, 50, 25, "Good", "None", "Low pollution burden."),
    (50, 100, 18, "Satisfactory", "Low", "Light particulate stress."),
    (100, 200, 10, "Moderate", "Moderate", "Increased oxidation and pigmentation triggers."),
    (200, 300, 5, "Poor", "High", "High particulate load, barrier strain."),
    (300, 400, 2, "Very Poor", "Critical", "Severe pollution stress."),
    (400, 999, 0, "Severe", "Emergency", "Hazardous pollution, minimize exposure."),
]

UV_THRESHOLDS = [
    (0, 2, 25, "Low", "None", "Low UV strain."),
    (2, 5, 18, "Moderate", "Low", "SPF advised for sustained exposure."),
    (5, 7, 12, "High", "Moderate", "Photoaging risk active."),
    (7, 10, 5, "Very High", "High", "Rapid UV damage without strong SPF."),
    (10, 20, 0, "Extreme", "Critical", "Extreme UV risk window."),
]

HUMIDITY_THRESHOLDS = [
    (0, 10, 0, "Critical Low", "Critical", "Very high transepidermal water loss risk."),
    (10, 20, 5, "Very Low", "High", "Pronounced dryness risk."),
    (20, 30, 12, "Low", "Moderate", "Mild dehydration pressure."),
    (30, 60, 25, "Optimal", "None", "Balanced hydration environment."),
    (60, 80, 12, "High", "Moderate", "Higher pore congestion probability."),
    (80, 90, 5, "Very High", "High", "Very humid, fungal breakout risk rises."),
    (90, 100, 0, "Extreme", "Critical", "Excessive humidity and skin stress risk."),
]

SEVERITY_BANDS = [
    (85, 100, "Paradise Mode", "#27AE60", "🏖️"),
    (70, 84, "Smooth Sailing", "#2ECC71", "⛵"),
    (50, 69, "Guard Up", "#F39C12", "🛡️"),
    (30, 49, "Battle Stations", "#E67E22", "⚔️"),
    (15, 29, "Hostile Mode", "#E74C3C", "🔥"),
    (0, 14, "Code Red", "#C0392B", "🚨"),
]

SCENARIO_THRESHOLDS = {
    "temp_high": 30,
    "aqi_high": 100,
    "uvi_high": 6,
    "humidity_high": 60,
}

THREAT_PRIORITY = ["uv_index", "aqi", "temperature", "humidity"]

SPF_REAPPLY_INTERVALS = {
    "extreme_heat": 60,
    "hot": 90,
    "warm": 120,
    "default": 120,
}

FITZPATRICK_MULTIPLIERS = {1: 2.5, 2: 3.0, 3: 5.0, 4: 6.7, 5: 10.0, 6: 15.0}
DEFAULT_FITZPATRICK = 4

