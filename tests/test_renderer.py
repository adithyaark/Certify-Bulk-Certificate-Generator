from pathlib import Path

import pytest

from app.services.renderer import render_certificate
from app.services.storage import save_certificate_file


def test_render_certificate_returns_pdf_bytes():
    pdf_bytes = render_certificate(
        "Asha Rao",
        "Python Bootcamp 2026",
        "2026-10-07",
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100


def test_render_certificate_supports_unicode_and_long_names(tmp_path: Path):
    long_name = "नमस्ते " * 40
    pdf_path = tmp_path / "certificate.pdf"

    pdf_bytes = render_certificate(long_name, "Python Bootcamp 2026", "2026-10-07")
    save_certificate_file(pdf_path, pdf_bytes)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert pdf_bytes.startswith(b"%PDF")


def test_render_certificate_fails_with_invalid_input():
    with pytest.raises(ValueError, match="name"):
        render_certificate("", "Event", "2026-10-07")

    with pytest.raises(ValueError, match="issue_date"):
        render_certificate("Asha", "Event", "not-a-date")
