from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CertificateItem, CertificateItemStatus, Job, JobStatus
from app.services.renderer import render_certificate
from app.services.storage import ensure_within_storage_dir, save_certificate_file

logger = logging.getLogger(__name__)


def _job_storage_directory(job_id: str) -> Path:
    storage_dir = Path(get_settings().storage_dir).resolve()
    return storage_dir / job_id


def _job_file_path(job_id: str, item_id: str) -> Path:
    storage_dir = _job_storage_directory(job_id)
    return ensure_within_storage_dir(storage_dir, f"{item_id}.pdf")


def _finalize_job(db: Session, job: Job) -> None:
    total = db.execute(
        select(CertificateItem).where(CertificateItem.job_id == job.id)
    ).scalars().all()
    succeeded = sum(item.status == CertificateItemStatus.SUCCESS for item in total)
    failed = sum(item.status == CertificateItemStatus.FAILED for item in total)
    pending = sum(item.status == CertificateItemStatus.PENDING for item in total)

    if failed == 0 and pending == 0:
        status_value = JobStatus.COMPLETED
    elif succeeded > 0 and failed > 0:
        status_value = JobStatus.COMPLETED_WITH_ERRORS
    elif pending == 0 and failed > 0:
        status_value = JobStatus.FAILED
    else:
        status_value = JobStatus.PENDING

    job.status = status_value
    job.completed_at = datetime.utcnow() if status_value != JobStatus.PENDING else None
    db.commit()


def process_job(job_id: str) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            logger.warning("Processing requested for unknown job %s", job_id)
            return

        job.status = JobStatus.PROCESSING
        db.commit()

        items = db.execute(
            select(CertificateItem)
            .where(CertificateItem.job_id == job.id)
            .where(CertificateItem.status == CertificateItemStatus.PENDING)
            .order_by(CertificateItem.created_at)
        ).scalars().all()

        for item in items:
            try:
                pdf_bytes = render_certificate(
                    item.recipient_name,
                    job.event_name,
                    job.issue_date.isoformat(),
                )
                file_path = _job_file_path(job.id, item.id)
                save_certificate_file(file_path, pdf_bytes)
                item.file_path = str(file_path)
                item.status = CertificateItemStatus.SUCCESS
                item.error_message = None
                logger.info("Generated certificate for job %s item %s", job.id, item.id)
            except Exception as exc:
                item.status = CertificateItemStatus.FAILED
                item.error_message = str(exc)
                item.file_path = None
                logger.exception("Failed certificate generation for job %s item %s", job.id, item.id)
            finally:
                db.commit()

        _finalize_job(db, job)
    except Exception as exc:
        job = db.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            db.commit()
        logger.exception("Unexpected error while processing job %s: %s", job_id, exc)
    finally:
        db.close()


def recover_processing_jobs(db: Session) -> None:
    jobs = db.execute(
        select(Job).where(Job.status == JobStatus.PROCESSING)
    ).scalars().all()

    for job in jobs:
        job.status = JobStatus.PENDING
        job.completed_at = None
        logger.warning("Recovered job %s from PROCESSING state", job.id)

    db.commit()
