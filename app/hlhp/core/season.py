"""Indian seasonal calendar per HLHP spec §5.1."""

from datetime import date


def indian_season(when: date | None = None) -> str:
    """Return season band: winter_dry | pre_monsoon | monsoon | post_monsoon | winter_humid."""
    today = when or date.today()
    month = today.month
    if month in (12, 1, 2):
        return "winter_dry"
    if month in (3, 4, 5):
        return "pre_monsoon"
    if month in (6, 7, 8, 9):
        return "monsoon"
    return "post_monsoon"
