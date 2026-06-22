from app.hlhp.models.profile import Gender

LANGUAGE_SWAPS = {
    Gender.MALE: {
        "gentle cleanser": "face wash",
        "Gentle cleanser": "Face wash",
        "moisturizer": "face moisturizer",
        "Moisturizer": "Face moisturizer",
        "blotting sheets": "oil control wipes",
    },
    Gender.FEMALE: {},
    Gender.OTHER: {},
    Gender.PREFER_NOT_TO_SAY: {},
}


def apply_language_swap(text: str, gender: Gender) -> str:
    swaps = LANGUAGE_SWAPS.get(gender, {})
    for src, dst in swaps.items():
        text = text.replace(src, dst)
    return text


def get_gender_tip(gender: Gender, env_data) -> str | None:
    if gender == Gender.MALE:
        if env_data.humidity_pct >= 60 or env_data.aqi > 100:
            return (
                "Beard tip: cleanse beard and underlying skin at night; humidity and pollution can trap debris."
            )
        if env_data.humidity_pct < 30:
            return "Shaving tip: use hydrating shave cream and moisturize immediately post shave."

    if gender == Gender.FEMALE and env_data.temperature_c >= 30:
        if env_data.humidity_pct >= 60:
            return "Makeup tip: prefer fluid SPF base and light setting powder in heat-humidity days."
        return "Makeup tip: use lighter base coverage in heat to reduce congestion and slippage."
    return None
