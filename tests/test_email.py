from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import email as email_service


def _email_settings() -> Settings:
    return Settings(
        _env_file=None,
        email_enabled=True,
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="app-password",
        smtp_from_email="sender@example.com",
        smtp_from_name="Certificate Team",
    )


class RecordingSMTP:
    instances: list["RecordingSMTP"] = []

    def __init__(self, host, port, timeout, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.kwargs = kwargs
        self.starttls_context = None
        self.login_args = None
        self.envelope = None
        self.message = None
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def starttls(self, context):
        self.starttls_context = context

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message, *, from_addr, to_addrs):
        self.message = message
        self.envelope = (from_addr, to_addrs)
        return {}


def test_send_certificate_email_builds_one_private_pdf_message(monkeypatch):
    RecordingSMTP.instances.clear()
    monkeypatch.setattr(email_service.smtplib, "SMTP", RecordingSMTP)

    email_service.send_certificate_email(
        recipient_name="Asha Rao",
        recipient_email="asha@example.com",
        event_name="Python Bootcamp 2026",
        pdf_bytes=b"%PDF-certificate",
        attachment_filename="certificate-item.pdf",
        message_id="<certificate-item@localhost>",
        settings=_email_settings(),
    )

    assert len(RecordingSMTP.instances) == 1
    smtp = RecordingSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.test", 587, 30.0)
    assert smtp.starttls_context is not None
    assert smtp.login_args == ("sender@example.com", "app-password")
    assert smtp.envelope == ("sender@example.com", ["asha@example.com"])
    message = smtp.message
    assert message is not None
    assert message["To"] == "asha@example.com"
    assert message["From"] == "Certificate Team <sender@example.com>"
    assert message["Message-ID"] == "<certificate-item@localhost>"
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "certificate-item.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-certificate"


def test_send_certificate_email_uses_implicit_ssl_and_one_envelope_recipient(monkeypatch):
    RecordingSMTP.instances.clear()
    settings = _email_settings()
    settings.smtp_use_tls = False
    settings.smtp_use_ssl = True
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", RecordingSMTP)

    email_service.send_certificate_email(
        recipient_name="Asha Rao",
        recipient_email="asha@example.com",
        event_name="Python Bootcamp 2026",
        pdf_bytes=b"private-pdf-bytes",
        attachment_filename="certificate.pdf",
        message_id="<certificate@localhost>",
        settings=settings,
    )

    smtp = RecordingSMTP.instances[0]
    assert smtp.kwargs["context"] is not None
    assert smtp.starttls_context is None
    assert smtp.envelope == ("sender@example.com", ["asha@example.com"])
    attachment = next(smtp.message.iter_attachments())
    assert attachment.get_payload(decode=True) == b"private-pdf-bytes"


@pytest.mark.parametrize(
    "recipient_email",
    [
        "asha@example.com,john@example.com",
        "asha@example.com\r\nBcc: victim@example.com",
        "Asha Rao <asha@example.com>",
    ],
)
def test_send_certificate_email_rejects_multi_address_and_header_injection(monkeypatch, recipient_email):
    monkeypatch.setattr(email_service.smtplib, "SMTP", RecordingSMTP)
    with pytest.raises(email_service.EmailDeliveryError, match="single valid mailbox"):
        email_service.send_certificate_email(
            recipient_name="Asha Rao",
            recipient_email=recipient_email,
            event_name="Bootcamp",
            pdf_bytes=b"pdf",
            attachment_filename="certificate.pdf",
            message_id="<certificate@localhost>",
            settings=_email_settings(),
        )


def test_send_certificate_email_rejects_invalid_sender_and_header_metadata(monkeypatch):
    settings = _email_settings()
    settings.smtp_from_email = "sender@example.com,other@example.com"
    monkeypatch.setattr(email_service.smtplib, "SMTP", RecordingSMTP)

    with pytest.raises(email_service.EmailDeliveryError, match="SMTP_FROM_EMAIL"):
        email_service.send_certificate_email(
            recipient_name="Asha Rao",
            recipient_email="asha@example.com",
            event_name="Bootcamp",
            pdf_bytes=b"pdf",
            attachment_filename="certificate.pdf",
            message_id="<certificate@localhost>",
            settings=settings,
        )

    settings = _email_settings()
    with pytest.raises(email_service.EmailDeliveryError, match="header metadata"):
        email_service.send_certificate_email(
            recipient_name="Asha Rao",
            recipient_email="asha@example.com",
            event_name="Bootcamp",
            pdf_bytes=b"pdf",
            attachment_filename="certificate\r\nX-Bad: yes.pdf",
            message_id="<certificate@localhost>",
            settings=settings,
        )


def test_email_configuration_requires_encryption_and_disabled_delivery_is_fixed():
    disabled = _email_settings()
    disabled.email_enabled = False
    with pytest.raises(email_service.EmailDeliveryError, match="disabled"):
        email_service.send_certificate_email(
            recipient_name="Asha Rao",
            recipient_email="asha@example.com",
            event_name="Bootcamp",
            pdf_bytes=b"pdf",
            attachment_filename="certificate.pdf",
            message_id="<certificate@localhost>",
            settings=disabled,
        )

    unencrypted = _email_settings()
    unencrypted.smtp_use_tls = False
    unencrypted.smtp_use_ssl = False
    assert email_service.email_configuration_error(unencrypted) == (
        "SMTP delivery requires STARTTLS or SSL encryption"
    )


def test_email_delivery_is_recipient_specific_and_failures_keep_pdfs(client: TestClient, monkeypatch):
    sent: list[dict[str, object]] = []
    settings = _email_settings()

    def fake_send_certificate_email(**kwargs):
        sent.append(kwargs)
        if kwargs["recipient_email"] == "john@example.com":
            raise RuntimeError("mailbox rejected message")

    monkeypatch.setattr("app.services.processor.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.processor.send_certificate_email", fake_send_certificate_email)

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
    assert response.status_code == 202

    job_id = response.json()["job_id"]
    data = client.get(f"/jobs/{job_id}").json()
    assert data["status"] == "COMPLETED_WITH_ERRORS"
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert data["email_sent"] == 1
    assert data["email_failed"] == 1
    assert [entry["recipient_email"] for entry in sent] == ["asha@example.com", "john@example.com"]
    assert all(entry["pdf_bytes"].startswith(b"%PDF") for entry in sent)
    assert [item["email_status"] for item in data["items"]] == ["SENT", "FAILED"]

    for item in data["items"]:
        download = client.get(f"/jobs/{job_id}/certificates/{item['id']}")
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")
