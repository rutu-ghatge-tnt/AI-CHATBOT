from app.hlhp.services.weather_visuals import extract_weather_visuals


def test_extract_weather_visuals_from_skintruth_shape():
    raw = {
        "data": {
            "weather": {
                "skinCareTip": "Lightweight Day!",
                "current": {
                    "screenVariants": [
                        {
                            "screen": "desktop",
                            "weatherType": "sunny",
                            "backgroundImage": "https://example.com/bg-desktop.png",
                            "animal": "https://example.com/animal-desktop.png",
                        },
                        {
                            "screen": "mobile",
                            "weatherType": "sunny",
                            "backgroundImage": "https://example.com/bg-mobile.png",
                            "animal": "https://example.com/animal-mobile.png",
                        },
                    ]
                },
            }
        }
    }
    out = extract_weather_visuals(raw)
    assert out["weather_type"] == "sunny"
    assert out["skin_care_tip"] == "Lightweight Day!"
    assert len(out["screen_variants"]) == 2
    assert out["screen_variants"][0]["background_image"].endswith("bg-desktop.png")
    assert out["screen_variants"][1]["animal_image"].endswith("animal-mobile.png")


def test_extract_weather_visuals_empty():
    out = extract_weather_visuals({})
    assert out["screen_variants"] == []
