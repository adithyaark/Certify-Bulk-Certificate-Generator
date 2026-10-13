from __future__ import annotations

import io
from datetime import date
from importlib.resources import files

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONT_PATH = files("app.fonts").joinpath("DejaVuSans.ttf")
_FONT_PATH_STR = str(_FONT_PATH)


def _validate_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _validate_issue_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("issue_date must be a valid ISO date") from exc


def _register_font() -> None:
    if "DejaVuSans" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("DejaVuSans", _FONT_PATH_STR))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", _FONT_PATH_STR))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Italic", _FONT_PATH_STR))
    pdfmetrics.registerFont(TTFont("DejaVuSans-BoldItalic", _FONT_PATH_STR))


def _fit_text_to_width(text: str, font_name: str, size: int, width: float) -> tuple[str, int]:
    available = max(10, min(size, 72))
    current_size = available
    while current_size > 10:
        if pdfmetrics.stringWidth(text, font_name, current_size) <= width:
            return text, current_size
        current_size -= 1
    return text, current_size


def _draw_centered_spaced(
    buffer: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font_name: str,
    font_size: float,
    character_spacing: float = 0,
) -> None:
    text_width = pdfmetrics.stringWidth(text, font_name, font_size)
    text_object = buffer.beginText()
    text_object.setTextOrigin(x - (text_width + character_spacing * max(0, len(text) - 1)) / 2, y)
    text_object.setFont(font_name, font_size)
    text_object.setCharSpace(character_spacing)
    text_object.textOut(text)
    buffer.drawText(text_object)


def render_certificate(name: str, event_name: str, issue_date: str) -> bytes:
    """Render a certificate as a single-page landscape A4 PDF."""
    clean_name = _validate_required_text(name, "name")
    clean_event = _validate_required_text(event_name, "event_name")
    parsed_date = _validate_issue_date(issue_date)

    _register_font()

    width, height = A4
    page_width, page_height = (height, width)
    buffer = canvas.Canvas(io.BytesIO(), pagesize=(page_width, page_height))
    buffer.setTitle("Certificate of Participation")
    buffer.setAuthor("Bulk Certificate Generator")

    outer_margin = 30
    inner_margin = 51
    outer_border = Color(0.36, 0.56, 0.71)
    inner_border = Color(0.71, 0.79, 0.86)

    # Keep the PDF's two fine blue rules and generous whitespace in sync with
    # the Streamlit preview. The coordinates are intentionally fixed so every
    # recipient gets the same print-ready landscape A4 composition.
    buffer.setFillColor(Color(1, 1, 1))
    buffer.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    buffer.setStrokeColor(outer_border)
    buffer.setLineWidth(3)
    buffer.rect(outer_margin, outer_margin, page_width - 2 * outer_margin, page_height - 2 * outer_margin)
    buffer.setStrokeColor(inner_border)
    buffer.setLineWidth(1)
    buffer.rect(inner_margin, inner_margin, page_width - 2 * inner_margin, page_height - 2 * inner_margin)

    buffer.setFillColor(Color(0.23, 0.44, 0.59))
    _draw_centered_spaced(
        buffer,
        "CERTIFICATE OF PARTICIPATION",
        page_width / 2,
        page_height - 120,
        "Courier",
        9,
        character_spacing=1.1,
    )

    buffer.setFillColor(Color(0.13, 0.23, 0.30))
    heading = "This certificate is proudly presented to"
    heading_text, heading_size = _fit_text_to_width(heading, "Helvetica-Bold", 17, page_width - 180)
    buffer.setFont("Helvetica-Bold", heading_size)
    buffer.drawCentredString(page_width / 2, page_height - 205, heading_text)

    name_font = "Times-Bold" if all(ord(character) < 128 for character in clean_name) else "DejaVuSans"
    name_text, fitted_size = _fit_text_to_width(clean_name, name_font, 30, page_width - 200)
    buffer.setFont(name_font, fitted_size)
    buffer.setFillColor(Color(0.09, 0.17, 0.25))
    buffer.drawCentredString(page_width / 2, page_height - 335, name_text)

    buffer.setFont("Helvetica", 11)
    buffer.setFillColor(Color(0.32, 0.44, 0.52))
    buffer.drawCentredString(page_width / 2, page_height - 390, f"For completing · {clean_event}")

    buffer.setFont("Helvetica", 9)
    buffer.setFillColor(Color(0.32, 0.42, 0.49))
    buffer.drawCentredString(
        page_width / 2,
        80,
        f"Issued on {parsed_date.strftime('%B %d, %Y')}",
    )

    buffer.showPage()
    return buffer.getpdfdata()
