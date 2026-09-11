"""Browser geolocation + reverse geocoding helpers.

These power the "share your location" pop-up and the location-risk block
on the dashboard. Two optional third-party pieces are involved:

- ``streamlit-js-eval`` is used to ask the *browser* (not the server) for
  the user's GPS coordinates via ``navigator.geolocation``. This requires
  the page to be served over HTTPS or ``localhost`` — browsers refuse the
  Geolocation API on plain HTTP.
- OpenStreetMap's Nominatim reverse-geocoding endpoint turns coordinates
  into a short, human-readable place name. It needs outbound internet
  access and is free but rate-limited; no API key is required.

Everything here degrades gracefully: if the optional dependency isn't
installed, or the network call fails, callers get a clear error string
back instead of an exception, so the rest of the app keeps working (the
UI falls back to manual coordinate entry / a plain "lat, lon" label).
"""

from __future__ import annotations

import requests

try:
    from streamlit_js_eval import get_geolocation as _get_geolocation

    GEOLOCATION_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _get_geolocation = None
    GEOLOCATION_AVAILABLE = False

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "PahadGuard-LandslideRiskApp/1.0"


def fetch_browser_location(component_key: str):
    """Ask the browser for the user's current GPS coordinates.

    Returns a ``(latitude, longitude, error)`` tuple:

    - On success: ``(lat, lon, None)``.
    - While the browser's permission prompt hasn't been answered yet:
      ``(None, None, "pending")``.
    - On failure (denied, unsupported, package missing, etc.):
      ``(None, None, "<human readable message>")``.
    """
    if not GEOLOCATION_AVAILABLE:
        return None, None, (
            "The 'streamlit-js-eval' package isn't installed, so the browser "
            "can't be asked for your location automatically. Install it with "
            "`pip install streamlit-js-eval`, or enter coordinates manually below."
        )

    try:
        result = _get_geolocation(component_key=component_key)
    except Exception as error:  # defensive: component/runtime errors
        return None, None, f"Couldn't read your browser's location ({error})."

    if result is None:
        return None, None, "pending"

    if isinstance(result, dict) and result.get("coords"):
        coords = result["coords"]
        latitude = coords.get("latitude")
        longitude = coords.get("longitude")
        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude), None
        return None, None, "The browser didn't return usable coordinates."

    if isinstance(result, dict) and result.get("error"):
        error_info = result["error"]
        message = (
            error_info.get("message")
            if isinstance(error_info, dict)
            else str(error_info)
        )
        return None, None, message or "Location permission was denied."

    return None, None, "Couldn't read a location from the browser."


def reverse_geocode(latitude: float, longitude: float) -> str:
    """Turn coordinates into a short, human-readable place description.

    Falls back to a plain coordinate string if the lookup service is
    unreachable (offline, blocked, rate-limited, etc.) so this never
    raises and never blocks showing a risk alert.
    """
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": latitude,
                "lon": longitude,
                "zoom": 14,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return f"Near {latitude:.4f}°N, {longitude:.4f}°E (place lookup unavailable)"

    address = payload.get("address", {}) if isinstance(payload, dict) else {}
    candidate_keys = (
        "village",
        "town",
        "suburb",
        "city",
        "county",
        "state_district",
        "state",
    )
    parts = [address.get(key) for key in candidate_keys if address.get(key)]
    # De-duplicate while preserving order, keep it short (most specific first).
    short_parts = list(dict.fromkeys(parts))[:2]

    if short_parts:
        return ", ".join(short_parts)

    display_name = payload.get("display_name") if isinstance(payload, dict) else None
    if display_name:
        return display_name.split(",")[0]

    return f"Near {latitude:.4f}°N, {longitude:.4f}°E"
