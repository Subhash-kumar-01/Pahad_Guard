import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from src.config import (
    DATA_FILE,
    FEATURE_COLUMNS,
    METRICS_FILE,
    MODEL_FILE,
)
from src.data.load_data import load_dataset
from src.features.engineering import prepare_features


def train_model(
    data_path: str | Path = DATA_FILE,
    model_path: str | Path = MODEL_FILE,
):
    dataframe = load_dataset(data_path)
    dataframe = prepare_features(dataframe)

    dataframe = dataframe[dataframe["data_complete"]].copy()

    x = dataframe[FEATURE_COLUMNS]
    y = dataframe["label"].astype(int)

    if y.nunique() < 2:
        raise ValueError("Training data must contain both classes: 0 and 1.")

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=10,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    pipeline.fit(x_train, y_train)

    probabilities = pipeline.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)

    metrics = {
        "accuracy": accuracy_score(y_test, predictions),
        "precision": precision_score(y_test, predictions, zero_division=0),
        "recall": recall_score(y_test, predictions, zero_division=0),
        "f1": f1_score(y_test, predictions, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        "classification_report": classification_report(
            y_test,
            predictions,
            zero_division=0,
        ),
    }

    if len(set(y_test)) == 2:
        metrics["roc_auc"] = roc_auc_score(y_test, probabilities)
    else:
        metrics["roc_auc"] = None

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)

    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))

    return pipeline, metrics


if __name__ == "__main__":
    _, training_metrics = train_model()
    print(json.dumps(training_metrics, indent=2))