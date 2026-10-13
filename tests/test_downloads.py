from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient


def test_single_certificate_download_returns_pdf(client: TestClient):
    job_id = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "Asha Rao", "email": "asha@example.com"}],
        },
    ).json()["job_id"]

    item_id = client.get(f"/jobs/{job_id}").json()["items"][0]["id"]
    response = client.get(f"/jobs/{job_id}/certificates/{item_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith('attachment; filename="certificate-')
    assert response.content.startswith(b"%PDF")


def test_zip_download_contains_successful_certificates(client: TestClient):
    response = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [
                {"name": "Asha Rao", "email": "asha@example.com"},
                {"name": "John Doe", "email": "john@example.com"},
            ],
        },
    )
    job_id = response.json()["job_id"]

    zip_response = client.get(f"/jobs/{job_id}/download")

    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
        assert len(archive.namelist()) == 2
        assert all(name.endswith(".pdf") for name in archive.namelist())
        assert all(archive.read(name).startswith(b"%PDF") for name in archive.namelist())


def test_certificate_download_rejects_missing_or_unready_or_wrong_job_items(client: TestClient):
    job_response = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "Asha Rao", "email": "asha@example.com"}],
        },
    )
    job_id = job_response.json()["job_id"]
    item_id = client.get(f"/jobs/{job_id}").json()["items"][0]["id"]

    missing = client.get(f"/jobs/{job_id}/certificates/does-not-exist")
    assert missing.status_code == 404

    ready_response = client.get(f"/jobs/{job_id}/certificates/{item_id}")
    assert ready_response.status_code == 200

    failing_job = client.post(
        "/jobs",
        json={
            "event_name": "Failed Event",
            "issue_date": "2026-10-08",
            "recipients": [{"name": "Asha Rao", "email": "invalid"}],
        },
    ).json()["job_id"]
    failed_item = client.get(f"/jobs/{failing_job}").json()["items"][0]["id"]
    failed_response = client.get(f"/jobs/{failing_job}/certificates/{failed_item}")
    assert failed_response.status_code == 409

    other_job = client.post(
        "/jobs",
        json={
            "event_name": "Other Event",
            "issue_date": "2026-10-08",
            "recipients": [{"name": "John Doe", "email": "john@example.com"}],
        },
    ).json()["job_id"]
    other_item = client.get(f"/jobs/{other_job}").json()["items"][0]["id"]
    wrong_job_response = client.get(f"/jobs/{job_id}/certificates/{other_item}")
    assert wrong_job_response.status_code == 404


def test_zip_download_returns_clear_error_when_no_certificates_are_ready(client: TestClient):
    job_id = client.post(
        "/jobs",
        json={
            "event_name": "Bootcamp",
            "issue_date": "2026-10-07",
            "recipients": [{"name": "Asha Rao", "email": "invalid"}],
        },
    ).json()["job_id"]

    response = client.get(f"/jobs/{job_id}/download")

    assert response.status_code == 404
    assert "No certificates are ready" in response.json()["detail"]
