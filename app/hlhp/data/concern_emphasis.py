from app.hlhp.models.profile import SkinConcern

CONCERN_KEY_DONTS = {
    SkinConcern.ACNE: {
        "high_humidity": "Do not touch your face often - sweat and bacteria can trigger breakouts quickly.",
        "low_humidity": "Do not skip moisturizer when oily - use a water-gel instead of going bare.",
        "high_aqi": "Do not sleep without cleansing off pollution and sunscreen thoroughly.",
        "default": "Do not use heavy occlusive textures when congestion risk is high.",
    },
    SkinConcern.PIGMENTATION: {
        "high_uv": "Do not rely on one sunscreen application all day - reapplication matters most.",
        "high_aqi": "Do not assume overcast means safe from dark-spot triggers; pollution still drives them.",
        "default": "Do not skip broad-spectrum SPF even on mild or cloudy days.",
    },
    SkinConcern.AGING: {
        "high_uv": "Do not skip antioxidant support under SPF in strong UV conditions.",
        "high_aqi": "Do not delay protection - pollution aging damage accumulates invisibly.",
        "low_humidity": "Do not overuse strong actives on visibly dehydrated skin.",
        "default": "Do not ignore neck and hands in daily protection.",
    },
    SkinConcern.SENSITIVITY: {
        "high_uv": "Do not introduce new active products during UV-heavy stress days.",
        "high_aqi": "Do not layer many actives at once when barrier is already inflamed.",
        "default": "Do not experiment with new products on reactive days.",
    },
    SkinConcern.DEHYDRATION: {
        "low_humidity": "Do not apply hyaluronic acid on dry skin - apply on damp skin and seal.",
        "default": "Do not use stripping cleansers until hydration recovers.",
    },
}


def _cluster(env_data) -> str:
    uv_high = env_data.uv_index >= 6
    temp_hot = env_data.temperature_c >= 30
    aqi_high = env_data.aqi > 100
    hum_high = env_data.humidity_pct >= 60
    hum_low = env_data.humidity_pct < 30

    if uv_high and temp_hot:
        return "high_uv_hot"
    if uv_high:
        return "high_uv"
    if aqi_high:
        return "high_aqi"
    if hum_high:
        return "high_humidity"
    if hum_low:
        return "low_humidity"
    return "mild"


def get_concern_key_dont(concern: SkinConcern, env_data) -> str | None:
    concern_donts = CONCERN_KEY_DONTS.get(concern, {})
    cluster = _cluster(env_data)
    return concern_donts.get(cluster) or concern_donts.get("default")
