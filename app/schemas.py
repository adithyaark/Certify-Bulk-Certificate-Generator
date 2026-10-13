from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class RecipientInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    email: str


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str
    issue_date: date
    recipients: list[RecipientInput]

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event_name is required")
        return value.strip()

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, value: list[RecipientInput]) -> list[RecipientInput]:
        if not value:
            raise ValueError("recipients cannot be empty")
        return value


class JobItemResponse(BaseModel):
    id: str
    recipient_name: str
    recipient_email: str
    status: str
    error_message: str | None = None
    download_url: str | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    total: int
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    event_name: str
    status: str
    total: int
    succeeded: int
    failed: int
    pending: int
    created_at: datetime
    completed_at: datetime | None
    items: list[JobItemResponse]


class CertificateResponse(BaseModel):
    item_id: str
    job_id: str
    status: str
    file_path: str | None = None
