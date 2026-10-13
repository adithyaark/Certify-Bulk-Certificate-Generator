from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CertificateItem, CertificateItemStatus, Job, JobStatus
from app.schemas import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.storage import ensure_within_storage_dir

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*$")


def _validate_recipient(recipient: dict[str, str]) -> tuple[str, str]:
    name = (recipient.get("name") or "").strip()
    email = (recipient.get("email") or "").strip()

    if not 1 <= len(name) <= 100:
        raise ValueError("Recipient name is required and must be 1-100 characters")
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Invalid email format")
    return name, email


def _get_item_status_counts(db: Session, job_id: str) -> dict[str, int]:
    counts = {
        "succeeded": 0,
        "failed": 0,
        "pending": 0,
    }
    result = db.execute(
        select(
            func.count(case((CertificateItem.status == CertificateItemStatus.SUCCESS, 1))),
            func.count(case((CertificateItem.status == CertificateItemStatus.FAILED, 1))),
            func.count(case((CertificateItem.status == CertificateItemStatus.PENDING, 1))),
        ).where(CertificateItem.job_id == job_id)
    ).one()
    counts["succeeded"], counts["failed"], counts["pending"] = result
    return counts


def _item_to_response(item: CertificateItem) -> dict[str, object]:
    return {
        "id": item.id,
        "recipient_name": item.recipient_name,
        "recipient_email": item.recipient_email,
        "status": item.status,
        "error_message": item.error_message,
        "download_url": (
            f"/jobs/{item.job_id}/certificates/{item.id}" if item.status == CertificateItemStatus.SUCCESS else None
        ),
    }


def _get_job_item(db: Session, job_id: str, item_id: str) -> CertificateItem:
    item = db.execute(
        select(CertificateItem).where(
            CertificateItem.job_id == job_id,
            CertificateItem.id == item_id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate item not found")
    return item


def _sanitize_zip_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._ -]", "_", name.strip())
    return sanitized or "certificate"


def get_certificate(db: Session, job_id: str, item_id: str) -> tuple[bytes, str]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    item = _get_job_item(db, job_id, item_id)
    if item.status != CertificateItemStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate is not ready for download",
        )
    if not item.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate file is missing",
        )

    storage_root = Path(get_settings().storage_dir).resolve()
    candidate = ensure_within_storage_dir(storage_root, item.file_path)
    try:
        return candidate.read_bytes(), f"certificate-{item.id}.pdf"
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate file not found") from exc


def get_job_certificate_zip(db: Session, job_id: str) -> tuple[bytes, str]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    successful_items = db.execute(
        select(CertificateItem)
        .where(
            CertificateItem.job_id == job_id,
            CertificateItem.status == CertificateItemStatus.SUCCESS,
        )
        .order_by(CertificateItem.created_at)
    ).scalars().all()
    if not successful_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No certificates are ready")

    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in successful_items:
            if not item.file_path:
                continue
            storage_root = Path(get_settings().storage_dir).resolve()
            file_path = ensure_within_storage_dir(storage_root, item.file_path)
            if not file_path.exists():
                continue

            base_name = _sanitize_zip_name(item.recipient_name)
            zip_name = base_name + ".pdf"
            index = 1
            while zip_name in used_names:
                zip_name = f"{base_name}-{index}.pdf"
                index += 1
            used_names.add(zip_name)
            archive.writestr(zip_name, file_path.read_bytes())

    if not used_names:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No certificates are ready")

    return buffer.getvalue(), f"{job.event_name.strip() or 'certificates'}.zip"


def create_job(db: Session, request: JobCreateRequest) -> JobCreateResponse:
    settings = get_settings()
    if len(request.recipients) > settings.max_recipients_per_job:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Too many recipients: maximum {settings.max_recipients_per_job} allowed",
        )

    seen: set[tuple[str, str]] = set()
    job = Job(
        id=str(uuid.uuid4()),
        event_name=request.event_name,
        issue_date=request.issue_date,
        status=JobStatus.PENDING,
        total=len(request.recipients),
    )
    db.add(job)
    db.flush()

    for recipient in request.recipients:
        key = (recipient.name.strip().lower(), recipient.email.strip().lower())
        status_value = CertificateItemStatus.PENDING
        error_message = None

        try:
            name, email = _validate_recipient(recipient.model_dump())
            if key in seen:
                status_value = CertificateItemStatus.FAILED
                error_message = "Duplicate recipient in this request"
            else:
                seen.add(key)
        except ValueError as exc:
            name = (recipient.name or "").strip()
            email = (recipient.email or "").strip()
            status_value = CertificateItemStatus.FAILED
            error_message = str(exc)

        item = CertificateItem(
            id=str(uuid.uuid4()),
            job_id=job.id,
            recipient_name=name[:100],
            recipient_email=email,
            status=status_value,
            error_message=error_message,
        )
        db.add(item)

    db.commit()
    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total=job.total,
        status_url=f"/jobs/{job.id}",
    )


def get_job(db: Session, job_id: str, offset: int = 0, limit: int = 50, status_filter: str | None = None) -> JobStatusResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    query = select(CertificateItem).where(CertificateItem.job_id == job_id)
    if status_filter:
        query = query.where(CertificateItem.status == status_filter)
    query = query.order_by(CertificateItem.created_at).offset(offset).limit(limit)
    items = db.scalars(query).all()
    counts = _get_item_status_counts(db, job_id)

    return JobStatusResponse(
        job_id=job.id,
        event_name=job.event_name,
        status=job.status,
        total=job.total,
        succeeded=counts["succeeded"],
        failed=counts["failed"],
        pending=counts["pending"],
        created_at=job.created_at,
        completed_at=job.completed_at,
        items=[_item_to_response(item) for item in items],
    )
