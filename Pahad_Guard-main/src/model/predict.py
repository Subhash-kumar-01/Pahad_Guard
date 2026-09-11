from pathlib import Path

import joblib
import pandas as pd

from src.config import FEATURE_COLUMNS, MODEL_FILE
from src.risk.engine import (
    alert_level,
    build_risk_score,
    explain_risk,
    risk_level,
)


def load_model(model_path: str | Path = MODEL_FILE):
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}. Run model training first."
        )

    return joblib.load(model_path)


def predict_dataframe(
    dataframe: pd.DataFrame,
    model_path: str | Path = MODEL_FILE,
) -> pd.DataFrame:
    result = dataframe.copy()

    model = load_model(model_path)

    missing_features = sorted(set(FEATURE_COLUMNS) - set(result.columns))

    if missing_features:
        raise ValueError(f"Missing model features: {missing_features}")

    result["model_probability"] = model.predict_proba(
        result[FEATURE_COLUMNS]
    )[:, 1]

    result["model_score"] = result["model_probability"] * 100

    result["risk_score"] = result.apply(build_risk_score, axis=1)

    result["risk_level"] = result["risk_score"].apply(risk_level)
    result["alert_level"] = result["risk_score"].apply(alert_level)

    result["risk_drivers"] = result.apply(
        lambda row: "|".join(explain_risk(row)),
        axis=1,
    )

    incomplete = ~result["data_complete"]
    result.loc[incomplete, "risk_score"] = 0
    result.loc[incomplete, "risk_level"] = "INSUFFICIENT DATA"
    result.loc[incomplete, "alert_level"] = "NONE"
    result.loc[incomplete, "risk_drivers"] = "Insufficient data for reliable risk assessment"

    return result


def predict_single(
    row: pd.Series,
    model_path: str | Path = MODEL_FILE,
) -> dict:
    dataframe = pd.DataFrame([row.to_dict()])
    prediction = predict_dataframe(dataframe, model_path).iloc[0]

    return {
        "risk_score": float(prediction["risk_score"]),
        "risk_level": prediction["risk_level"],
        "alert_level": prediction["alert_level"],
        "risk_drivers": prediction["risk_drivers"].split("|"),
    }