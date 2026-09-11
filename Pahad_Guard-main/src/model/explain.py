from pathlib import Path

import joblib
import pandas as pd

from src.config import FEATURE_COLUMNS, MODEL_FILE


DISPLAY_NAMES = {
    "rainfall_24h": "Rainfall — 24 hours",
    "rainfall_3day": "Rainfall — 3 days",
    "rainfall_7day": "Rainfall — 7 days",
    "soil_moisture": "Soil moisture",
    "elevation": "Elevation",
    "slope": "Slope",
    "land_cover_encoded": "Land cover",
    "historical_landslide": "Historical landslide",
}


def get_feature_importance(
    model_path: str | Path = MODEL_FILE,
) -> pd.DataFrame:
    model = joblib.load(model_path)
    classifier = model.named_steps["classifier"]

    importance = pd.DataFrame(
        {
            "feature": FEATURE_COLUMNS,
            "importance": classifier.feature_importances_,
        }
    )

    importance["feature"] = importance["feature"].map(DISPLAY_NAMES)
    importance["importance"] = importance["importance"] / importance[
        "importance"
    ].sum()

    return importance.sort_values("importance", ascending=False)