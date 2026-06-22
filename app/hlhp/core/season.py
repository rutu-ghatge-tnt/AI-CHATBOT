"""Indian seasonal calendar — v2 four-band model + legacy five-band alias."""

from datetime import date

from app.hlhp.core.trigger_bands import season_match_tags


def season_v2(when: date | None = None) -> str:
    """v2 §3.5: winter | summer | monsoon | post_monsoon."""
    today = when or date.today()
    month = today.month
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "summer"
    if month in (6, 7, 8, 9):
        return "monsoon"
    return "post_monsoon"


def indian_season(when: date | None = None) -> str:
    """
    Primary season tag for matching. Returns v2 band; legacy callers
    still receive a value that indexes correctly via season_match_tags().
    """
    return season_v2(when)


def seasons_for_matching(when: date | None = None) -> set[str]:
    """All season tags applicable for inverted-index lookup."""
    return season_match_tags(season_v2(when))
