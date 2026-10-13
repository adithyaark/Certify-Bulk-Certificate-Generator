from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_job_returns_202_and_persists_records(client: TestClient):
    payload = {
        "event_name": "Python Bootcamp 2026",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Asha Rao", "email": "asha@example.com"},
            {"name": "John Doe", "email": "john@example.com"},
        ],
    }

    response = client.post("/jobs", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["total"] == 2
    assert data["job_id"]
    assert data["status_url"].endswith(f"/jobs/{data['job_id']}")

    job_response = client.get(f"/jobs/{data['job_id']}")
    assert job_response.status_code == 200
    job_data = job_response.json()
    assert job_data["total"] == 2
    assert job_data["succeeded"] == 2
    assert job_data["failed"] == 0
    assert job_data["pending"] == 0
    assert len(job_data["items"]) == 2


def test_create_job_rejects_invalid_request_level_fields(client: TestClient):
    test_cases = [
        {"event_name": "", "issue_date": "2026-10-07", "recipients": [{"name": "Asha", "email": "asha@example.com"}]},
        {"event_name": "Event", "issue_date": "invalid", "recipients": [{"name": "Asha", "email": "asha@example.com"}]},
        {"event_name": "Event", "issue_date": "2026-10-07", "recipients": []},
    ]

    for payload in test_cases:
        response = client.post("/jobs", json=payload)
        assert response.status_code == 422


def test_invalid_recipient_items_are_failed_without_stopping_valid_ones(client: TestClient):
    payload = {
        "event_name": "Bootcamp",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Asha Rao", "email": "invalid"},
            {"name": "John Doe", "email": "john@example.com"},
            {"name": "  ", "email": "valid@example.com"},
            {"name": "Asha Rao", "email": "asha@example.com"},
            {"name": "Asha Rao", "email": "ASHA@example.com"},
        ],
    }

    response = client.post("/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    response = client.get(f"/jobs/{job_id}")
    data = response.json()
    assert data["failed"] == 3
    assert data["pending"] == 0
    assert {item["recipient_email"] for item in data["items"] if item["status"] == "FAILED"} == {
        "invalid",
        "valid@example.com",
        "ASHA@example.com",
    }
    assert data["items"][0]["error_message"]


def test_duplicate_recipients_are_failed_only_after_first_occurrence(client: TestClient):
    payload = {
        "event_name": "Bootcamp",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "  Asha Rao  ", "email": " ASHA@example.com "},
            {"name": "asha rao", "email": "asha@example.com"},
            {"name": "John Doe", "email": "john@example.com"},
            {"name": "john doe", "email": "JOHN@example.com"},
        ],
    }

    response = client.post("/jobs", json=payload)
    assert response.status_code == 202
    data = client.get(f"/jobs/{response.json()['job_id']}").json()

    failed_emails = [item["recipient_email"].lower() for item in data["items"] if item["status"] == "FAILED"]
    assert failed_emails == ["asha@example.com", "john@example.com"]
    assert all(item["error_message"] == "Duplicate recipient in this request" for item in data["items"] if item["status"] == "FAILED")
