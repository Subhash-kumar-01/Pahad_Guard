import streamlit as st


def render_metric_cards(
    active_zones: int,
    high_risk: int,
    critical: int,
    warnings: int,
):
    columns = st.columns(4)

    columns[0].metric("Active zones", active_zones)
    columns[1].metric("High risk", high_risk)
    columns[2].metric("Critical", critical)
    columns[3].metric("Warnings", warnings)


def render_risk_gauge(score: float, level: str):
    score = max(0, min(100, score))

    st.progress(score / 100)
    st.metric("AI risk score", f"{score:.1f}/100")
    st.subheader(f"Risk level: {level}")


def render_alert_card(
    level: str,
    score: float,
    zone_id: str,
    message: str,
):
    if level == "CRITICAL":
        st.error(
            f"🚨 CRITICAL ALERT\n\n"
            f"Zone: {zone_id}\n\n"
            f"Risk: {score:.1f}/100\n\n"
            f"{message}"
        )
    elif level == "WARNING":
        st.warning(
            f"⚠️ WARNING\n\n"
            f"Zone: {zone_id}\n\n"
            f"Risk: {score:.1f}/100\n\n"
            f"{message}"
        )
    else:
        st.info(
            f"👀 WATCH\n\n"
            f"Zone: {zone_id}\n\n"
            f"Risk: {score:.1f}/100\n\n"
            f"{message}"
        )


def render_location_alert_card(
    description: str,
    latitude: float,
    longitude: float,
    mode_label: str,
    in_pilot_area: bool,
    score: float,
    level: str,
    alert: str,
    message: str,
    closest_zone_id: str,
    closest_distance_km: float,
):
    """Dashboard block: a short description of the user's location plus a
    live risk alert for that point, based on the current or live GPS
    coordinates shared from the browser."""

    with st.container(border=True):
        top_left, top_right = st.columns([3, 2])
        with top_left:
            st.markdown(f"**📍 {description}**")
            st.caption(f"{latitude:.4f}°N, {longitude:.4f}°E")
        with top_right:
            st.caption(mode_label)
            st.caption(
                f"Nearest monitored zone: {closest_zone_id} "
                f"({closest_distance_km:.1f} km away)"
            )

        if not in_pilot_area:
            st.warning(
                "This location is outside the Sikkim pilot area, so this "
                "estimate is not reliable — the model was trained only on "
                "Sikkim data."
            )

        gauge_col, alert_col = st.columns([1, 2])
        with gauge_col:
            render_risk_gauge(score, level)
        with alert_col:
            if alert == "CRITICAL":
                st.error(f"🚨 CRITICAL\n\n{message}")
            elif alert == "WARNING":
                st.warning(f"⚠️ WARNING\n\n{message}")
            elif alert == "WATCH":
                st.info(f"👀 WATCH\n\n{message}")
            else:
                st.success("✅ No prototype alert is triggered at your location.")

        st.caption(
            "Prototype estimate only — not an official landslide warning. "
            "Rainfall/terrain values are approximated from nearby monitored zones."
        )