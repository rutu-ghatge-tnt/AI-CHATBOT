"""Book Inventory citation cross-checks at build time."""

from __future__ import annotations

import re
from typing import Any

_DOI_RE = re.compile(r"\b10\.\d{4,}/\S+", re.I)
_PMID_RE = re.compile(r"\bPMID[:\s]?\d+\b", re.I)
_PAPER_URL_RE = re.compile(
    r"pmc\.ncbi\.nlm\.nih\.gov|pubmed\.ncbi\.nlm\.nih\.gov|doi\.org|/articles/PMC\d+",
    re.I,
)
_PAPER_SOURCE_TYPES = {
    "paper",
    "journal",
    "web",
    "pubmed",
    "preprint",
    "research paper",
    "pubmed/web",
    "web/pubmed",
}


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return " ".join(title.split())


def _book_titles(inventory: list[dict[str, Any]]) -> list[str]:
    return [_normalize_title(b.get("title") or "") for b in inventory if b.get("title")]


def _is_external_paper(row: dict[str, Any]) -> bool:
    source_type = (row.get("source_type") or "").lower().strip()
    pages = row.get("pages_doi_pmid") or ""
    chapter = row.get("chapter_section") or ""
    if source_type in _PAPER_SOURCE_TYPES:
        return True
    if any(x in source_type for x in ("paper", "pubmed", "journal", "web")):
        return True
    if _DOI_RE.search(pages) or _PMID_RE.search(pages) or _PAPER_URL_RE.search(pages):
        return True
    if _DOI_RE.search(chapter) or _PMID_RE.search(chapter):
        return True
    return False


def _matches_inventory(source_title: str, normalized_books: list[str]) -> bool:
    norm = _normalize_title(source_title)
    if not norm:
        return False
    for book in normalized_books:
        if not book:
            continue
        if norm in book or book in norm:
            return True
        norm_tokens = set(norm.split())
        book_tokens = set(book.split())
        overlap = len(norm_tokens & book_tokens)
        if overlap >= max(4, min(len(norm_tokens), len(book_tokens)) * 2 // 3):
            return True
    return False


def validate_citations(
    findings: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    books = _book_titles(inventory)

    for row in findings:
        row_id = row["id"]
        title = row.get("source_title") or ""
        pages = row.get("pages_doi_pmid") or ""

        if not title:
            issues.append({"row_id": row_id, "rule": "missing_title", "detail": "no source title"})
            continue
        if not pages:
            issues.append({"row_id": row_id, "rule": "missing_pages", "detail": "no pages/DOI/PMID"})
            continue
        if _is_external_paper(row):
            continue
        if not _matches_inventory(title, books):
            issues.append(
                {
                    "row_id": row_id,
                    "rule": "book_not_in_inventory",
                    "detail": f"source '{title[:80]}' not matched in Book Inventory",
                }
            )
    return issues
