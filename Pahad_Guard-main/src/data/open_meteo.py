"""Open-Meteo weather/soil data integration.

Open-Meteo's public API does not require an API key for non-commercial use.
This module provides the live weather features used by Pahad Guard.
"""

from __future__ import annotations

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 15


def _sum(values: list[float | None]) -> float:
    return float(sum(float(v or 0.0) for v in values))


def get_dynamic_features(latitude: float, longitude: float) -> dict:
    """Fetch recent precipitation, soil moisture and elevation.

    Rainfall windows are calculated from hourly precipitation for the last
    seven completed days. Elevation is supplied by Open-Meteo's elevation
    model. Slope is intentionally left as None because Open-Meteo does not
    expose a slope variable; the application uses its nearest-zone baseline
    for slope instead of pretending weather data contains terrain slope.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "daily": "precipitation_sum",
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    response = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly", {})
    precipitation = hourly.get("precipitation", [])
    soil_values = hourly.get("soil_moisture_0_to_7cm", [])

    # Use the most recent 24 hourly observations for the 24h feature.
    recent_precip = precipitation[-24:] if precipitation else []
    rainfall_24h = _sum(recent_precip)
    rainfall_3day = _sum(precipitation[-72:])
    rainfall_7day = _sum(precipitation[-168:])

    valid_soil = [float(v) for v in soil_values if v is not None]
    soil_moisture = float(sum(valid_soil[-24:]) / len(valid_soil[-24:])) if valid_soil else None

    elevation = payload.get("elevation")

    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "rainfall_24h": rainfall_24h,
        "rainfall_3day": rainfall_3day,
        "rainfall_7day": rainfall_7day,
        "soil_moisture": soil_moisture,
        "elevation": float(elevation) if elevation is not None else None,
        "source": "Open-Meteo",
    }
