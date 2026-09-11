import pandas as pd

from src.risk.engine import (
    alert_level,
    build_risk_score,
    risk_level,
)


def make_row(**overrides):
    values = {
        "rainfall_24h": 10,
        "rainfall_3day": 25,
        "rainfall_7day": 45,
        "soil_moisture": 0.20,
        "elevation": 500,
        "slope": 5,
        "land_cover": "forest",
        "historical_landslide": 0,
    }
    values.update(overrides)
    return pd.Series(values)


def test_low_risk_conditions():
    row = make_row()
    score = build_risk_score(row)

    assert score <= 50
    assert risk_level(score) in {"LOW", "MODERATE"}
    assert alert_level(score) == "NONE"


def test_extreme_conditions_produce_high_risk():
    row = make_row(
        rainfall_24h=250,
        rainfall_3day=500,
        rainfall_7day=800,
        soil_moisture=0.95,
        elevation=2200,
        slope=45,
        land_cover="bare_land",
        historical_landslide=1,
    )

    score = build_risk_score(row)

    assert score >= 75
    assert risk_level(score) == "CRITICAL"
    assert alert_level(score) == "CRITICAL"