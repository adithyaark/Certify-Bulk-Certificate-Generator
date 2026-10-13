# Bulk Certificate Generator

This project provides a FastAPI backend and a polished Streamlit workspace for creating bulk certificate generation jobs, processing recipients, and downloading generated PDFs or a ZIP archive. It uses SQLite by default, SQLAlchemy for persistence, and ReportLab for fixed-template PDF rendering.

## Setup

From the project root, create and activate a virtual environment with Python 3.10 or newer:

```powershell
py -3.10 -m venv .venv310
.\.venv310\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The defaults are configured in `.env.example`. Copy them to an environment file when you need custom values:

```powershell
Copy-Item .env.example .env
```

The available settings are:

- `DATABASE_URL`: SQLite database location, default `sqlite:///./storage/app.db`
- `STORAGE_DIR`: certificate output directory, default `./storage`
- `MAX_RECIPIENTS_PER_JOB`: maximum recipients per job, default `1000`

## Run the API

Start the development server from the project root:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Open the interactive documentation at `http://127.0.0.1:8001/docs`.

## Run the Streamlit workspace

The Streamlit app runs directly on the same application services, so a demo deployment does not need a separate API process:

```powershell
python -m streamlit run streamlit_app.py
```

Open `http://localhost:8501`. The workspace supports:

- event name and issue date configuration;
- CSV upload with `name` and `email` columns;
- an editable recipient table with add/remove rows;
- per-recipient validation with failure isolation;
- individual PDF downloads and a ZIP download for the whole batch; and
- recent generation history backed by the existing SQLite database.

The starter rows are demo data. Replace them or upload the CSV template before generating a real batch.

## Deploy for a portfolio demo

### Streamlit Community Cloud

1. Push this project to a public GitHub repository.
2. Create an app at [share.streamlit.io](https://share.streamlit.io/).
3. Select the repository and branch, then set the main file to `streamlit_app.py`.
4. Deploy. Streamlit Cloud installs `requirements.txt` automatically.

The included `.streamlit/config.toml` supplies the theme, and `runtime.txt` keeps the deployment on Python 3.11. For a hosted demo, SQLite and generated files are stored on the app's local filesystem; this is appropriate for a portfolio demo and can be replaced with PostgreSQL/object storage for production.

### Render or another process-based host

The included `Procfile` starts Streamlit on the host-provided port:

```text
web: streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=$PORT
```

Create a web service from the repository, use `pip install -r requirements.txt` as the build command, and use the Procfile as the start command. Set `DATABASE_URL`, `STORAGE_DIR`, and `MAX_RECIPIENTS_PER_JOB` as environment variables when using non-default settings.

## Run tests

```powershell
python -m pytest -q
```

The verified project result is **17 tests passed**.

## Submit a generation request

```powershell
curl.exe -X POST "http://127.0.0.1:8001/jobs" -H "Content-Type: application/json" -d '{
  "event_name": "Python Bootcamp 2026",
  "issue_date": "2026-10-07",
  "recipients": [
    {"name": "Asha Rao", "email": "asha@example.com"},
    {"name": "John Doe", "email": "john@example.com"}
  ]
}'
```

A typical response is:

```json
{
  "job_id": "<uuid>",
  "status": "PENDING",
  "total": 2,
  "status_url": "/jobs/<uuid>"
}
```

The request is validated at the request level before records are created. Individual recipient validation failures are stored as failed items without stopping valid recipients.

## Check job status

```powershell
curl.exe "http://127.0.0.1:8001/jobs/<job_id>"
```

A sample successful response is:

```json
{
  "job_id": "<uuid>",
  "event_name": "Python Bootcamp 2026",
  "status": "COMPLETED",
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "pending": 0,
  "created_at": "2026-10-07T10:00:00",
  "completed_at": "2026-10-07T10:00:02",
  "items": [
    {
      "id": "<uuid>",
      "recipient_name": "Asha Rao",
      "recipient_email": "asha@example.com",
      "status": "SUCCESS",
      "error_message": null,
      "download_url": "/jobs/<job_id>/certificates/<item_id>"
    }
  ]
}
```

Use `?status=FAILED` to show only failed items and adjust `limit` and `offset` for large jobs.

## Retrieve certificates

### Single certificate

```powershell
curl.exe -L "http://127.0.0.1:8001/jobs/<job_id>/certificates/<item_id>" -o certificate.pdf
```

The response has `Content-Type: application/pdf` and a `Content-Disposition` attachment filename.

### ZIP of all successful certificates

```powershell
curl.exe -L "http://127.0.0.1:8001/jobs/<job_id>/download" -o certificates.zip
```

The ZIP contains one PDF per successful recipient. Duplicate recipient names are de-duplicated using a numerical suffix.

## Design decisions

- **Background processing:** job creation returns immediately so the client is not blocked by PDF generation.
- **BackgroundTasks:** the project uses FastAPI's built-in task runner because it is simple, synchronous, and requires no additional infrastructure.
- **Validation strategy:** request-level validation rejects malformed jobs before database work, while recipient-level validation records each invalid item as `FAILED` without interrupting the rest of the job.
- **Failure isolation:** each item is rendered and saved independently. One PDF failure is stored as an error message while the remaining items continue.
- **Storage choice:** files are stored under `storage/{job_id}/{item_id}.pdf` using a path guard that prevents traversal outside the configured directory.
- **Status model:** job status is calculated from the item statuses and is one of `PENDING`, `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, or `FAILED`.

## Known limitations

- The current processor runs inside the FastAPI process using `BackgroundTasks`; it is suitable for development and small workloads.
- A larger deployment would use a task queue such as Celery with Redis and durable worker processes.
- SQLite is convenient for local use; PostgreSQL would be a better choice for concurrent workloads and larger datasets.
- PDF files are stored locally in the configured storage directory; object storage such as S3 would be preferable for scale and redundancy.
- The API does not implement authentication, rate limiting, or retry queues.

## Interview cheat sheet

- **Where are jobs created?** `app/services/job_service.py` contains the transaction and validation logic; `app/api/jobs.py` contains the route handler.
- **How do failures stay isolated?** The processor catches exceptions around each item, marks that item as `FAILED`, commits the change, and continues with the remaining items.
- **How is a request rejected?** Pydantic validates `event_name`, `issue_date`, and the non-empty recipient list before the service runs.
- **How are duplicate recipients handled?** The service normalizes the name and email, keeps the first occurrence, and marks later duplicates as `FAILED` with a clear error.
- **How does PDF rendering avoid crashes on long names?** `app/services/renderer.py` shrinks the name font until it fits the fixed page width.
- **How does storage prevent path traversal?** `app/services/storage.py` resolves the candidate path and confirms it remains inside the configured storage directory.
- **How are jobs recovered after a crash?** Startup checks for `PROCESSING` jobs in `app/main.py` and resets them to `PENDING` so pending certificates can be retried.
- **How is a certificate download authorized?** The service requires both the job ID and item ID to match, and it returns a `404` for an item belonging to another job.
- **Why is ZIP generation streaming-friendly?** It writes entries into an in-memory ZIP buffer and avoids loading every certificate into a list before creating the archive.
- **Where are database tables created?** `app/db.py` creates all tables automatically during application startup.
