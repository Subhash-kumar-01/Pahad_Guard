def clamp_score(score: float) -> float:
    return max(0.0, min(100.0, float(score)))


def risk_level(score: float) -> str:
    score = clamp_score(score)

    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MODERATE"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def risk_color(score: float) -> str:
    level = risk_level(score)

    return {
        "LOW": "#2ca02c",
        "MODERATE": "#f1c40f",
        "HIGH": "#e67e22",
        "CRITICAL": "#d62728",
    }[level]


def alert_level(score: float) -> str:
    score = clamp_score(score)

    if score < 50:
        return "NONE"
    if score < 75:
        return "WATCH"
    if score < 90:
        return "WARNING"
    return "CRITICAL"


def alert_message(level: str) -> str:
    messages = {
        "NONE": "No prototype alert is currently triggered.",
        "WATCH": (
            "Continue monitoring rainfall, soil moisture and vulnerable slopes."
        ),
        "WARNING": (
            "Inspect vulnerable slopes, monitor nearby roads and prepare local response."
        ),
        "CRITICAL": (
            "Prioritize field verification, road monitoring and emergency coordination."
        ),
    }

    return messages.get(level, "No message available.")


def explain_risk(row) -> list[str]:
    drivers = []

    if row["rainfall_24h"] >= 100:
        drivers.append("Heavy 24-hour rainfall")
    elif row["rainfall_24h"] >= 60:
        drivers.append("Elevated 24-hour rainfall")

    if row["soil_moisture"] >= 0.75:
        drivers.append("High soil moisture")
    elif row["soil_moisture"] >= 0.55:
        drivers.append("Moderately high soil moisture")

    if row["slope"] >= 30:
        drivers.append("Steep slope")
    elif row["slope"] >= 20:
        drivers.append("Moderately steep slope")

    if row["historical_landslide"] == 1:
        drivers.append("Historical landslide activity")

    if row["land_cover"] in {"bare_land", "urban"}:
        drivers.append("Less protective land cover")

    if not drivers:
        drivers.append("No individual feature crossed the prototype driver thresholds")

    return drivers


def build_risk_score(row) -> float:
    rainfall_component = min(float(row["rainfall_24h"]) / 180, 1.0) * 35
    soil_component = min(float(row["soil_moisture"]) / 0.90, 1.0) * 25
    slope_component = min(float(row["slope"]) / 45, 1.0) * 25
    history_component = float(row["historical_landslide"]) * 10

    land_cover_component = {
        "forest": 0,
        "grassland": 2,
        "agriculture": 4,
        "bare_land": 7,
        "urban": 5,
        "water": 0,
    }.get(str(row["land_cover"]).lower(), 3)

    return clamp_score(
        rainfall_component
        + soil_component
        + slope_component
        + history_component
        + land_cover_component
    )