"""Unit tests for HLHP evidence build validators."""

from app.hlhp.evidence.citations import validate_citations
from app.hlhp.evidence.voice import validate_l1_voice


def _finding(**kwargs):
    base = {
        "id": "TST-1",
        "source_type": "Book",
        "source_title": "Skin Barrier",
        "pages_doi_pmid": "p. 42",
        "alert_l1_guest": "Apply sunscreen before outdoor time today.",
        "alert_l1_personalised": "UV is high today. Sunscreen is recommended.",
        "triggers": {"user_filter": []},
    }
    base.update(kwargs)
    return base


def test_voice_does_not_flag_plain_english_or():
    glossary = [{"category": "Stats", "term": "95% CI / OR / RR / HR / SMD / n="}]
    issues = validate_l1_voice(
        [_finding(alert_l1_guest="Pick a gel or cream moisturizer for oily skin.")],
        glossary,
    )
    assert not any(i["rule"] == "glossary_stats" and "OR" in i["detail"] for i in issues)


def test_voice_flags_percentage_in_l1():
    issues = validate_l1_voice(
        [_finding(alert_l1_guest="About 95% of UV reaching skin is UVA.")],
        [],
    )
    assert any(i["rule"] == "percentage" for i in issues)


def test_citations_accepts_pubmed_paper_with_pmc_url():
    row = _finding(
        source_type="Research Paper",
        source_title="Clinical and molecular change induced by visible light",
        pages_doi_pmid="https://pmc.ncbi.nlm.nih.gov/articles/PMC9859939/",
    )
    issues = validate_citations([row], [{"title": "Unrelated Book"}])
    assert issues == []


def test_citations_flags_unknown_book_without_external_id():
    row = _finding(
        source_type="Book",
        source_title="Totally Unknown Dermatology Title XYZ",
        pages_doi_pmid="p. 99",
    )
    issues = validate_citations([row], [{"title": "Skin Barrier"}])
    assert any(i["rule"] == "book_not_in_inventory" for i in issues)
