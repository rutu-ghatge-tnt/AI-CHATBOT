from __future__ import annotations

from app.label_looker.engines.base_formula.matrices import (
    lookup_alcohol_score,
    lookup_carrier_score,
    lookup_finish_score,
    lookup_fragrance_score,
    lookup_texture_score,
)
from app.label_looker.engines.base_formula.types import BaseFormulaRecord, BaseFormulaScore, MATRIX_SCORE_VALUES, RuntimeContext

AXIS_WEIGHTS_DEFAULT = {"texture": 0.50, "carrier": 0.25, "fragrance": 0.15, "alcohol": 0.10}
AXIS_WEIGHTS_WITH_FINISH = {"texture": 0.40, "carrier": 0.20, "fragrance": 0.15, "alcohol": 0.10, "finish": 0.15}


def score_base_formula(ctx: RuntimeContext, base_formula: BaseFormulaRecord) -> BaseFormulaScore:
    has_finish = bool(base_formula.get("finish"))
    weights = AXIS_WEIGHTS_WITH_FINISH if has_finish else AXIS_WEIGHTS_DEFAULT
    details = []

    m, n = lookup_texture_score(base_formula.get("texture", "lotion"), ctx["skin_type"], ctx["season"])
    details.append(_detail("texture", m, weights["texture"], n))
    m, n = lookup_carrier_score(base_formula.get("continuous_phase", "aqueous"), ctx["skin_type"], ctx["season"], bool(ctx["flags"].get("acne_prone")))
    details.append(_detail("carrier", m, weights["carrier"], n))
    m, n = lookup_fragrance_score(base_formula.get("fragrance_level", "none"), ctx["flags"])
    details.append(_detail("fragrance", m, weights["fragrance"], n))
    m, n = lookup_alcohol_score(base_formula.get("alcohol_level", "none"), ctx["skin_type"], ctx["flags"])
    details.append(_detail("alcohol", m, weights["alcohol"], n))
    if has_finish:
        m, n = lookup_finish_score(base_formula["finish"], ctx["skin_type"])
        details.append(_detail("finish", m, weights["finish"], n))

    total = sum(d["contribution"] for d in details)
    return BaseFormulaScore(
        total=max(0.0, total),
        details=details,
        has_finish_axis=has_finish,
        rationale_strings=[d["note"] for d in details],
    )


def _detail(axis: str, matrix_score: str, weight: float, note: str) -> dict:
    numeric = MATRIX_SCORE_VALUES.get(matrix_score, 5)
    return {
        "axis": axis,
        "matrix_score": matrix_score,
        "numeric": numeric,
        "weight": weight,
        "contribution": (numeric / 10.0) * 15.0 * weight,
        "note": note,
    }

