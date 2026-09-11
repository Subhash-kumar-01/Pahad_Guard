import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"
MODEL_DIR = BASE_DIR / "models"

DATA_FILE = PROCESSED_DATA_DIR / "sikkim_demo_dataset.csv"
MODEL_FILE = MODEL_DIR / "landslide_random_forest.joblib"
METRICS_FILE = MODEL_DIR / "model_metrics.json"

AUTH_DB_FILE = DATA_DIR / "users.db"

PILOT_AREA = "Sikkim, India"

FEATURE_COLUMNS = [
    "rainfall_24h",
    "rainfall_3day",
    "rainfall_7day",
    "soil_moisture",
    "elevation",
    "slope",
    "land_cover_encoded",
    "historical_landslide",
]

RAW_FEATURE_COLUMNS = [
    "rainfall_24h",
    "rainfall_3day",
    "rainfall_7day",
    "soil_moisture",
    "elevation",
    "slope",
    "land_cover",
    "historical_landslide",
]

LAND_COVER_MAPPING = {
    "forest": 0,
    "agriculture": 1,
    "grassland": 2,
    "bare_land": 3,
    "urban": 4,
    "water": 5,
}

RISK_THRESHOLDS = {
    "LOW": (0, 25),
    "MODERATE": (26, 50),
    "HIGH": (51, 75),
    "CRITICAL": (76, 100),
}

ALERT_THRESHOLDS = {
    "NONE": (0, 49.99),
    "WATCH": (50, 74.99),
    "WARNING": (75, 89.99),
    "CRITICAL": (90, 100),
}

# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

ROLES: tuple[str, ...] = ("user", "admin", "department")
DEFAULT_ROLE = "user"

# Which navigation pages each role may open. "Database" (the admin panel)
# is admin-only; the department role sees every information page; regular
# users only get what a citizen needs.
ROLE_PAGES: dict[str, list[str]] = {
    "user": [
        "Overview",
        "Risk Map",
        "Alerts",
    ],
    "department": [
        "Overview",
        "Risk Map",
        "Zone Analysis",
        "Coordinate Analysis",
        "Alerts",
        "Rainfall Simulator",
    ],
    "admin": [
        "Overview",
        "Risk Map",
        "Zone Analysis",
        "Coordinate Analysis",
        "Alerts",
        "Rainfall Simulator",
        "Database",
    ],
}

# ---------------------------------------------------------------------------
# Extra login/signup verification fields (role-based access hardening)
# ---------------------------------------------------------------------------

# Department accounts must supply a matching "Department ID" both when they
# sign up and when they log back in. Admin accounts must supply this shared
# "Secret ID" when logging in. Override via a .env file for real deployments.
ADMIN_SECRET_ID = os.getenv("ADMIN_SECRET_ID", "PAHAD-ADMIN-2024")