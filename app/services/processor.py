from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CertificateItem, CertificateItemStatus, EmailStatus, Job, JobStatus
from app.services.email import email_configuration_error, safe_email_error_message, send_certificate_email
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
    email_failed = sum(item.email_status == EmailStatus.FAILED for item in total)
    email_pending = sum(item.email_status in {EmailStatus.PENDING, EmailStatus.SENDING} for item in total)

    if failed == 0 and pending == 0 and email_failed == 0 and email_pending == 0:
        status_value = JobStatus.COMPLETED
    elif pending == 0 and email_pending == 0 and (succeeded > 0 or email_failed > 0):
        status_value = JobStatus.COMPLETED_WITH_ERRORS
    elif pending == 0 and email_pending == 0 and failed > 0:
        status_value = JobStatus.FAILED
    else:
        status_value = JobStatus.PENDING

    job.status = status_value
    job.completed_at = datetime.utcnow() if status_value != JobStatus.PENDING else None
    db.commit()


def _read_certificate_file(item: CertificateItem) -> bytes:
    if not item.file_path:
        raise FileNotFoundError("Certificate file is missing")
    storage_root = Path(get_settings().storage_dir).resolve()
    file_path = ensure_within_storage_dir(storage_root, item.file_path)
    return file_path.read_bytes()


def _deliver_email(db: Session, job: Job, item: CertificateItem, pdf_bytes: bytes) -> None:
    settings = get_settings()
    if not settings.email_enabled:
        item.email_status = EmailStatus.SKIPPED
        item.email_error_message = None
        item.email_sent_at = None
        return

    configuration_error = email_configuration_error(settings)
    if configuration_error:
        item.email_status = EmailStatus.FAILED
        item.email_error_message = configuration_error
        item.email_sent_at = None
        return

    item.email_status = EmailStatus.SENDING
    item.email_error_message = None
    db.commit()
    try:
        send_certificate_email(
            recipient_name=item.recipient_name,
            recipient_email=item.recipient_email,
            event_name=job.event_name,
            pdf_bytes=pdf_bytes,
            attachment_filename=f"certificate-{item.id}.pdf",
            message_id=f"<certificate-{item.id}@localhost>",
            settings=settings,
        )
        item.email_status = EmailStatus.SENT
        item.email_sent_at = datetime.utcnow()
        item.email_error_message = None
    except Exception as exc:
        safe_message = safe_email_error_message(exc)
        item.email_status = EmailStatus.FAILED
        item.email_error_message = safe_message
        item.email_sent_at = None
        logger.error("Email delivery failed for job %s item %s: %s", job.id, item.id, safe_message)


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
            .where(
                or_(
                    CertificateItem.status == CertificateItemStatus.PENDING,
                    (
                        (CertificateItem.status == CertificateItemStatus.SUCCESS)
                        & CertificateItem.email_status.in_({EmailStatus.PENDING, EmailStatus.SENDING})
                    ),
                )
            )
            .order_by(CertificateItem.created_at)
        ).scalars().all()

        for item in items:
            try:
                if item.status == CertificateItemStatus.PENDING:
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
                else:
                    pdf_bytes = _read_certificate_file(item)

                _deliver_email(db, job, item, pdf_bytes)
            except Exception as exc:
                if item.status == CertificateItemStatus.PENDING:
                    item.status = CertificateItemStatus.FAILED
                    item.error_message = str(exc)
                    item.file_path = None
                    item.email_status = EmailStatus.SKIPPED
                    item.email_error_message = None
                    logger.exception("Failed certificate generation for job %s item %s", job.id, item.id)
                else:
                    item.email_status = EmailStatus.FAILED
                    safe_message = safe_email_error_message(exc)
                    item.email_error_message = safe_message
                    logger.error("Email preparation failed for job %s item %s: %s", job.id, item.id, safe_message)
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
        for item in job.items:
            if item.email_status == EmailStatus.SENDING:
                item.email_status = EmailStatus.PENDING
        logger.warning("Recovered job %s from PROCESSING state", job.id)

    db.commit()
