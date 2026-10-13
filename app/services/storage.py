from __future__ import annotations

from pathlib import Path


def ensure_within_storage_dir(storage_dir: Path, relative_path: str) -> Path:
    """Return a normalized path that is guaranteed to remain inside storage_dir."""
    storage_root = storage_dir.resolve()
    candidate = Path(relative_path)
    candidate = candidate.resolve() if candidate.is_absolute() else (storage_root / candidate).resolve()

    try:
        candidate.relative_to(storage_root)
    except ValueError as exc:
        raise ValueError("Requested file path is outside the storage directory") from exc

    return candidate


def save_certificate_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
