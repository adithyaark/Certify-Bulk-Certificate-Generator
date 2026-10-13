from pathlib import Path

import pytest

from app.services.storage import ensure_within_storage_dir, save_certificate_file


def test_save_certificate_file_writes_bytes(tmp_path: Path):
    pdf_path = tmp_path / "certificate.pdf"

    save_certificate_file(pdf_path, b"%PDF-1.4 test")

    assert pdf_path.read_bytes() == b"%PDF-1.4 test"


def test_ensure_within_storage_dir_rejects_traversal(tmp_path: Path):
    storage_dir = tmp_path / "storage"

    with pytest.raises(ValueError, match="outside the storage directory"):
        ensure_within_storage_dir(storage_dir, "../outside.pdf")

    with pytest.raises(ValueError, match="outside the storage directory"):
        ensure_within_storage_dir(storage_dir, str(tmp_path / "absolute" / "path.pdf"))

    safe_path = ensure_within_storage_dir(storage_dir, "nested/secure.pdf")
    assert safe_path == storage_dir / "nested" / "secure.pdf"
