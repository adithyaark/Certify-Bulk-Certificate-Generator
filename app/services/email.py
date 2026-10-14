from __future__ import annotations

import re
import socket
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Settings, get_settings
from app.services.email_validation import contains_header_control, validate_single_mailbox


EMAIL_DISABLED_ERROR = "Email delivery is disabled"
AUTHENTICATION_ERROR = "SMTP authentication failed"
RECIPIENT_REFUSED_ERROR = "SMTP server refused the recipient"
NETWORK_ERROR = "Unable to connect to the SMTP server"
ENCRYPTION_ERROR = "SMTP encryption negotiation failed"
SMTP_ERROR = "SMTP delivery failed"
INVALID_METADATA_ERROR = "Email contains invalid header metadata"


class EmailDeliveryError(RuntimeError):
    """Raised when the SMTP server does not accept a certificate message."""

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


def safe_email_error_message(error: BaseException) -> str:
    """Map an email failure to a fixed message safe to persist and display."""
    if isinstance(error, EmailDeliveryError):
        return error.public_message
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return AUTHENTICATION_ERROR
    if isinstance(error, (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError)):
        return RECIPIENT_REFUSED_ERROR
    if isinstance(error, (ssl.SSLError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return NETWORK_ERROR
    if isinstance(error, (socket.timeout, TimeoutError, ConnectionError, OSError)):
        return NETWORK_ERROR
    return SMTP_ERROR


def email_configuration_error(settings: Settings | None = None) -> str | None:
    """Return a safe, user-facing configuration error without exposing credentials."""
    settings = settings or get_settings()
    if not settings.email_enabled:
        return None

    missing = []
    if not isinstance(settings.smtp_host, str) or not settings.smtp_host.strip():
        missing.append("SMTP_HOST")
    if not settings.smtp_username or not settings.smtp_username.strip():
        missing.append("SMTP_USERNAME")
    if not settings.smtp_password or not settings.smtp_password.get_secret_value():
        missing.append("SMTP_PASSWORD")
    if not settings.smtp_from_email or not settings.smtp_from_email.strip():
        missing.append("SMTP_FROM_EMAIL")
    if missing:
        return "Email delivery is enabled but missing: " + ", ".join(missing)
    if settings.smtp_use_tls and settings.smtp_use_ssl:
        return "SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled"
    if not settings.smtp_use_tls and not settings.smtp_use_ssl:
        return "SMTP delivery requires STARTTLS or SSL encryption"
    try:
        validate_single_mailbox(settings.smtp_from_email, field_name="SMTP_FROM_EMAIL")
    except ValueError:
        return "SMTP_FROM_EMAIL must be a single valid mailbox"
    if contains_header_control(settings.smtp_from_name):
        return "SMTP_FROM_NAME contains invalid header metadata"
    return None


def _safe_subject(event_name: str) -> str:
    cleaned = re.sub(r"[\r\n\x00-\x1f\x7f]", " ", event_name).strip()
    return f"Your certificate for {cleaned or 'the event'}"[:255]


def _validate_header_metadata(*values: str) -> None:
    if any(contains_header_control(value) for value in values):
        raise EmailDeliveryError(INVALID_METADATA_ERROR)


def send_certificate_email(
    *,
    recipient_name: str,
    recipient_email: str,
    event_name: str,
    pdf_bytes: bytes,
    attachment_filename: str,
    message_id: str,
    settings: Settings | None = None,
) -> None:
    """Send one certificate message to exactly one recipient via SMTP."""
    settings = settings or get_settings()
    if not settings.email_enabled:
        raise EmailDeliveryError(EMAIL_DISABLED_ERROR)
    configuration_error = email_configuration_error(settings)
    if configuration_error:
        raise EmailDeliveryError(configuration_error)

    try:
        sender_email = validate_single_mailbox(settings.smtp_from_email, field_name="SMTP_FROM_EMAIL")
        recipient_email = validate_single_mailbox(recipient_email, field_name="Recipient email")
    except ValueError as exc:
        raise EmailDeliveryError(str(exc)) from None
    _validate_header_metadata(message_id, attachment_filename)

    password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, sender_email))
    message["To"] = recipient_email
    message["Subject"] = _safe_subject(event_name)
    message["Message-ID"] = message_id
    message.set_content(
        f"Hello {recipient_name},\n\n"
        f"Your certificate for {event_name} is attached.\n\n"
        "Congratulations!\n"
    )
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_filename,
    )

    context = ssl.create_default_context()
    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
                context=context,
            ) as smtp:
                smtp.login(settings.smtp_username, password)
                refused = smtp.send_message(message, from_addr=sender_email, to_addrs=[recipient_email])
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as smtp:
                smtp.starttls(context=context)
                smtp.login(settings.smtp_username, password)
                refused = smtp.send_message(message, from_addr=sender_email, to_addrs=[recipient_email])
    except smtplib.SMTPAuthenticationError:
        raise EmailDeliveryError(AUTHENTICATION_ERROR) from None
    except smtplib.SMTPRecipientsRefused:
        raise EmailDeliveryError(RECIPIENT_REFUSED_ERROR) from None
    except (ssl.SSLError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
        raise EmailDeliveryError(NETWORK_ERROR) from None
    except (socket.timeout, TimeoutError, ConnectionError, OSError):
        raise EmailDeliveryError(NETWORK_ERROR) from None
    except smtplib.SMTPException:
        raise EmailDeliveryError(SMTP_ERROR) from None

    if refused:
        raise EmailDeliveryError(RECIPIENT_REFUSED_ERROR)
