import os
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from dashboard.components import (
    render_alert_card,
    render_location_alert_card,
    render_metric_cards,
    render_risk_gauge,
)
from src.auth.database import (
    list_auth_logs,
    list_prediction_logs,
    list_users,
    log_prediction,
    update_user_role,
)
from src.auth.ui import current_role, is_authenticated, logout, render_auth_page
from src.config import (
    DATA_FILE,
    DEFAULT_ROLE,
    LAND_COVER_MAPPING,
    MODEL_FILE,
    PILOT_AREA,
    ROLES,
    ROLE_PAGES,
)
from src.data.open_meteo import get_dynamic_features
from src.data.load_data import load_dataset
from src.features.engineering import prepare_features
from src.location.geo import GEOLOCATION_AVAILABLE, fetch_browser_location, reverse_geocode
from src.model.predict import predict_dataframe, predict_single
from src.model.train import train_model
from src.risk.engine import (
    alert_level,
    alert_message,
    risk_level,
    risk_color,
)
from src.utils.invoice import build_prediction_invoice_pdf
from src.utils.validation import validate_sikkim_coordinates

try:
    from streamlit_autorefresh import st_autorefresh

    AUTOREFRESH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    AUTOREFRESH_AVAILABLE = False

load_dotenv()

LOCATION_STATE_DEFAULTS = {
    "location_mode": None,  # None | "current" | "live"
    "location_prompted": False,
    "user_lat": None,
    "user_lon": None,
    "location_description": None,
    "live_refresh_count": 0,
}


@st.cache_data
def get_data():
    return load_dataset(DATA_FILE)


@st.cache_resource
def get_model():
    if not MODEL_FILE.exists():
        train_model()
    return MODEL_FILE


def initialize_application():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        from src.data.generate_demo_data import generate_demo_dataset

        generate_demo_dataset(DATA_FILE)

    if not MODEL_FILE.exists():
        train_model()


def create_risk_map(dataframe: pd.DataFrame, selected_zone: str | None = None):
    center_lat = dataframe["latitude"].mean()
    center_lon = dataframe["longitude"].mean()

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="OpenStreetMap",
    )

    for _, row in dataframe.iterrows():
        selected = row["zone_id"] == selected_zone
        radius = 9 if selected else 6
        color = risk_color(row["risk_score"])

        popup_text = f"""
        <b>{row['zone_id']}</b><br>
        Risk score: {row['risk_score']:.1f}/100<br>
        Level: {row['risk_level']}<br>
        Rainfall 24h: {row['rainfall_24h']:.1f} mm<br>
        Soil moisture: {row['soil_moisture']:.2f}<br>
        Slope: {row['slope']:.1f}°<br>
        Elevation: {row['elevation']:.0f} m
        """

        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(popup_text, max_width=280),
            tooltip=f"{row['zone_id']} — {row['risk_level']}",
        ).add_to(fmap)

    return fmap


def haversine_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometers between a point and one or more points."""
    r = 6371.0
    lat1_r, lon1_r, lat2_r, lon2_r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return r * c


def fetch_live_weather(latitude: float, longitude: float):
    """Fetch live weather/soil/elevation data from Open-Meteo.

    Open-Meteo's public API does not require an API key. Slope is not
    provided by the weather API, so the caller keeps the nearest-zone slope.
    """
    try:
        data = get_dynamic_features(latitude, longitude)
    except Exception as error:
        return None, str(error)

    if data.get("elevation") is None:
        return None, "Open-Meteo returned no elevation for this point."

    return data, None

def nearest_zone_baseline(dataframe: pd.DataFrame, latitude: float, longitude: float, k: int = 3):
    """Inverse-distance-weighted defaults from the k nearest monitored zones.

    The model requires slope, but Open-Meteo does not provide it. Therefore
    slope is always taken from the monitored-zone dataset rather than from
    live weather data.
    """
    required_columns = {
        "latitude",
        "longitude",
        "rainfall_24h",
        "rainfall_3day",
        "rainfall_7day",
        "soil_moisture",
        "elevation",
        "slope",
        "land_cover",
        "historical_landslide",
        "zone_id",
    }
    missing = sorted(required_columns.difference(dataframe.columns))
    if missing:
        raise ValueError(
            "The loaded dataset is missing required columns: "
            + ", ".join(missing)
            + ". Please check the dataset/feature-engineering pipeline."
        )

    working = dataframe.copy()
    working["distance_km"] = haversine_distance(
        latitude, longitude, working["latitude"], working["longitude"]
    )
    nearest = working.sort_values("distance_km").head(max(1, min(k, len(working))))

    if nearest.empty:
        raise ValueError("No monitored zones are available for location-risk assessment.")

    weights = 1.0 / nearest["distance_km"].replace(0, 1e-6)
    weights = weights / weights.sum()

    numeric_features = [
        "rainfall_24h",
        "rainfall_3day",
        "rainfall_7day",
        "soil_moisture",
        "elevation",
        "slope",
    ]

    baseline = {}
    for feature in numeric_features:
        values = pd.to_numeric(nearest[feature], errors="coerce")
        valid = values.notna()
        if not valid.any():
            raise ValueError(f"No valid '{feature}' values exist in the monitored-zone dataset.")
        feature_weights = weights[valid]
        feature_weights = feature_weights / feature_weights.sum()
        baseline[feature] = float((values[valid] * feature_weights).sum())

    closest = nearest.iloc[0]
    baseline["land_cover"] = closest["land_cover"]
    baseline["historical_landslide"] = int(closest["historical_landslide"])
    baseline["closest_zone_id"] = closest["zone_id"]
    baseline["closest_distance_km"] = float(closest["distance_km"])
    baseline["nearest_table"] = nearest

    return baseline


def assess_custom_location(
    latitude: float,
    longitude: float,
    rainfall_24h: float,
    rainfall_3day: float,
    rainfall_7day: float,
    soil_moisture: float,
    elevation: float,
    slope: float,
    land_cover: str,
    historical_landslide: int,
) -> pd.Series:
    """Run a single custom coordinate through the real feature + prediction pipeline."""
    row = {
        "zone_id": "Custom point",
        "latitude": latitude,
        "longitude": longitude,
        "rainfall_24h": rainfall_24h,
        "rainfall_3day": rainfall_3day,
        "rainfall_7day": rainfall_7day,
        "soil_moisture": soil_moisture,
        "elevation": elevation,
        "slope": slope,
        "land_cover": land_cover,
        "historical_landslide": historical_landslide,
    }

    single_row = pd.DataFrame([row])
    single_row = prepare_features(single_row)
    single_row = predict_dataframe(single_row)

    return single_row.iloc[0]


def init_location_state() -> None:
    for key, value in LOCATION_STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.dialog("📍 Share your location")
def location_choice_dialog():
    st.write(
        "Pahad Guard can show a personalized landslide-risk alert for where "
        "you are right now. Choose how you'd like to share your location:"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📍 Current Location", use_container_width=True):
            st.session_state.location_mode = "current"
            st.session_state.location_prompted = True
            st.session_state.user_lat = None
            st.session_state.user_lon = None
            st.session_state.location_description = None
            st.rerun()
    with col2:
        if st.button("🔴 Live Location", use_container_width=True):
            st.session_state.location_mode = "live"
            st.session_state.location_prompted = True
            st.session_state.user_lat = None
            st.session_state.user_lon = None
            st.session_state.location_description = None
            st.session_state.live_refresh_count = 0
            st.rerun()

    st.caption(
        "**Current Location** looks up where you are once. "
        "**Live Location** keeps checking every few seconds so the alert "
        "on your dashboard stays up to date as you move."
    )

    if not GEOLOCATION_AVAILABLE:
        st.caption(
            "ℹ️ Browser location isn't configured on this server — you'll be "
            "able to enter coordinates manually instead."
        )

    if st.button("Skip for now"):
        st.session_state.location_mode = None
        st.session_state.location_prompted = True
        st.rerun()


def evaluate_location_risk(dataframe: pd.DataFrame, latitude: float, longitude: float):
    """Run the same estimation pipeline used in Coordinate Analysis.

    Important: Open-Meteo does not provide slope, so slope MUST come from the
    nearest monitored zones. Never read ``live_data["slope"]`` here. This is
    the direct fix for the KeyError that occurs when live_data has no slope key.
    """
    baseline = nearest_zone_baseline(dataframe, latitude, longitude, k=3)
    live_data, live_error = fetch_live_weather(latitude, longitude)

    # Open-Meteo supplies live elevation/soil when available.
    # Slope is always taken from the monitored-zone baseline.
    elevation = baseline["elevation"]
    if live_data and live_data.get("elevation") is not None:
        elevation = float(live_data["elevation"])

    slope = float(baseline["slope"])

    soil_moisture = baseline["soil_moisture"]
    if live_data and live_data.get("soil_moisture") is not None:
        soil_moisture = float(live_data["soil_moisture"])

    # Keep rainfall on the same baseline used by the coordinate-analysis
    # workflow. This avoids accidentally passing missing/partial live rainfall
    # fields into a model trained on the monitored-zone feature set.
    result = assess_custom_location(
        latitude,
        longitude,
        baseline["rainfall_24h"],
        baseline["rainfall_3day"],
        baseline["rainfall_7day"],
        soil_moisture,
        elevation,
        slope,
        baseline["land_cover"],
        baseline["historical_landslide"],
    )
    return result, baseline


def _manual_location_fallback():
    """Shown when we don't yet have coordinates (permission pending/denied,
    or the optional browser-geolocation package isn't installed)."""
    with st.expander("Enter coordinates manually instead", expanded=not GEOLOCATION_AVAILABLE):
        col1, col2 = st.columns(2)
        manual_lat = col1.number_input(
            "Latitude", value=27.60, format="%.6f", key="manual_loc_lat"
        )
        manual_lon = col2.number_input(
            "Longitude", value=88.40, format="%.6f", key="manual_loc_lon"
        )
        if st.button("Use these coordinates", key="use_manual_loc"):
            st.session_state.user_lat = manual_lat
            st.session_state.user_lon = manual_lon
            st.session_state.location_description = reverse_geocode(manual_lat, manual_lon)
            st.rerun()


def render_user_location_panel(dataframe: pd.DataFrame):
    """Dashboard block: description of the user's shared location plus a
    live risk alert for that point (Current or Live location mode)."""
    st.markdown("### 📍 Your location")

    header_left, header_right = st.columns([4, 1])
    with header_right:
        if st.button("Change", key="change_location_btn", use_container_width=True):
            for key, value in LOCATION_STATE_DEFAULTS.items():
                st.session_state[key] = value
            st.rerun()

    mode = st.session_state.location_mode

    if mode is None:
        with header_left:
            st.info(
                "Location sharing is off, so no personal risk alert is shown "
                "here. Click **Change** to turn it on."
            )
        return

    if mode == "live":
        if AUTOREFRESH_AVAILABLE:
            refresh_count = st_autorefresh(interval=15000, key="live_location_autorefresh")
            with header_left:
                st.caption("🔴 Live — refreshing automatically every 15 seconds.")
        else:
            refresh_count = st.session_state.live_refresh_count
            with header_left:
                st.caption("🔴 Live mode")
                if st.button("🔄 Refresh my live location", key="manual_live_refresh"):
                    st.session_state.live_refresh_count += 1
                    refresh_count = st.session_state.live_refresh_count
        component_key = f"user_location_live_{refresh_count}"
    else:
        with header_left:
            st.caption("📍 Current location (one-time lookup)")
        component_key = "user_location_current"

    if mode == "current" and st.session_state.user_lat is not None:
        # Already resolved once — don't keep re-asking the browser.
        lat, lon, error = st.session_state.user_lat, st.session_state.user_lon, None
    else:
        lat, lon, error = fetch_browser_location(component_key)

    if error == "pending":
        st.info("📡 Waiting for your browser's location permission — please allow access.")
        if st.session_state.user_lat is None:
            _manual_location_fallback()
            return
    elif error:
        st.warning(error)
        if st.session_state.user_lat is None:
            _manual_location_fallback()
            return
    else:
        st.session_state.user_lat = lat
        st.session_state.user_lon = lon
        st.session_state.location_description = reverse_geocode(lat, lon)

    if st.session_state.user_lat is None:
        _manual_location_fallback()
        return

    lat = st.session_state.user_lat
    lon = st.session_state.user_lon
    description = st.session_state.location_description or f"{lat:.4f}, {lon:.4f}"
    mode_label = "🔴 Live tracking" if mode == "live" else "📍 One-time lookup"

    in_pilot_area = not validate_sikkim_coordinates(
        pd.DataFrame({"latitude": [lat], "longitude": [lon]})
    ).empty

    with st.spinner("Assessing risk at your location..."):
        result, baseline = evaluate_location_risk(dataframe, lat, lon)

    render_location_alert_card(
        description=description,
        latitude=lat,
        longitude=lon,
        mode_label=mode_label,
        in_pilot_area=in_pilot_area,
        score=float(result["risk_score"]),
        level=result["risk_level"],
        alert=result["alert_level"],
        message=alert_message(result["alert_level"]),
        closest_zone_id=baseline["closest_zone_id"],
        closest_distance_km=baseline["closest_distance_km"],
    )

    _manual_location_fallback()


def show_coordinate_analysis(dataframe: pd.DataFrame):
    st.title("📌 Coordinate-Based Zone Analysis")
    st.write(
        "Assess landslide risk at any latitude/longitude. Rainfall, soil moisture and "
        "elevation can be pulled live from Open-Meteo. Slope is taken from the "
        "nearest monitored zones because Open-Meteo does not provide slope."
    )

    col1, col2 = st.columns(2)
    with col1:
        input_lat = st.number_input(
            "Latitude", value=27.60, format="%.6f", key="coord_lat"
        )
    with col2:
        input_lon = st.number_input(
            "Longitude", value=88.40, format="%.6f", key="coord_lon"
        )

    in_sikkim = not validate_sikkim_coordinates(
        pd.DataFrame({"latitude": [input_lat], "longitude": [input_lon]})
    ).empty

    if not in_sikkim:
        st.warning(
            "These coordinates fall outside the Sikkim pilot area "
            "(27.0–28.3°N, 87.8–89.0°E). The model was trained only on this "
            "region, so predictions elsewhere are not meaningful."
        )

    k = st.slider(
        "Nearest zones to use for rainfall defaults",
        min_value=1,
        max_value=min(10, len(dataframe)),
        value=min(3, len(dataframe)),
    )
    baseline = nearest_zone_baseline(dataframe, input_lat, input_lon, k=k)

    use_live = st.checkbox(
        "Fetch rainfall, elevation & soil moisture live from Open-Meteo",
        value=True,
    )

    live_data, live_error = (None, None)
    if use_live:
        with st.spinner("Querying Open-Meteo..."):
            live_data, live_error = fetch_live_weather(input_lat, input_lon)
        if live_error:
            st.info(
                f"Live Open-Meteo data unavailable ({live_error}). "
                "Falling back to values estimated from the nearest monitored "
                "zones — you can edit them below."
            )

    default_elevation = live_data["elevation"] if live_data else baseline["elevation"]
    default_slope = float(baseline["slope"])
    default_rainfall_24h = live_data["rainfall_24h"] if live_data else baseline["rainfall_24h"]
    default_rainfall_3day = live_data["rainfall_3day"] if live_data else baseline["rainfall_3day"]
    default_rainfall_7day = live_data["rainfall_7day"] if live_data else baseline["rainfall_7day"]
    default_soil_moisture = (
        live_data["soil_moisture"]
        if live_data and live_data.get("soil_moisture") is not None
        else baseline["soil_moisture"]
    )

    st.markdown("### Site conditions")
    st.caption(
        f"Rainfall defaults blended from the {k} nearest monitored zones "
        f"(closest: {baseline['closest_zone_id']}, "
        f"{baseline['closest_distance_km']:.1f} km away)"
        + (" · live weather/elevation/soil from Open-Meteo; slope from nearest zone." if live_data else " · live data unavailable; using nearby-zone estimates.")
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        rainfall_24h = st.number_input(
            "Rainfall — 24h (mm)", min_value=0.0, value=float(default_rainfall_24h), step=1.0
        )
        rainfall_3day = st.number_input(
            "Rainfall — 3 day (mm)", min_value=0.0, value=float(default_rainfall_3day), step=1.0
        )
        rainfall_7day = st.number_input(
            "Rainfall — 7 day (mm)", min_value=0.0, value=float(default_rainfall_7day), step=1.0
        )
    with c2:
        elevation = st.number_input(
            "Elevation (m)", min_value=0.0, value=float(default_elevation), step=10.0
        )
        slope = st.number_input(
            "Slope (°)", min_value=0.0, max_value=90.0, value=float(default_slope), step=1.0
        )
        soil_moisture = st.number_input(
            "Soil moisture (0–1)", min_value=0.0, max_value=1.0,
            value=float(default_soil_moisture), step=0.01,
        )
    with c3:
        land_cover_options = list(LAND_COVER_MAPPING.keys())
        default_land_cover = baseline["land_cover"] if baseline["land_cover"] in land_cover_options else "grassland"
        land_cover = st.selectbox(
            "Land cover",
            options=land_cover_options,
            index=land_cover_options.index(default_land_cover),
        )
        historical_choice = st.radio(
            "Historical landslide activity at/near this point?",
            options=["No", "Yes"],
            index=int(baseline["historical_landslide"]),
            horizontal=True,
        )
        historical_landslide = 1 if historical_choice == "Yes" else 0

    if st.button("Run risk assessment", type="primary"):
        result = assess_custom_location(
            input_lat,
            input_lon,
            rainfall_24h,
            rainfall_3day,
            rainfall_7day,
            soil_moisture,
            elevation,
            slope,
            land_cover,
            historical_landslide,
        )

        log_prediction(
            {
                "user_email": st.session_state.get("user_email"),
                "user_role": current_role(),
                "source": "Coordinate Analysis",
                "zone_id": f"Custom point ({input_lat:.4f}, {input_lon:.4f})",
                "latitude": float(input_lat),
                "longitude": float(input_lon),
                "location_description": reverse_geocode(input_lat, input_lon),
                "rainfall_24h": float(rainfall_24h),
                "rainfall_3day": float(rainfall_3day),
                "rainfall_7day": float(rainfall_7day),
                "soil_moisture": float(soil_moisture),
                "elevation": float(elevation),
                "slope": float(slope),
                "land_cover": land_cover,
                "historical_landslide": int(historical_landslide),
                "risk_score": float(result["risk_score"]),
                "risk_level": result["risk_level"],
                "alert_level": result["alert_level"],
                "model_probability": float(result["model_probability"]),
            }
        )

        st.markdown("### Result")
        left, right = st.columns([1, 1])
        with left:
            render_risk_gauge(float(result["risk_score"]), result["risk_level"])
        with right:
            st.write(f"Model probability: **{result['model_probability'] * 100:.1f}%**")
            st.write("Risk drivers:")
            for driver in result["risk_drivers"].split("|"):
                st.write(f"• {driver}")

        if result["alert_level"] != "NONE":
            render_alert_card(
                result["alert_level"],
                result["risk_score"],
                f"Point ({input_lat:.4f}, {input_lon:.4f})",
                alert_message(result["alert_level"]),
            )
        else:
            st.success("No prototype alert is triggered at these coordinates.")

        st.markdown("### Map context")
        fmap = folium.Map(location=[input_lat, input_lon], zoom_start=10, tiles="OpenStreetMap")
        folium.Marker(
            location=[input_lat, input_lon],
            tooltip="Queried point",
            popup=f"({input_lat:.4f}, {input_lon:.4f})",
            icon=folium.Icon(color="blue", icon="crosshairs", prefix="fa"),
        ).add_to(fmap)

        for _, row in baseline["nearest_table"].iterrows():
            color = risk_color(row["risk_score"])
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=8,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=f"{row['zone_id']} — {row['risk_level']} ({row['distance_km']:.1f} km)",
            ).add_to(fmap)

        st_folium(fmap, width=None, height=480, returned_objects=[])

        st.caption(
            "Prototype estimate only — not an official landslide warning. "
            + ("Live weather/soil/elevation values are from Open-Meteo; slope is from the nearest monitored zones."
               if live_data else "Weather/terrain values are interpolated from nearby monitored zones.")
        )


def show_overview(dataframe: pd.DataFrame):
    st.title("🏔️ NER Landslide AI")
    st.subheader("Early Warning & Risk Monitoring System")

    st.info(
        "Prototype decision-support system for Sikkim. "
        "The risk values are not official government warning thresholds."
    )

    total_zones = len(dataframe)
    high_risk = int((dataframe["risk_score"] >= 51).sum())
    critical = int((dataframe["risk_score"] >= 76).sum())
    warnings = int((dataframe["alert_level"].isin(["WARNING", "CRITICAL"])).sum())

    render_metric_cards(total_zones, high_risk, critical, warnings)

    st.markdown("---")
    render_user_location_panel(dataframe)
    st.markdown("---")

    left, right = st.columns(2)

    with left:
        st.markdown("### Risk distribution")
        risk_counts = (
            dataframe["risk_level"]
            .value_counts()
            .rename_axis("Risk level")
            .reset_index(name="Zones")
        )
        order = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
        risk_counts["Risk level"] = pd.Categorical(
            risk_counts["Risk level"],
            categories=order,
            ordered=True,
        )
        risk_counts = risk_counts.sort_values("Risk level")

        fig = px.bar(
            risk_counts,
            x="Risk level",
            y="Zones",
            color="Risk level",
            color_discrete_map={
                "LOW": "#2ca02c",
                "MODERATE": "#f1c40f",
                "HIGH": "#e67e22",
                "CRITICAL": "#d62728",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Average environmental conditions")
        averages = pd.DataFrame(
            {
                "Feature": [
                    "Rainfall 24h",
                    "Rainfall 3-day",
                    "Rainfall 7-day",
                    "Soil moisture",
                    "Slope",
                ],
                "Value": [
                    dataframe["rainfall_24h"].mean(),
                    dataframe["rainfall_3day"].mean(),
                    dataframe["rainfall_7day"].mean(),
                    dataframe["soil_moisture"].mean() * 100,
                    dataframe["slope"].mean(),
                ],
            }
        )

        fig = px.bar(
            averages,
            x="Feature",
            y="Value",
            color="Feature",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Highest-risk zones")
    columns = [
        "zone_id",
        "risk_score",
        "risk_level",
        "alert_level",
        "rainfall_24h",
        "soil_moisture",
        "slope",
    ]
    st.dataframe(
        dataframe.sort_values("risk_score", ascending=False)[columns].head(10),
        use_container_width=True,
        hide_index=True,
    )


def show_map(dataframe: pd.DataFrame):
    st.title("🗺️ Interactive Risk Map")

    selected_zone = st.selectbox(
        "Select a zone to highlight",
        options=["None"] + sorted(dataframe["zone_id"].unique().tolist()),
    )

    selected_zone = None if selected_zone == "None" else selected_zone

    fmap = create_risk_map(dataframe, selected_zone)
    st_folium(fmap, width=None, height=650, returned_objects=[])


def show_zone_analysis(dataframe: pd.DataFrame):
    st.title("📍 Zone Analysis")

    selected_zone = st.selectbox(
        "Choose a zone",
        sorted(dataframe["zone_id"].unique().tolist()),
    )

    zone = dataframe[dataframe["zone_id"] == selected_zone].iloc[0]
    score = float(zone["risk_score"])

    left, right = st.columns([1, 1])

    with left:
        render_risk_gauge(score, zone["risk_level"])
        st.markdown(f"### {selected_zone}")
        st.write(f"Coordinates: {zone['latitude']:.4f}, {zone['longitude']:.4f}")
        st.write(f"Historical landslide events: {int(zone['historical_landslide'])}")

    with right:
        st.markdown("### Environmental features")
        feature_table = pd.DataFrame(
            {
                "Feature": [
                    "Rainfall — 24 hours",
                    "Rainfall — 3 days",
                    "Rainfall — 7 days",
                    "Soil moisture",
                    "Elevation",
                    "Slope",
                    "Land cover",
                ],
                "Value": [
                    f"{zone['rainfall_24h']:.1f} mm",
                    f"{zone['rainfall_3day']:.1f} mm",
                    f"{zone['rainfall_7day']:.1f} mm",
                    f"{zone['soil_moisture']:.2f}",
                    f"{zone['elevation']:.0f} m",
                    f"{zone['slope']:.1f}°",
                    zone["land_cover"],
                ],
            }
        )
        st.table(feature_table)

    st.markdown("### Main risk drivers")
    drivers = zone["risk_drivers"].split("|")

    for driver in drivers:
        st.write(f"• {driver}")

    if zone["alert_level"] != "NONE":
        render_alert_card(
            zone["alert_level"],
            score,
            selected_zone,
            alert_message(zone["alert_level"]),
        )


def show_alerts(dataframe: pd.DataFrame):
    st.title("🚨 Alerts")

    alerts = dataframe[dataframe["alert_level"] != "NONE"].copy()
    alerts = alerts.sort_values("risk_score", ascending=False)

    if alerts.empty:
        st.success("No active prototype alerts.")
        return

    for _, zone in alerts.iterrows():
        render_alert_card(
            zone["alert_level"],
            zone["risk_score"],
            zone["zone_id"],
            alert_message(zone["alert_level"]),
        )


def show_simulator(dataframe: pd.DataFrame):
    st.title("🌧️ Rainfall Scenario Simulator")

    selected_zone = st.selectbox(
        "Choose a zone to simulate",
        sorted(dataframe["zone_id"].unique().tolist()),
        key="sim_zone",
    )

    zone = dataframe[dataframe["zone_id"] == selected_zone].iloc[0]
    original_rainfall = float(zone["rainfall_24h"])

    st.metric("Current 24-hour rainfall", f"{original_rainfall:.1f} mm")

    increase = st.slider(
        "Additional simulated rainfall",
        min_value=0,
        max_value=300,
        value=50,
        step=10,
    )

    simulated = zone.copy()
    simulated["rainfall_24h"] = original_rainfall + increase
    simulated["rainfall_3day"] = float(zone["rainfall_3day"]) + increase
    simulated["rainfall_7day"] = float(zone["rainfall_7day"]) + increase

    result = predict_single(simulated)
    new_score = result["risk_score"]
    new_level = result["risk_level"]
    new_alert = result["alert_level"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Simulated rainfall", f"{simulated['rainfall_24h']:.1f} mm")
    col2.metric("New risk score", f"{new_score:.1f}/100")
    col3.metric("New risk level", new_level)

    render_risk_gauge(new_score, new_level)

    if new_alert != "NONE":
        render_alert_card(
            new_alert,
            new_score,
            selected_zone,
            alert_message(new_alert),
        )
    else:
        st.success("No prototype alert is triggered at this rainfall level.")

    comparison = pd.DataFrame(
        {
            "Scenario": ["Current", "Simulated"],
            "Rainfall 24h": [original_rainfall, simulated["rainfall_24h"]],
            "Risk score": [zone["risk_score"], new_score],
        }
    )

    fig = px.bar(
        comparison,
        x="Scenario",
        y=["Rainfall 24h", "Risk score"],
        barmode="group",
        title="Current versus simulated scenario",
    )
    st.plotly_chart(fig, use_container_width=True)

    if st.button("💾 Save this scenario to history"):
        log_prediction(
            {
                "user_email": st.session_state.get("user_email"),
                "user_role": current_role(),
                "source": "Rainfall Simulator",
                "zone_id": selected_zone,
                "latitude": float(zone["latitude"]),
                "longitude": float(zone["longitude"]),
                "location_description": None,
                "rainfall_24h": float(simulated["rainfall_24h"]),
                "rainfall_3day": float(simulated["rainfall_3day"]),
                "rainfall_7day": float(simulated["rainfall_7day"]),
                "soil_moisture": float(zone["soil_moisture"]),
                "elevation": float(zone["elevation"]),
                "slope": float(zone["slope"]),
                "land_cover": zone["land_cover"],
                "historical_landslide": int(zone["historical_landslide"]),
                "risk_score": float(new_score),
                "risk_level": new_level,
                "alert_level": new_alert,
                "model_probability": float(result.get("model_probability", 0.0)),
            }
        )
        st.success("Scenario saved to the geographic/prediction history.")


def show_database(dataframe: pd.DataFrame):
    """Admin-only page: user/role management plus full access to the
    monitoring database (demo dataset)."""
    st.title("🗄️ Database & Admin Panel")
    st.caption(
        "Admin workspace — manage account roles and inspect the monitoring "
        "database."
    )

    st.markdown("### 👥 User management")
    users = list_users()

    if not users:
        st.info("No user accounts have been created yet.")
    else:
        st.dataframe(
            pd.DataFrame(users),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Change a user's role")
        user_options = {f"{u['full_name']} ({u['email']})": u for u in users}
        selected_label = st.selectbox("User", list(user_options.keys()))
        selected_user = user_options[selected_label]

        current_role_name = selected_user["role"]
        new_role = st.selectbox(
            "New role",
            list(ROLES),
            index=list(ROLES).index(current_role_name),
        )

        if st.button("Update role", type="primary"):
            if new_role == current_role_name:
                st.info("The selected role is unchanged.")
            else:
                success, message = update_user_role(selected_user["id"], new_role)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    st.markdown("### 🗃️ Monitoring database")
    st.caption(f"{len(dataframe):,} zones in the pilot dataset.")
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    st.download_button(
        "Download dataset (CSV)",
        dataframe.to_csv(index=False).encode("utf-8"),
        file_name="pahad_guard_dataset.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.markdown("### 📜 User & Department login/signup logs")
    st.caption(
        "Every login and sign-up attempt (successful or failed) by every "
        "User and Department account, with full details."
    )
    auth_logs = list_auth_logs()
    if not auth_logs:
        st.info("No login/signup activity has been recorded yet.")
    else:
        auth_logs_df = pd.DataFrame(auth_logs)
        st.dataframe(auth_logs_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download auth logs (CSV)",
            auth_logs_df.to_csv(index=False).encode("utf-8"),
            file_name="pahad_guard_auth_logs.csv",
            mime="text/csv",
        )

    st.markdown("---")
    st.markdown("### 🧭 Geographic data & prediction history")
    st.caption(
        "Every stored risk lookup (coordinate analysis, saved rainfall "
        "simulations) across all accounts — full geographic and prediction "
        "details, downloadable as CSV or as a printable invoice."
    )
    prediction_logs = list_prediction_logs()
    if not prediction_logs:
        st.info("No geographic/prediction history has been recorded yet.")
    else:
        prediction_logs_df = pd.DataFrame(prediction_logs)
        st.dataframe(prediction_logs_df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Download history (CSV)",
                prediction_logs_df.to_csv(index=False).encode("utf-8"),
                file_name="pahad_guard_prediction_history.csv",
                mime="text/csv",
            )
        with col2:
            invoice_pdf = build_prediction_invoice_pdf(
                prediction_logs,
                generated_for=st.session_state.get("user_email", ""),
                generated_by_role="admin",
            )
            st.download_button(
                "🧾 Download as invoice (PDF)",
                invoice_pdf,
                file_name="pahad_guard_prediction_invoice.pdf",
                mime="application/pdf",
            )


def main():
    st.set_page_config(
        page_title="NER Landslide AI",
        page_icon="🏔️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_application()
    init_location_state()

    dataframe = get_data()
    dataframe = prepare_features(dataframe)
    dataframe = predict_dataframe(dataframe)

    if not st.session_state.location_prompted:
        location_choice_dialog()

    role = current_role()
    allowed_pages = ROLE_PAGES.get(role, ROLE_PAGES[DEFAULT_ROLE])

    # Backend guard: never let a page outside the role's allowed set render,
    # even if the radio's session value is stale (e.g. after a re-login).
    if st.session_state.get("selected_page") not in allowed_pages:
        st.session_state["selected_page"] = allowed_pages[0]

    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Open page",
        allowed_pages,
        index=allowed_pages.index(st.session_state["selected_page"]),
        key="selected_page",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Pilot area: {PILOT_AREA}")
    st.sidebar.caption("Prototype — not an official warning service")

    st.sidebar.markdown("---")
    location_mode = st.session_state.location_mode
    if location_mode == "live":
        st.sidebar.caption("📍 Location sharing: 🔴 Live")
    elif location_mode == "current":
        st.sidebar.caption("📍 Location sharing: Current (one-time)")
    else:
        st.sidebar.caption("📍 Location sharing: Off")

    st.sidebar.markdown("---")
    role_badge = {
        "admin": "🛡️ Admin",
        "department": "🏛️ Department",
        "user": "👤 User",
    }.get(role, "👤 User")
    st.sidebar.caption(
        f"{role_badge} — {st.session_state.get('user_name') or st.session_state.get('user_email')}"
    )
    st.sidebar.caption(f"Access level: {role}")
    if st.sidebar.button("Log out"):
        logout()
        st.rerun()

    if page == "Overview":
        show_overview(dataframe)
    elif page == "Risk Map":
        show_map(dataframe)
    elif page == "Zone Analysis":
        show_zone_analysis(dataframe)
    elif page == "Coordinate Analysis":
        show_coordinate_analysis(dataframe)
    elif page == "Alerts":
        show_alerts(dataframe)
    elif page == "Rainfall Simulator":
        show_simulator(dataframe)
    elif page == "Database":
        show_database(dataframe)


if __name__ == "__main__":
    if is_authenticated():
        main()
    else:
        render_auth_page()