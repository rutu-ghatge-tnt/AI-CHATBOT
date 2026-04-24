"""
Sync filter images to existing SkinTruth taxonomy documents.

Behavior:
- Reads image files from Filters taxonomy folders.
- Fetches existing records from taxonomy collections via admin APIs.
- Matches image file names to existing labels/values only (no create).
- Applies taxonomy-specific alias maps to handle naming variants/typos.
- Uses deterministic normalization first, then Claude for ambiguous/fallback matches.
- Updates matched existing documents with multipart PUT (appIcon/webIcon).
- Optional strict mode skips updates when records already have icons.

Usage:
  python scripts/sync_filter_icons_to_taxonomies.py --dry-run
  python scripts/sync_filter_icons_to_taxonomies.py --apply
  python scripts/sync_filter_icons_to_taxonomies.py --apply --strict-skip-existing-icons
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from anthropic import Anthropic
from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.skintruth.in/api/v1"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
PAGE_SIZE = 100

TAXONOMY_CONFIG = {
    "skin-types": "Skintypes",
    "hair-types": "Hairtypes",
    "skin-concerns": "Skin concerns",
    "hair-concerns": "Hair concerns",
}

TAXONOMY_ALIASES: Dict[str, Dict[str, str]] = {
    "hair-concerns": {
        "hair thining": "thinning hair",
        "thinning": "thinning hair",
        "hairfall": "hair fall",
        "hair fall": "hair fall",
        "hair-fall": "hair fall",
        "splitends": "split ends",
        "scalp itch": "scalp itchiness",
        "sensitive scalp": "scalp sensitivity",
        "no specific": "no specific",
    },
    "skin-concerns": {
        "oiliness 1": "oiliness",
        "dryness 1": "dryness",
        "pigmentation 1": "pigmentation",
        "stretch marks 1": "stretch marks",
        "acne 1": "acne",
        "remove bg": "skip",
    },
    "hair-types": {
        "hairtype 01": "skip",
        "hairtype 02": "skip",
        "hairtype 03": "skip",
    },
    "skin-types": {},
}


@dataclass
class ExistingRecord:
    record_id: str
    label: str
    value: str
    raw: Dict[str, Any]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_filename(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"\(\d+\)$", "", stem).strip()
    return normalize_text(stem)


def resolve_alias(taxonomy: str, normalized_name: str) -> str:
    alias_map = TAXONOMY_ALIASES.get(taxonomy, {})
    return alias_map.get(normalized_name, normalized_name)


def variants(text: str) -> List[str]:
    base = normalize_text(text)
    out = {base}
    out.add(base.replace(" and ", " "))
    out.add(base.replace(" hair ", " "))
    out.add(base.replace(" scalp ", " "))
    out.add(base.replace("fall", " fall"))
    out.add(base.replace("thining", "thinning"))
    out.add(base.replace("splitends", "split ends"))
    return [x.strip() for x in out if x.strip()]


def pick_id(raw: Dict[str, Any]) -> Optional[str]:
    for key in ("id", "_id"):
        value = raw.get(key)
        if value is not None:
            return str(value)
    return None


def extract_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "docs", "results", "rows", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        # Common API pattern: data: { skinTypes: [...]} etc.
        for value in data.values():
            if isinstance(value, list):
                return value
    for key in ("items", "docs", "results", "rows", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    # Last-resort shallow scan for any top-level list
    for value in payload.values():
        if isinstance(value, list):
            return value
    return []


def list_all_records(
    base_url: str, token: str, taxonomy: str, timeout_sec: int = 60
) -> List[ExistingRecord]:
    page = 1
    records: List[ExistingRecord] = []
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        url = f"{base_url}/{taxonomy}"
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={"page": page, "limit": PAGE_SIZE},
                timeout=timeout_sec,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            response = exc.response
            log_event(
                "error",
                "list_http_error",
                taxonomy=taxonomy,
                page=page,
                status_code=response.status_code if response is not None else None,
                response_text=response.text[:800] if response is not None else "",
                url=url,
            )
            break
        except requests.RequestException as exc:
            log_event(
                "error",
                "list_request_error",
                taxonomy=taxonomy,
                page=page,
                error=str(exc),
                url=url,
            )
            break
        payload = resp.json()
        rows = extract_records(payload)
        log_event(
            "info",
            "list_page_fetched",
            taxonomy=taxonomy,
            page=page,
            status_code=resp.status_code,
            payload_keys=list(payload.keys()) if isinstance(payload, dict) else [],
            rows_detected=len(rows),
        )
        if not rows:
            log_event(
                "warning",
                "list_page_empty",
                taxonomy=taxonomy,
                page=page,
                payload_preview=str(payload)[:800],
            )
            break

        for row in rows:
            if not isinstance(row, dict):
                continue
            record_id = pick_id(row)
            label = str(row.get("label", "")).strip()
            value = str(row.get("value", "")).strip() or label
            if record_id and label:
                records.append(
                    ExistingRecord(
                        record_id=record_id,
                        label=label,
                        value=value,
                        raw=row,
                    )
                )

        if len(rows) < PAGE_SIZE:
            break
        page += 1

    return records


def build_index(records: Iterable[ExistingRecord]) -> Dict[str, List[ExistingRecord]]:
    idx: Dict[str, List[ExistingRecord]] = {}
    for record in records:
        keys = variants(record.label) + variants(record.value)
        for key in keys:
            idx.setdefault(key, []).append(record)
    return idx


def ask_claude_best_match(
    client: Anthropic,
    model: str,
    taxonomy: str,
    image_name: str,
    normalized_image_name: str,
    candidates: List[ExistingRecord],
) -> Tuple[Optional[ExistingRecord], float, str]:
    if not candidates:
        return None, 0.0, "No candidates available for Claude matching."

    candidate_labels = [{"id": c.record_id, "label": c.label, "value": c.value} for c in candidates]
    prompt = {
        "task": "Match image filename to best existing taxonomy label.",
        "rules": [
            "Choose exactly one candidate from provided list.",
            "Prioritize semantic equivalence and spelling variants.",
            "If not confident, set confidence below 0.80.",
            "Return JSON only.",
        ],
        "taxonomy": taxonomy,
        "image_file": image_name,
        "normalized_image_name": normalized_image_name,
        "candidates": candidate_labels,
        "output_schema": {
            "chosen_id": "string",
            "confidence": "number in [0,1]",
            "reason": "string",
        },
    }

    msg = client.messages.create(
        model=model,
        max_tokens=350,
        temperature=0,
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
    parsed = _parse_json_from_text(text)
    chosen_id = str(parsed.get("chosen_id", "")).strip()
    confidence = float(parsed.get("confidence", 0.0))
    reason = str(parsed.get("reason", "")).strip()

    matched = next((c for c in candidates if c.record_id == chosen_id), None)
    return matched, confidence, reason


def match_image_to_record(
    image_path: Path,
    taxonomy: str,
    records: List[ExistingRecord],
    index: Dict[str, List[ExistingRecord]],
    claude_client: Optional[Anthropic],
    claude_model: str,
    confidence_threshold: float,
) -> Tuple[Optional[ExistingRecord], Dict[str, Any]]:
    raw_filename_norm = normalize_filename(image_path)
    filename_norm = resolve_alias(taxonomy, raw_filename_norm)
    detail: Dict[str, Any] = {
        "image": str(image_path),
        "taxonomy": taxonomy,
        "raw_normalized_image_name": raw_filename_norm,
        "normalized_image_name": filename_norm,
        "method": "",
        "confidence": None,
        "reason": "",
    }
    if filename_norm == "skip":
        detail["method"] = "taxonomy_alias_skip"
        detail["confidence"] = 1.0
        detail["reason"] = "File mapped to skip by taxonomy alias rules."
        return None, detail

    exact_matches = index.get(filename_norm, [])
    if len(exact_matches) == 1:
        detail["method"] = "deterministic_alias_exact" if raw_filename_norm != filename_norm else "deterministic_exact"
        detail["confidence"] = 1.0
        detail["reason"] = "Single normalized exact match."
        return exact_matches[0], detail
    if len(exact_matches) > 1:
        # If multiple records normalize to the same key, prefer exact label/value text equality.
        for candidate in exact_matches:
            if normalize_text(candidate.label) == filename_norm or normalize_text(candidate.value) == filename_norm:
                detail["method"] = "deterministic_exact_preferred"
                detail["confidence"] = 1.0
                detail["reason"] = "Preferred exact label/value match among duplicate normalized candidates."
                return candidate, detail

    candidate_pool = exact_matches if exact_matches else records

    if claude_client is None:
        if len(candidate_pool) == 1:
            detail["method"] = "deterministic_single_candidate"
            detail["confidence"] = 1.0
            detail["reason"] = "Single candidate without Claude."
            return candidate_pool[0], detail
        detail["method"] = "unmatched_no_claude"
        detail["confidence"] = 0.0
        detail["reason"] = "Ambiguous match and Claude disabled."
        return None, detail

    try:
        match, confidence, reason = ask_claude_best_match(
            client=claude_client,
            model=claude_model,
            taxonomy=taxonomy,
            image_name=image_path.name,
            normalized_image_name=filename_norm,
            candidates=candidate_pool,
        )
        detail["method"] = "claude"
        detail["confidence"] = confidence
        detail["reason"] = reason
        if match and confidence >= confidence_threshold:
            return match, detail
        return None, detail
    except Exception as exc:
        detail["method"] = "claude_error"
        detail["confidence"] = 0.0
        detail["reason"] = f"Claude matching failed: {exc}"
        return None, detail


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Parse JSON from Claude text response.
    Handles plain JSON and fenced JSON blocks.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty Claude response")

    # 1) Direct JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2) Markdown fenced block: ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        parsed = json.loads(fence_match.group(1))
        if isinstance(parsed, dict):
            return parsed

    # 3) First JSON object substring
    obj_match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if obj_match:
        parsed = json.loads(obj_match.group(0))
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Unable to parse JSON from Claude response: {raw[:300]}")


def update_icons(
    base_url: str,
    token: str,
    taxonomy: str,
    record: ExistingRecord,
    image_path: Path,
    timeout_sec: int = 120,
) -> requests.Response:
    url = f"{base_url}/{taxonomy}/{record.record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "label": record.label,
        "value": record.value,
    }

    with image_path.open("rb") as f:
        files = {
            "appIcon": (image_path.name, f, "image/png"),
            "webIcon": (image_path.name, f, "image/png"),
        }
        resp = requests.put(url, headers=headers, data=data, files=files, timeout=timeout_sec)
    return resp


def gather_images(filters_root: Path, relative_dir: str) -> List[Path]:
    folder = filters_root / relative_dir
    if not folder.exists():
        return []
    return sorted(p for p in folder.glob("*.png") if p.is_file())


def has_existing_icons(raw: Dict[str, Any]) -> bool:
    app_icon = raw.get("appIcon")
    web_icon = raw.get("webIcon")

    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            for k in ("url", "path", "key", "fileName", "filename"):
                v = value.get(k)
                if isinstance(v, str) and v.strip():
                    return True
            return bool(value)
        return bool(value)

    return _present(app_icon) or _present(web_icon)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Filters images to existing taxonomy docs.")
    parser.add_argument("--base-url", default=os.getenv("SHOP_API_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--admin-token", default=os.getenv("ADMIN_BEARER_TOKEN", ""))
    parser.add_argument("--filters-root", default="Filters")
    parser.add_argument("--model", default=os.getenv("CLAUDE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--claude-api-key", default=os.getenv("CLAUDE_API_KEY", ""))
    parser.add_argument("--confidence-threshold", type=float, default=0.85)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no PUT calls.")
    parser.add_argument("--apply", action="store_true", help="Execute PUT updates.")
    parser.add_argument(
        "--strict-skip-existing-icons",
        action="store_true",
        help="Never update records that already have appIcon/webIcon.",
    )
    parser.add_argument("--output-dir", default="tmp/filter_icon_sync")
    return parser.parse_args()


def ensure_mode(args: argparse.Namespace) -> bool:
    if args.apply:
        return False
    return True


def clean_env_value(value: str) -> str:
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1].strip()
    return v


def log_event(level: str, message: str, **kwargs: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "message": message,
    }
    if kwargs:
        payload["meta"] = kwargs
    print(json.dumps(payload, ensure_ascii=True))


def main() -> None:
    load_dotenv()
    args = parse_args()
    args.base_url = clean_env_value(args.base_url)
    args.admin_token = clean_env_value(args.admin_token)
    args.claude_api_key = clean_env_value(args.claude_api_key)
    dry_run = ensure_mode(args)

    if not args.admin_token:
        raise SystemExit("Missing admin token. Set ADMIN_BEARER_TOKEN or pass --admin-token.")

    project_root = Path(__file__).resolve().parents[1]
    filters_root = (project_root / args.filters_root).resolve()
    output_dir = (project_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not filters_root.exists():
        raise SystemExit(f"Filters root not found: {filters_root}")

    claude_client = Anthropic(api_key=args.claude_api_key) if args.claude_api_key else None
    log_event(
        "info",
        "run_started",
        mode="dry_run" if dry_run else "apply",
        base_url=args.base_url,
        filters_root=str(filters_root),
        claude_enabled=bool(claude_client),
        strict_skip_existing_icons=bool(args.strict_skip_existing_icons),
        token_present=bool(args.admin_token),
    )

    matched_actions: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    taxonomy_counts: Dict[str, Dict[str, int]] = {}

    for taxonomy, rel_dir in TAXONOMY_CONFIG.items():
        taxonomy_counts[taxonomy] = {
            "images_total": 0,
            "matched_total": 0,
            "matched_deterministic": 0,
            "matched_claude": 0,
            "skipped_unmatched_or_low_confidence": 0,
            "skipped_alias_skip": 0,
            "skipped_existing_icons": 0,
            "put_success": 0,
            "put_failed": 0,
            "put_exception": 0,
        }
        log_event("info", "taxonomy_started", taxonomy=taxonomy, folder=rel_dir)
        records = list_all_records(args.base_url, args.admin_token, taxonomy, timeout_sec=args.timeout_sec)
        log_event("info", "records_fetched", taxonomy=taxonomy, count=len(records))
        idx = build_index(records)

        images = gather_images(filters_root, rel_dir)
        taxonomy_counts[taxonomy]["images_total"] = len(images)
        log_event("info", "images_discovered", taxonomy=taxonomy, count=len(images), folder=rel_dir)

        for image_path in images:
            match, detail = match_image_to_record(
                image_path=image_path,
                taxonomy=taxonomy,
                records=records,
                index=idx,
                claude_client=claude_client,
                claude_model=args.model,
                confidence_threshold=args.confidence_threshold,
            )

            if not match:
                if detail.get("method") == "taxonomy_alias_skip":
                    taxonomy_counts[taxonomy]["skipped_alias_skip"] += 1
                else:
                    taxonomy_counts[taxonomy]["skipped_unmatched_or_low_confidence"] += 1
                skipped.append(
                    {
                        **detail,
                        "status": "unmatched_or_low_confidence",
                    }
                )
                log_event(
                    "warning",
                    "image_skipped",
                    taxonomy=taxonomy,
                    image=image_path.name,
                    method=detail.get("method"),
                    reason=detail.get("reason"),
                    confidence=detail.get("confidence"),
                )
                continue

            action = {
                **detail,
                "status": "matched",
                "record_id": match.record_id,
                "record_label": match.label,
                "record_value": match.value,
            }
            taxonomy_counts[taxonomy]["matched_total"] += 1
            if detail.get("method") == "claude":
                taxonomy_counts[taxonomy]["matched_claude"] += 1
            else:
                taxonomy_counts[taxonomy]["matched_deterministic"] += 1

            if args.strict_skip_existing_icons and has_existing_icons(match.raw):
                taxonomy_counts[taxonomy]["skipped_existing_icons"] += 1
                skipped.append(
                    {
                        **action,
                        "status": "skipped_existing_icons",
                        "api_action": "strict_skip_existing_icons",
                        "reason": "Record already has appIcon/webIcon and strict mode is enabled.",
                    }
                )
                log_event(
                    "info",
                    "strict_skip_existing_icons",
                    taxonomy=taxonomy,
                    image=image_path.name,
                    record_id=match.record_id,
                    record_label=match.label,
                )
                continue

            if dry_run:
                action["api_action"] = "dry_run_skip_put"
                matched_actions.append(action)
                log_event(
                    "info",
                    "dry_run_match",
                    taxonomy=taxonomy,
                    image=image_path.name,
                    record_id=match.record_id,
                    record_label=match.label,
                    method=detail.get("method"),
                    confidence=detail.get("confidence"),
                )
                continue

            try:
                resp = update_icons(
                    base_url=args.base_url,
                    token=args.admin_token,
                    taxonomy=taxonomy,
                    record=match,
                    image_path=image_path,
                    timeout_sec=max(120, args.timeout_sec),
                )
                if 200 <= resp.status_code < 300:
                    taxonomy_counts[taxonomy]["put_success"] += 1
                    action["api_action"] = "put_success"
                    action["status_code"] = resp.status_code
                    matched_actions.append(action)
                    log_event(
                        "info",
                        "put_success",
                        taxonomy=taxonomy,
                        image=image_path.name,
                        record_id=match.record_id,
                        status_code=resp.status_code,
                    )
                else:
                    taxonomy_counts[taxonomy]["put_failed"] += 1
                    failures.append(
                        {
                            **action,
                            "api_action": "put_failed",
                            "status_code": resp.status_code,
                            "response_text": resp.text[:1000],
                        }
                    )
                    log_event(
                        "error",
                        "put_failed",
                        taxonomy=taxonomy,
                        image=image_path.name,
                        record_id=match.record_id,
                        status_code=resp.status_code,
                    )
            except Exception as exc:
                taxonomy_counts[taxonomy]["put_exception"] += 1
                failures.append(
                    {
                        **action,
                        "api_action": "put_exception",
                        "error": str(exc),
                    }
                )
                log_event(
                    "error",
                    "put_exception",
                    taxonomy=taxonomy,
                    image=image_path.name,
                    record_id=match.record_id,
                    error=str(exc),
                )

        log_event("info", "taxonomy_completed", taxonomy=taxonomy, counts=taxonomy_counts[taxonomy])

    skipped_reason_counts: Dict[str, int] = {}
    for item in skipped:
        reason_key = str(item.get("status", "unknown"))
        if item.get("api_action") == "strict_skip_existing_icons":
            reason_key = "skipped_existing_icons"
        elif item.get("method") == "taxonomy_alias_skip":
            reason_key = "skipped_alias_skip"
        elif item.get("status") == "unmatched_or_low_confidence":
            reason_key = "unmatched_or_low_confidence"
        skipped_reason_counts[reason_key] = skipped_reason_counts.get(reason_key, 0) + 1

    overall_counts = {
        "images_total": sum(c["images_total"] for c in taxonomy_counts.values()),
        "matched_total": sum(c["matched_total"] for c in taxonomy_counts.values()),
        "matched_deterministic": sum(c["matched_deterministic"] for c in taxonomy_counts.values()),
        "matched_claude": sum(c["matched_claude"] for c in taxonomy_counts.values()),
        "put_success": sum(c["put_success"] for c in taxonomy_counts.values()),
        "put_failed": sum(c["put_failed"] for c in taxonomy_counts.values()),
        "put_exception": sum(c["put_exception"] for c in taxonomy_counts.values()),
        "skipped_total": len(skipped),
    }

    summary = {
        "mode": "dry_run" if dry_run else "apply",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "taxonomy_counts": taxonomy_counts,
        "overall_counts": overall_counts,
        "skipped_reason_counts": skipped_reason_counts,
        "matched_count": len(matched_actions),
        "skipped_count": len(skipped),
        "failure_count": len(failures),
    }
    log_event("info", "run_completed", summary=summary)

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "matched_actions.json").write_text(json.dumps(matched_actions, indent=2), encoding="utf-8")
    (output_dir / "skipped.json").write_text(json.dumps(skipped, indent=2), encoding="utf-8")
    (output_dir / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    log_event("info", "reports_written", output_dir=str(output_dir))


if __name__ == "__main__":
    main()
