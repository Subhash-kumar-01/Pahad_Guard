"""Generate a downloadable PDF "invoice" summarising stored geographic /
prediction history records.

Kept isolated from the Streamlit app so it can be unit-tested on its own.
Uses ``reportlab`` (already a common, lightweight, dependency-free-at-import
PDF library) — no network access required to build the document.
"""

from datetime import datetime, timezone
from io import BytesIO
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INVOICE_COLUMNS = [
    ("timestamp", "Timestamp (UTC)"),
    ("source", "Source"),
    ("user_email", "Requested by"),
    ("zone_id", "Zone / Point"),
    ("latitude", "Lat"),
    ("longitude", "Lon"),
    ("rainfall_24h", "Rain 24h (mm)"),
    ("soil_moisture", "Soil moisture"),
    ("elevation", "Elevation (m)"),
    ("slope", "Slope (°)"),
    ("risk_score", "Risk score"),
    ("risk_level", "Risk level"),
    ("alert_level", "Alert"),
]


def _format_cell(record: dict, key: str):
    value = record.get(key)
    if value is None:
        return "—"
    if key in ("latitude", "longitude", "slope"):
        return f"{float(value):.4f}"
    if key in ("rainfall_24h", "elevation", "risk_score"):
        return f"{float(value):.1f}"
    if key == "soil_moisture":
        return f"{float(value):.2f}"
    return str(value)


def build_prediction_invoice_pdf(
    records: Sequence[dict],
    generated_for: str = "",
    generated_by_role: str = "",
) -> bytes:
    """Build a PDF invoice/report for a list of prediction-log dict rows
    (as returned by ``src.auth.database.list_prediction_logs``).

    Returns raw PDF bytes, ready for a Streamlit ``download_button``.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title="Pahad Guard — Geographic & Prediction History Invoice",
    )

    styles = getSampleStyleSheet()
    story = []

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    story.append(Paragraph("🏔️ Pahad Guard", styles["Title"]))
    story.append(
        Paragraph(
            "Geographic Data &amp; Prediction History — Invoice",
            styles["Heading2"],
        )
    )
    story.append(Spacer(1, 6))

    meta_lines = [f"Generated: {generated_at}"]
    if generated_for:
        meta_lines.append(f"Requested by: {generated_for}")
    if generated_by_role:
        meta_lines.append(f"Role: {generated_by_role}")
    meta_lines.append(f"Total records: {len(records)}")

    for line in meta_lines:
        story.append(Paragraph(line, styles["Normal"]))

    story.append(Spacer(1, 12))

    header = [label for _, label in INVOICE_COLUMNS]
    table_data = [header]
    for record in records:
        table_data.append(
            [_format_cell(record, key) for key, _ in INVOICE_COLUMNS]
        )

    if len(table_data) == 1:
        story.append(Paragraph("No history records to report.", styles["Normal"]))
    else:
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f4c81")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)

    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            "This is an auto-generated prototype report, not an official "
            "landslide warning or government document.",
            styles["Italic"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
