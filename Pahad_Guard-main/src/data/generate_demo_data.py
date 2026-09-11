from pathlib import Path

import numpy as np
import pandas as pd


def generate_demo_dataset(
    output_path: str | Path,
    rows: int = 180,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    latitudes = rng.uniform(27.10, 28.10, rows)
    longitudes = rng.uniform(88.00, 88.90, rows)

    rainfall_24h = np.clip(rng.gamma(shape=2.5, scale=35, size=rows), 2, 280)
    rainfall_3day = rainfall_24h + rng.gamma(shape=2.5, scale=45, size=rows)
    rainfall_7day = rainfall_3day + rng.gamma(shape=2.5, scale=65, size=rows)

    soil_moisture = np.clip(
        0.25 + rainfall_7day / 650 + rng.normal(0, 0.08, rows),
        0.05,
        0.98,
    )

    elevation = np.clip(
        rng.normal(1450, 480, rows),
        150,
        3600,
    )

    slope = np.clip(
        5 + elevation / 125 + rng.normal(0, 8, rows),
        1,
        55,
    )

    land_covers = rng.choice(
        ["forest", "agriculture", "grassland", "bare_land", "urban"],
        size=rows,
        p=[0.48, 0.22, 0.14, 0.10, 0.06],
    )

    historical_landslide = rng.binomial(1, 0.20, rows)

    raw_score = (
        0.035 * rainfall_24h
        + 0.012 * rainfall_3day
        + 0.006 * rainfall_7day
        + 42 * soil_moisture
        + 1.15 * slope
        + 0.004 * elevation
        + 15 * historical_landslide
        + np.where(land_covers == "bare_land", 8, 0)
        + np.where(land_covers == "urban", 5, 0)
        + rng.normal(0, 8, rows)
    )

    probability = 1 / (1 + np.exp(-(raw_score - 78) / 14))
    labels = rng.binomial(1, probability)

    dates = pd.date_range(
        end=pd.Timestamp.today().normalize(),
        periods=rows,
        freq="D",
    )

    dataframe = pd.DataFrame(
        {
            "zone_id": [f"SIKKIM-{index + 1:03d}" for index in range(rows)],
            "latitude": latitudes.round(6),
            "longitude": longitudes.round(6),
            "date": dates,
            "rainfall_24h": rainfall_24h.round(2),
            "rainfall_3day": rainfall_3day.round(2),
            "rainfall_7day": rainfall_7day.round(2),
            "soil_moisture": soil_moisture.round(3),
            "elevation": elevation.round(2),
            "slope": slope.round(2),
            "land_cover": land_covers,
            "historical_landslide": historical_landslide,
            "label": labels,
        }
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False)

    return dataframe


if __name__ == "__main__":
    from src.config import DATA_FILE

    generate_demo_dataset(DATA_FILE)