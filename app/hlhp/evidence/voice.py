"""Glossary-driven L1 voice validation and runtime sanitisation."""

from __future__ import annotations

import re
from typing import Any

_CLOCK_TIME_RE = re.compile(
    r"\b\d{1,2}\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b",
    re.I,
)
# Consumer L1 should not quote study statistics; allow "SPF 50" style product labels.
_PERCENT_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%")
_FDA_RE = re.compile(r"\bFDA\b(?!\s*/\s*US)")
_INCI_ALLOWED = {"ceramides"}

_PERCENT_OF_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*%\s+of\s+",
    re.I,
)
_RANGE_PERCENT_RE = re.compile(r"\b\d+\s*[–-]\s*\d+\s*%")
_OVER_PERCENT_RE = re.compile(
    r"\b(?:over|above|more than)\s+\d+(?:\.\d+)?\s*%",
    re.I,
)


def _lay_fraction(pct: float) -> str:
    if pct >= 90:
        return "nearly all of the "
    if pct >= 70:
        return "most of the "
    if pct >= 50:
        return "about half of the "
    if pct >= 30:
        return "a large share of the "
    return "some of the "


def sanitize_l1_percentages(text: str) -> str:
    """Rewrite study percentages in consumer L1 into plain language."""

    def of_repl(match: re.Match[str]) -> str:
        return _lay_fraction(float(match.group(1)))

    text = _PERCENT_OF_RE.sub(of_repl, text)
    text = _RANGE_PERCENT_RE.sub("substantially more ", text)
    text = _OVER_PERCENT_RE.sub("most of the ", text)
    text = re.sub(
        r"\b(?:about|around|roughly|approximately|filters?|blocks?)\s+(\d+(?:\.\d+)?)\s*%",
        lambda m: f"{'filters' if 'filter' in m.group(0).lower() else 'blocks' if 'block' in m.group(0).lower() else 'about'} "
        f"{'most' if float(m.group(1)) >= 70 else 'much'}",
        text,
        flags=re.I,
    )
    return text

# Stats glossary — use explicit patterns only (never split "OR" / "RR" as words).
_STATS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"p\s*<\s*0\.0[15]", re.I), "p-value"),
    (re.compile(r"\b95%\s*CI\b", re.I), "95% CI"),
    (re.compile(r"\bn\s*=\s*\d+", re.I), "sample size n="),
    (re.compile(r"\bSMD\b"), "SMD"),
    (re.compile(r"\bOR\s*=\s*[\d.]+", re.I), "odds ratio"),
    (re.compile(r"\bRR\s*=\s*[\d.]+", re.I), "relative risk"),
    (re.compile(r"\bHR\s*=\s*[\d.]+", re.I), "hazard ratio"),
]


def _molecule_chemistry_patterns(
    glossary: list[dict[str, Any]],
) -> list[tuple[str, str, re.Pattern[str]]]:
    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for entry in glossary:
        category = (entry.get("category") or "").strip()
        term = (entry.get("term") or "").strip()
        if category not in {"Molecule", "Chemistry", "Unit", "Greek"} or not term:
            continue
        if category == "Unit":
            continue
        for part in re.split(r"\s*/\s*", term):
            part = part.strip()
            if not part or len(part) < 4 or part.lower() in _INCI_ALLOWED:
                continue
            if part.upper() in {"OR", "RR", "HR", "ROS", "PAH", "SC"}:
                continue
            escaped = re.escape(part).replace(r"\-", r"[-]?")
            patterns.append(
                (category, part, re.compile(rf"\b{escaped}\b", re.I)),
            )
    return patterns


def _acronym_patterns(glossary: list[dict[str, Any]]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for entry in glossary:
        if (entry.get("category") or "").strip() != "Acronym":
            continue
        term = (entry.get("term") or "").strip()
        if term.upper() in {"UVI", "MED", "TEWL"}:
            patterns.append((term, re.compile(rf"\b{re.escape(term)}\b", re.I)))
    return patterns


def validate_l1_voice(
    findings: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
) -> list[dict[str, str]]:
    mol_chem = _molecule_chemistry_patterns(glossary)
    acronyms = _acronym_patterns(glossary)
    issues: list[dict[str, str]] = []

    for row in findings:
        row_id = row["id"]
        for field in ("alert_l1_guest", "alert_l1_personalised"):
            text = row.get(field) or ""
            if not text:
                continue
            if _CLOCK_TIME_RE.search(text):
                issues.append(
                    {
                        "row_id": row_id,
                        "field": field,
                        "rule": "clock_time",
                        "detail": "clock-time phrase in L1",
                    }
                )
            if _PERCENT_RE.search(text):
                issues.append(
                    {
                        "row_id": row_id,
                        "field": field,
                        "rule": "percentage",
                        "detail": "percentage in L1",
                    }
                )
            if _FDA_RE.search(text):
                issues.append(
                    {
                        "row_id": row_id,
                        "field": field,
                        "rule": "fda",
                        "detail": "FDA without US qualifier",
                    }
                )
            for pattern, label in _STATS_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        {
                            "row_id": row_id,
                            "field": field,
                            "rule": "glossary_stats",
                            "detail": f"stats phrase '{label}'",
                        }
                    )
            for category, term, pattern in mol_chem:
                if pattern.search(text):
                    issues.append(
                        {
                            "row_id": row_id,
                            "field": field,
                            "rule": f"glossary_{category.lower()}",
                            "detail": f"banned jargon '{term}'",
                        }
                    )
            for term, pattern in acronyms:
                if pattern.search(text):
                    issues.append(
                        {
                            "row_id": row_id,
                            "field": field,
                            "rule": "glossary_acronym",
                            "detail": f"prefer lay term over '{term}'",
                        }
                    )
    return issues


def apply_lay_voice(text: str, glossary: list[dict[str, Any]]) -> str:
    """Best-effort runtime sanitisation using glossary lay translations."""
    if not text:
        return text
    result = text
    for entry in glossary:
        term = (entry.get("term") or "").strip()
        lay = (entry.get("lay_translation") or "").strip()
        category = (entry.get("category") or "").strip()
        if not term or not lay or category not in {"Acronym", "Molecule"}:
            continue
        for part in term.split("/"):
            part = part.strip()
            if not part or part.lower() in _INCI_ALLOWED or len(part) < 3:
                continue
            replacement = lay.split("—")[0].split("=")[0].strip()
            if len(replacement) > 60:
                continue
            result = re.sub(rf"\b{re.escape(part)}\b", replacement, result, flags=re.I)
    return result
