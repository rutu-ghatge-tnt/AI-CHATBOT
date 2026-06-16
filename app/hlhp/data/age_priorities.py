from app.hlhp.models.profile import AgeBracket

AGE_STEP_PRIORITY = {
    AgeBracket.AGE_18_24: {
        "priority_order": ["treatment", "sunscreen", "serum"],
        "evening_template": (
            "{cleanser} -> Salicylic/BHA support -> Lightweight moisturizer -> Spot care as needed"
        ),
    },
    AgeBracket.AGE_25_30: {
        "priority_order": ["sunscreen", "serum", "moisturizer"],
        "evening_template": (
            "{cleanser} -> Niacinamide/Vitamin C -> Lightweight moisturizer -> Retinol 1-2x weekly"
        ),
    },
    AgeBracket.AGE_31_40: {
        "priority_order": ["sunscreen", "serum", "moisturizer"],
        "evening_template": (
            "{cleanser} -> Antioxidant serum -> Retinoid alternate nights -> Peptide moisturizer"
        ),
    },
    AgeBracket.AGE_41_50: {
        "priority_order": ["serum", "sunscreen", "moisturizer"],
        "evening_template": (
            "{cleanser} -> Retinoid/repair serum -> Rich night cream -> Targeted eye and neck care"
        ),
    },
    AgeBracket.AGE_50_PLUS: {
        "priority_order": ["moisturizer", "sunscreen", "serum"],
        "evening_template": (
            "{cleanser} -> Ceramide-rich serum -> Rich peptide cream -> Occlusive support if dry"
        ),
    },
}


def get_age_priority(age_bracket: AgeBracket) -> dict:
    return AGE_STEP_PRIORITY.get(age_bracket, AGE_STEP_PRIORITY[AgeBracket.AGE_25_30])


def reorder_steps_by_age(steps: list, age_bracket: AgeBracket) -> list:
    priority = get_age_priority(age_bracket)["priority_order"]

    def _sort(step):
        return priority.index(step.product_category) if step.product_category in priority else len(priority)

    ordered = sorted(steps, key=_sort)
    for i, step in enumerate(ordered, start=1):
        step.step_number = i
    return ordered
