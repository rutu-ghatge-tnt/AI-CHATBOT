from app.hl_engine.models.personalized_alert import HairAlert, HairAlertStep
from app.hl_engine.models.profile import HairConcern, HairType, UserProfile

HAIR_TYPE_IMPACTS = {
    HairType.STRAIGHT: {
        "high_humidity": "Roots can get oily and flat quickly in this humidity.",
        "low_humidity": "Static and flyaways increase in dry air.",
        "high_uv": "UV can reduce shine and increase brittleness.",
        "high_aqi": "Pollution residue can make strands dull and gritty.",
    },
    HairType.WAVY: {
        "high_humidity": "Wave definition may collapse into frizz.",
        "low_humidity": "Waves may feel brittle and rough.",
        "high_uv": "UV can weaken pattern and moisture balance.",
        "high_aqi": "Pollution buildup can increase scalp irritation.",
    },
    HairType.CURLY: {
        "high_humidity": "Humidity can trigger frizz and shape instability.",
        "low_humidity": "Curls can dry out rapidly and snap easier.",
        "high_uv": "UV can worsen dryness and roughness.",
        "high_aqi": "Coils can trap more particulate buildup.",
    },
    HairType.COILY: {
        "high_humidity": "Excess humidity can cause swelling and frizz.",
        "low_humidity": "High breakage risk in dry conditions.",
        "high_uv": "UV stress can increase fragility quickly.",
        "high_aqi": "Pollution can settle deep and irritate scalp.",
    },
    HairType.THINNING: {
        "high_humidity": "Humidity can make thinning appear more visible.",
        "low_humidity": "Dryness can increase fragility and shedding.",
        "high_uv": "Exposed scalp areas are at greater UV risk.",
        "high_aqi": "Pollution can worsen scalp stress around follicles.",
    },
}

HAIR_CONCERN_PROTOCOLS = {
    HairConcern.FRIZZ: {
        "trigger": lambda env: env.humidity_pct >= 60,
        "steps": [
            HairAlertStep(action="Apply anti-humidity leave-in on damp hair.", reason="It reduces moisture swelling and frizz expansion."),
            HairAlertStep(action="Minimize touching once hair sets.", reason="Friction breaks curl/wave definition and increases frizz."),
        ],
        "key_dont": "Do not use rough towels; use microfiber or a soft cotton T-shirt.",
    },
    HairConcern.DRYNESS: {
        "trigger": lambda env: env.humidity_pct < 30,
        "steps": [
            HairAlertStep(action="Use leave-in conditioner and seal lightly with oil.", reason="Dry air strips moisture quickly from strands."),
            HairAlertStep(action="Reduce wash frequency temporarily.", reason="Frequent wash can worsen moisture loss."),
        ],
        "key_dont": "Do not heat-style on already dehydrated hair.",
    },
    HairConcern.THINNING: {
        "trigger": lambda env: env.uv_index >= 6,
        "steps": [
            HairAlertStep(action="Use UV-protective spray around part lines.", reason="UV stress can worsen follicle and scalp strain."),
            HairAlertStep(action="Use hat/scarf for prolonged outdoor exposure.", reason="Physical shielding protects exposed scalp zones."),
        ],
        "key_dont": "Do not use tight hairstyles that pull on thinning areas.",
    },
}


def generate_hair_alert(profile: UserProfile, env) -> HairAlert | None:
    if not profile.has_hair_profile:
        return None

    condition = None
    if env.humidity_pct >= 60:
        condition = "high_humidity"
    elif env.humidity_pct < 30:
        condition = "low_humidity"
    elif env.uv_index >= 6:
        condition = "high_uv"
    elif env.aqi > 100:
        condition = "high_aqi"
    if not condition:
        return None

    impact = HAIR_TYPE_IMPACTS.get(profile.hair_type, {}).get(condition, "Hair condition is affected by current weather stress.")
    steps = []
    concern_used = "general"
    key_dont = "Avoid aggressive styling and keep scalp clean."

    for concern in profile.hair_concerns:
        protocol = HAIR_CONCERN_PROTOCOLS.get(concern)
        if protocol and protocol["trigger"](env):
            steps = protocol["steps"]
            key_dont = protocol["key_dont"]
            concern_used = concern.value
            break

    if not steps:
        steps = [HairAlertStep(action="Use protective leave-in support.", reason="It helps reduce environmental stress on hair.")]

    return HairAlert(
        whats_happening=impact,
        do_steps=steps,
        key_dont=key_dont,
        hair_type_used=profile.hair_type.value,
        hair_concern_used=concern_used,
    )
