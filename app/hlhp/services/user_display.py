"""Resolve display first name from merged profile / account documents."""

from __future__ import annotations

from typing import Any


def extract_first_name_from_doc(doc: dict[str, Any] | None) -> str:
    """Best-effort first name from flat or nested SkinBB profile shapes."""
    if not doc:
        return ""

    candidates: list[str] = []

    def _push(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    for key in (
        "firstName",
        "first_name",
        "frontName",
        "displayName",
        "userName",
        "username",
    ):
        _push(doc.get(key))

    account = doc.get("account")
    if isinstance(account, dict):
        for key in ("firstName", "first_name", "name"):
            _push(account.get(key))

    _push(doc.get("name"))
    if not candidates and isinstance(doc.get("name"), str):
        parts = doc["name"].strip().split()
        if parts:
            candidates.append(parts[0])

    if not candidates:
        return ""

    return candidates[0].split()[0]
