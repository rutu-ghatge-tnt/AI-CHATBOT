"""One-off smoke test for HL / HLHP routes (run: python scripts/smoke_hlhp_api.py)."""
from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    c = TestClient(app, raise_server_exceptions=True)

    r1 = c.get("/api/hl/v1/alert", params={"lat": 18.5628, "lng": 73.7700})
    print("v1", r1.status_code)
    if r1.status_code == 200:
        j = r1.json()
        print("compact_headline:", (j.get("compact_headline") or "")[:160])
    else:
        print(r1.text[:800])

    r2 = c.get(
        "/api/hl/v2/alert/preview",
        params={
            "lat": 18.5628,
            "lng": 73.7700,
            "skin_type": "combination",
            "primary_concern": "acne",
            "gender": "female",
            "age_bracket": "25-30",
            "hair_type": "straight",
            "hair_concern": "dandruff",
        },
    )
    print("v2 preview", r2.status_code)
    if r2.status_code == 200:
        j2 = r2.json()
        print("personalized_headline:", (j2.get("personalized_headline") or "")[:160])
        print("has hair_alert:", bool(j2.get("hair_alert")))
    else:
        print(r2.text[:800])


if __name__ == "__main__":
    main()
