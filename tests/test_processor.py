from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CertificateItem, CertificateItemStatus, Job, JobStatus
from app.services.job_service import create_job
from app.services.processor import recover_processing_jobs
from app.schemas import JobCreateRequest


def _create_job(db: Session, recipients: list[dict[str, str]]) -> Job:
    request = JobCreateRequest(
        event_name="Bootcamp",
        issue_date="2026-10-07",
        recipients=[{"name": name, "email": email} for name, email in recipients],
    )
    return create_job(db, request)


def test_background_processor_completes_successful_job(client: TestClient):
    job_id = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [
                {"name": "Asha Rao", "email": "asha@example.com"},
                {"name": "John Doe", "email": "john@example.com"},
            ],
        },
    ).json()["job_id"]

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert data["pending"] == 0
    assert len(data["items"]) == 2
    assert all(item["status"] == "SUCCESS" for item in data["items"])


def test_processor_marks_failed_item_without_stopping_other_items(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    original = __import__("app.services.processor", fromlist=["render_certificate"]).render_certificate

    def failing_renderer(name: str, event_name: str, issue_date: str):
        if name == "John Doe":
            raise RuntimeError("Renderer failed")
        return original(name, event_name, issue_date)

    monkeypatch.setattr("app.services.processor.render_certificate", failing_renderer)

    job_id = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [
                {"name": "Asha Rao", "email": "asha@example.com"},
                {"name": "John Doe", "email": "john@example.com"},
            ],
        },
    ).json()["job_id"]

    response = client.get(f"/jobs/{job_id}")
    data = response.json()
    assert data["status"] == "COMPLETED_WITH_ERRORS"
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["items"][1]["status"] == "FAILED"
    assert "Renderer failed" in data["items"][1]["error_message"]


def test_processor_marks_job_failed_when_unexpected_error_occurs(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def broken_renderer(name: str, event_name: str, issue_date: str):
        raise RuntimeError("Unknown renderer error")

    monkeypatch.setattr("app.services.processor.render_certificate", broken_renderer)
    job_id = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "Asha Rao", "email": "asha@example.com"}],
        },
    ).json()["job_id"]

    response = client.get(f"/jobs/{job_id}")
    assert response.json()["status"] == "FAILED"


def test_recover_processing_jobs_retries_pending_items(temp_db: None):
    from app.models import CertificateItem, CertificateItemStatus, Job, JobStatus

    db = SessionLocal()
    job_id = "job-recover-" + str(abs(hash("recover")))
    job = Job(
        id=job_id,
        event_name="Bootcamp",
        issue_date=date(2026, 10, 7),
        status=JobStatus.PROCESSING,
        total=2,
    )
    db.add(job)
    db.add_all(
        [
            CertificateItem(id=f"{job_id}-pending", job_id=job.id, recipient_name="Asha", recipient_email="asha@example.com", status=CertificateItemStatus.PENDING),
            CertificateItem(id=f"{job_id}-success", job_id=job.id, recipient_name="John", recipient_email="john@example.com", status=CertificateItemStatus.SUCCESS, file_path="existing.pdf"),
        ]
    )
    db.commit()

    recover_processing_jobs(db)
    recovered = db.get(Job, job.id)
    assert recovered.status == JobStatus.PENDING

    db.close()
