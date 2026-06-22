from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _scalar(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        if len(raw) == 1:
            return _scalar(raw[0])
        return None
    if isinstance(raw, str):
        t = raw.strip()
        return t if t else None
    if isinstance(raw, (int, float, bool)):
        return raw
    if isinstance(raw, dict):
        for k in ("value", "label", "name", "slug"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return raw


def _list_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        t = raw.strip()
        return [t] if t else []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            for k in ("value", "label", "name"):
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                    break
    return list(dict.fromkeys(out))


def _parse_age(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str) and raw.strip():
        m = re.search(r"\d+", raw.strip())
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return None
    return None


def _age_from_dob(raw: Any) -> int | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            born = datetime.strptime(text, fmt)
            today = datetime.now()
            years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            return years if years >= 0 else None
        except ValueError:
            continue
    return None


# Keys the Label Looker scan gate requires per product mode (not expectedBenefit — per scan).
_SCAN_REQUIRED_BY_MODE: dict[str, list[str]] = {
    "skincare": ["age", "gender", "skinType", "skinConcerns"],
    "haircare": ["age", "gender", "hairType", "hairConcerns"],
    "lipcare": ["age", "gender", "lipType", "lipConcerns"],
}

# Full edit-profile form schema (section → fields). `requiredForScan` modes list when field counts for scan gate.
_FORM_SCHEMA: list[dict[str, Any]] = [
    {"key": "firstName", "section": "account", "label": "First name", "requiredForScan": []},
    {"key": "lastName", "section": "account", "label": "Last name", "requiredForScan": []},
    {"key": "username", "section": "account", "label": "Username", "requiredForScan": []},
    {"key": "email", "section": "account", "label": "Email", "requiredForScan": []},
    {"key": "mobile", "section": "account", "label": "Mobile", "requiredForScan": []},
    {"key": "city", "section": "account", "label": "City", "requiredForScan": []},
    {"key": "state", "section": "account", "label": "State", "requiredForScan": []},
    {"key": "country", "section": "account", "label": "Country", "requiredForScan": []},
    {"key": "bio", "section": "account", "label": "Bio", "requiredForScan": []},
    {"key": "instagram", "section": "account", "label": "Instagram", "requiredForScan": []},
    {"key": "age", "section": "identity", "label": "Age", "requiredForScan": ["skincare", "haircare", "lipcare"]},
    {"key": "gender", "section": "identity", "label": "Identify as", "requiredForScan": ["skincare", "haircare", "lipcare"]},
    {"key": "bornOn", "section": "identity", "label": "Born on", "requiredForScan": []},
    {"key": "weight", "section": "body", "label": "Weight", "requiredForScan": []},
    {"key": "height", "section": "body", "label": "Height", "requiredForScan": []},
    {"key": "skinType", "section": "skin", "label": "Skin type", "requiredForScan": ["skincare", "lipcare"]},
    {"key": "skinTone", "section": "skin", "label": "Skin tone", "requiredForScan": []},
    {"key": "skinConcerns", "section": "skin", "label": "Skin concerns", "requiredForScan": ["skincare", "lipcare"]},
    {"key": "skinGoals", "section": "skin", "label": "Skin goals", "requiredForScan": []},
    {"key": "hairType", "section": "hair", "label": "Hair type", "requiredForScan": ["haircare"]},
    {"key": "hairConcerns", "section": "hair", "label": "Hair concerns", "requiredForScan": ["haircare"]},
    {"key": "hairGoals", "section": "hair", "label": "Hair goals", "requiredForScan": []},
    {"key": "scalpConcern", "section": "analysis", "label": "Scalp concern", "requiredForScan": []},
    {"key": "environmentAssessment", "section": "analysis", "label": "Environment assessment", "requiredForScan": []},
    {"key": "screenTime", "section": "analysis", "label": "Screen time", "requiredForScan": []},
    {"key": "breakPattern", "section": "analysis", "label": "Break pattern", "requiredForScan": []},
    {"key": "stressLevel", "section": "analysis", "label": "Stress level", "requiredForScan": []},
]

# Mongo / auth source keys per form key (first match wins).
_SOURCE_ALIASES: dict[str, list[str]] = {
    "firstName": ["firstName", "first_name"],
    "lastName": ["lastName", "last_name"],
    "username": ["username", "userName", "profileUrl"],
    "email": ["email"],
    "mobile": ["mobile", "phone", "phoneNumber", "mobileNumber"],
    "city": ["city"],
    "state": ["state"],
    "country": ["country"],
    "bio": ["bio", "about"],
    "instagram": ["instagram", "instagramHandle"],
    "age": ["age", "ageYears", "age_years", "ageValue"],
    "gender": ["gender", "Gender", "identifyAs"],
    "bornOn": ["bornOn", "born_on", "dateOfBirth", "dob", "birthDate"],
    "weight": ["weight", "weightKg", "weight_kg"],
    "height": ["height", "heightCm", "height_cm"],
    "skinType": ["skinType", "skin_type"],
    "skinTone": ["skinTone", "skin_tone"],
    "skinConcerns": ["skinConcerns", "skin_concerns"],
    "skinGoals": ["skinGoals", "skin_goals"],
    "hairType": ["hairType", "hair_type"],
    "hairConcerns": ["hairConcerns", "hair_concerns"],
    "hairGoals": ["hairGoals", "hair_goals"],
    "scalpConcern": ["scalpConcern", "scalp_concern", "scalpConcerns"],
    "environmentAssessment": ["environmentAssessment", "environment_assessment"],
    "screenTime": ["screenTime", "screen_time", "sleepDurations"],
    "breakPattern": ["breakPattern", "break_pattern"],
    "stressLevel": ["stressLevel", "stress_level"],
}


def _read_field(sources: list[dict[str, Any]], key: str) -> Any:
    aliases = _SOURCE_ALIASES.get(key, [key])
    for src in sources:
        for alias in aliases:
            if alias not in src:
                continue
            raw = src.get(alias)
            if key in ("skinConcerns", "skinGoals", "hairConcerns", "hairGoals"):
                vals = _list_values(raw)
                if vals:
                    return vals
            else:
                val = _scalar(raw)
                if _is_present(val):
                    return val
    if key == "age":
        for src in sources:
            for alias in ("bornOn", "born_on", "dateOfBirth", "dob", "birthDate"):
                computed = _age_from_dob(src.get(alias))
                if computed is not None:
                    return computed
    if key == "lipType":
        for src in sources:
            v = _scalar(src.get("lipType") or src.get("skinType"))
            if _is_present(v):
                return v
    if key == "lipConcerns":
        for src in sources:
            vals = _list_values(src.get("lipConcerns") or src.get("skinConcerns"))
            if vals:
                return vals
    return None


def build_profile_form_values(*, details: dict[str, Any], auth_user: dict[str, Any] | None) -> dict[str, Any]:
    """Nested form payload for Edit profile UI — every section prefilled when data exists."""
    sources = [details, auth_user or {}]
    flat: dict[str, Any] = {}
    for row in _FORM_SCHEMA:
        key = row["key"]
        val = _read_field(sources, key)
        if key == "age":
            val = _parse_age(val)
        flat[key] = val

    return {
        "account": {
            "firstName": flat.get("firstName"),
            "lastName": flat.get("lastName"),
            "username": flat.get("username"),
            "email": flat.get("email"),
            "mobile": flat.get("mobile"),
            "city": flat.get("city"),
            "state": flat.get("state"),
            "country": flat.get("country"),
            "bio": flat.get("bio"),
            "instagram": flat.get("instagram"),
        },
        "identity": {
            "age": flat.get("age"),
            "gender": flat.get("gender"),
            "bornOn": flat.get("bornOn"),
        },
        "body": {
            "weight": flat.get("weight"),
            "height": flat.get("height"),
        },
        "skin": {
            "skinType": flat.get("skinType"),
            "skinTone": flat.get("skinTone"),
            "skinConcerns": flat.get("skinConcerns") or [],
            "skinGoals": flat.get("skinGoals") or [],
        },
        "hair": {
            "hairType": flat.get("hairType"),
            "hairConcerns": flat.get("hairConcerns") or [],
            "hairGoals": flat.get("hairGoals") or [],
        },
        "analysis": {
            "scalpConcern": flat.get("scalpConcern"),
            "environmentAssessment": flat.get("environmentAssessment"),
            "screenTime": flat.get("screenTime"),
            "breakPattern": flat.get("breakPattern"),
            "stressLevel": flat.get("stressLevel"),
        },
        "flat": flat,
    }


def assess_profile_completeness(*, details: dict[str, Any], auth_user: dict[str, Any] | None, mode: str = "skincare") -> dict[str, Any]:
    form = build_profile_form_values(details=details, auth_user=auth_user)
    flat = dict(form["flat"])
    mode_norm = mode if mode in _SCAN_REQUIRED_BY_MODE else "skincare"
    scan_required_keys = list(_SCAN_REQUIRED_BY_MODE.get(mode_norm, _SCAN_REQUIRED_BY_MODE["skincare"]))

    # Lipcare gate uses lipType/lipConcerns; form stores skinType/skinConcerns.
    if mode_norm == "lipcare":
        if not _is_present(flat.get("skinType")):
            lip = _read_field([details, auth_user or {}], "lipType")
            if _is_present(lip):
                flat["skinType"] = lip
        if not _is_present(flat.get("skinConcerns")):
            lip_c = _read_field([details, auth_user or {}], "lipConcerns")
            if _is_present(lip_c):
                flat["skinConcerns"] = lip_c

    scan_key_to_form_key = {
        "lipType": "skinType",
        "lipConcerns": "skinConcerns",
    }

    field_status: dict[str, dict[str, Any]] = {}
    missing_for_scan: list[str] = []
    missing_details: list[dict[str, Any]] = []
    highlight_keys: list[str] = []

    for row in _FORM_SCHEMA:
        key = row["key"]
        val = flat.get(key)
        present = _is_present(val)
        required_for_scan = any(
            scan_key_to_form_key.get(req, req) == key or req == key for req in scan_required_keys
        )
        missing = required_for_scan and not present
        field_status[key] = {
            "present": present,
            "value": val,
            "section": row["section"],
            "label": row["label"],
            "requiredForScan": required_for_scan,
            "missing": missing,
            "highlight": missing,
        }
        if missing:
            missing_for_scan.append(key)
            missing_details.append(
                {
                    "key": key,
                    "section": row["section"],
                    "label": row["label"],
                }
            )
            highlight_keys.append(key)

    return {
        "mode": mode_norm,
        "form": form,
        "fieldStatus": field_status,
        "missingFields": missing_for_scan,
        "missingFieldDetails": missing_details,
        "highlightFields": highlight_keys,
        "hasRequiredForScan": len(missing_for_scan) == 0,
        "requiredFieldsForScan": scan_required_keys,
    }


def profile_updates_from_form_body(body: dict[str, Any]) -> dict[str, Any]:
    """Map edit-profile form POST/PATCH body → Mongo user_details keys."""
    flat: dict[str, Any] = {}
    if isinstance(body.get("flat"), dict):
        flat.update(body["flat"])
    for section_key in ("account", "identity", "body", "skin", "hair", "analysis"):
        section = body.get(section_key)
        if isinstance(section, dict):
            flat.update(section)
    # Legacy nested category_profiles
    cp = body.get("category_profiles") or body.get("categoryProfiles")
    if isinstance(cp, dict):
        skin = cp.get("skin")
        if isinstance(skin, dict):
            if skin.get("type") is not None:
                flat.setdefault("skinType", skin.get("type"))
            if skin.get("concerns") is not None:
                flat.setdefault("skinConcerns", skin.get("concerns"))
            if skin.get("benefits_wanted") is not None:
                flat.setdefault("skinGoals", skin.get("benefits_wanted"))
        hair = cp.get("hair")
        if isinstance(hair, dict):
            if hair.get("type") is not None:
                flat.setdefault("hairType", hair.get("type"))
            if hair.get("concerns") is not None:
                flat.setdefault("hairConcerns", hair.get("concerns"))
            if hair.get("benefits_wanted") is not None:
                flat.setdefault("hairGoals", hair.get("benefits_wanted"))

    updates: dict[str, Any] = {}
    list_keys = {"skinConcerns", "skinGoals", "hairConcerns", "hairGoals"}
    for key, val in flat.items():
        if key not in {r["key"] for r in _FORM_SCHEMA}:
            continue
        if key in list_keys:
            if isinstance(val, list):
                updates[key] = _list_values(val)
            elif val is not None:
                updates[key] = _list_values(val)
        elif key == "age":
            parsed = _parse_age(val)
            if parsed is not None:
                updates["age"] = parsed
        elif val is not None:
            updates[key] = _scalar(val)
    return updates
