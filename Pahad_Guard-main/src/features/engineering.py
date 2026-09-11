import numpy as np
import pandas as pd

from src.config import LAND_COVER_MAPPING


def prepare_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    numeric_columns = [
        "rainfall_24h",
        "rainfall_3day",
        "rainfall_7day",
        "soil_moisture",
        "elevation",
        "slope",
        "historical_landslide",
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result["land_cover"] = (
        result["land_cover"]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    result["land_cover_encoded"] = (
        result["land_cover"]
        .map(LAND_COVER_MAPPING)
        .fillna(LAND_COVER_MAPPING["grassland"])
        .astype(int)
    )

    result["rainfall_intensity_index"] = (
        0.50 * result["rainfall_24h"]
        + 0.30 * result["rainfall_3day"]
        + 0.20 * result["rainfall_7day"]
    )

    result["terrain_exposure_index"] = (
        0.70 * result["slope"] + 0.01 * result["elevation"]
    )

    result["data_complete"] = ~result[
        [
            "rainfall_24h",
            "rainfall_3day",
            "rainfall_7day",
            "soil_moisture",
            "elevation",
            "slope",
            "land_cover_encoded",
            "historical_landslide",
        ]
    ].isnull().any(axis=1)

    return result.replace([np.inf, -np.inf], np.nan)