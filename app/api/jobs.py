from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import JobCreateRequest, JobCreateResponse
from app.services.job_service import create_job, get_certificate, get_job, get_job_certificate_zip
from app.services.processor import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_generation_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> JobCreateResponse:
    job = create_job(db, request)
    background_tasks.add_task(process_job, job.job_id)
    return job


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    return get_job(db, job_id, offset=offset, limit=limit, status_filter=status_filter)


@router.get("/{job_id}/certificates/{item_id}")
def download_certificate(
    job_id: str,
    item_id: str,
    db: Session = Depends(get_db),
) -> Response:
    content, filename = get_certificate(db, job_id, item_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/download")
def download_job_certificates(
    job_id: str,
    db: Session = Depends(get_db),
) -> Response:
    content, filename = get_job_certificate_zip(db, job_id)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
