from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "zone_id",
    "latitude",
    "longitude",
    "date",
    "rainfall_24h",
    "rainfall_3day",
    "rainfall_7day",
    "soil_moisture",
    "elevation",
    "slope",
    "land_cover",
    "historical_landslide",
    "label",
]


def load_dataset(path: str | Path) -> pd.DataFrame:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    dataframe = pd.read_csv(path)

    missing = sorted(set(REQUIRED_COLUMNS) - set(dataframe.columns))

    if missing:
        raise ValueError(f"Dataset is missing columns: {missing}")

    dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")

    return dataframe