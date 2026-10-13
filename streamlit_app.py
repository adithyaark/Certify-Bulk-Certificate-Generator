from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

import streamlit as st
from sqlalchemy import select

from app.db import SessionLocal, create_db
from app.models import Job, JobStatus
from app.schemas import JobCreateRequest, RecipientInput
from app.services.job_service import (
    create_job,
    get_certificate,
    get_job,
    get_job_certificate_zip,
)
from app.services.processor import process_job


st.set_page_config(
    page_title="Certify · Bulk Certificate Generator",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


STATUS_LABELS = {
    JobStatus.PENDING: "Queued",
    JobStatus.PROCESSING: "Generating",
    JobStatus.COMPLETED: "Complete",
    JobStatus.COMPLETED_WITH_ERRORS: "Complete with errors",
    JobStatus.FAILED: "Failed",
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

        :root {
            --ink: #19242f;
            --muted: #6e7b87;
            --line: #e5e9ed;
            --paper: #ffffff;
            --canvas: #f5f7f9;
            --blue: #2563eb;
            --blue-dark: #1d4ed8;
            --mint: #dff7ed;
            --mint-ink: #147a59;
            --amber: #fff1d8;
            --amber-ink: #a86600;
        }

        html, body, .stApp {
            overflow-x: hidden;
        }

        .stApp {
            background: var(--canvas);
            color: var(--ink);
            font-family: 'Manrope', sans-serif;
            min-height: 100vh;
        }

        .block-container {
            width: 100% !important;
            max-width: none !important;
            padding: 2.2rem 3.5rem 4rem !important;
        }

        [data-testid="stSidebar"] {
            background: #111a23;
            border-right: 0;
            width: 19rem !important;
        }

        [data-testid="stSidebar"] * {
            color: #dce6ee;
        }

        [data-testid="stSidebar"] .stCaption {
            color: #91a2b1 !important;
        }

        [data-testid="stSidebar"] hr {
            border-color: #293743;
        }

        h1, h2, h3, h4, p {
            font-family: 'Manrope', sans-serif;
        }

        h1 {
            letter-spacing: -0.05em;
            line-height: 1.05;
        }

        h2, h3 {
            letter-spacing: -0.03em;
        }

        .brand-mark {
            align-items: center;
            display: flex;
            gap: 0.65rem;
            margin: 0.4rem 0 2.6rem;
        }

        .brand-symbol {
            align-items: center;
            background: #2e7cf6;
            border-radius: 11px;
            color: white;
            display: flex;
            font-size: 1.1rem;
            font-weight: 800;
            height: 34px;
            justify-content: center;
            width: 34px;
        }

        .brand-name {
            color: #f7fbff;
            font-size: 1.05rem;
            font-weight: 800;
            letter-spacing: -0.03em;
        }

        .eyebrow {
            color: var(--blue);
            font-family: 'DM Mono', monospace;
            font-size: 0.72rem;
            font-weight: 500;
            letter-spacing: 0.08em;
            margin-bottom: 0.55rem;
            text-transform: uppercase;
        }

        .hero-copy {
            color: var(--muted);
            font-size: 1.03rem;
            line-height: 1.65;
            max-width: 690px;
        }

        .hero-rule {
            background: linear-gradient(90deg, var(--blue), #8db7ff 54%, transparent);
            height: 3px;
            margin: 1.4rem 0 2rem;
            max-width: 180px;
        }

        .surface {
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 12px 35px rgba(26, 42, 58, 0.045);
            padding: 1.4rem 1.5rem;
        }

        .surface-title {
            color: var(--ink);
            font-size: 1rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }

        .surface-subtitle {
            color: var(--muted);
            font-size: 0.82rem;
            line-height: 1.55;
            margin-bottom: 1.15rem;
        }

        .step-number {
            align-items: center;
            background: #eaf1ff;
            border-radius: 50%;
            color: var(--blue);
            display: inline-flex;
            font-family: 'DM Mono', monospace;
            font-size: 0.7rem;
            font-weight: 500;
            height: 25px;
            justify-content: center;
            margin-right: 0.55rem;
            vertical-align: 1px;
            width: 25px;
        }

        .metric-card {
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 14px;
            min-height: 100px;
            padding: 1rem 1.1rem;
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }

        .metric-value {
            color: var(--ink);
            font-size: 1.55rem;
            font-weight: 800;
            letter-spacing: -0.05em;
            margin-top: 0.35rem;
        }

        .metric-note {
            color: var(--muted);
            font-size: 0.74rem;
            margin-top: 0.1rem;
        }

        .preview-card {
            background: #f9fafb;
            border: 1px solid #e3e8ed;
            border-radius: 12px;
            margin-top: 1.25rem;
            padding: 0.75rem;
        }

        .certificate-preview {
            background: #fff;
            border: 2px solid #5c8fb4;
            box-shadow: 0 8px 22px rgba(30, 51, 69, 0.08);
            min-height: 240px;
            padding: 2.2rem 1.25rem 1.2rem;
            position: relative;
            text-align: center;
        }

        .certificate-preview:before {
            border: 1px solid #b5cadb;
            content: '';
            inset: 7px;
            pointer-events: none;
            position: absolute;
        }

        .certificate-kicker {
            color: #3b7197;
            font-family: 'DM Mono', monospace;
            font-size: 0.52rem;
            letter-spacing: 0.13em;
            position: relative;
            text-transform: uppercase;
        }

        .certificate-heading {
            color: #203a4d;
            font-size: 1.05rem;
            font-weight: 800;
            margin: 1rem 0 1.3rem;
            position: relative;
        }

        .certificate-name {
            color: #172b3a;
            font-family: Georgia, serif;
            font-size: 1.55rem;
            font-weight: 700;
            line-height: 1.1;
            position: relative;
        }

        .certificate-event {
            color: #527084;
            font-size: 0.7rem;
            margin-top: 0.8rem;
            position: relative;
        }

        .certificate-date {
            color: #526c7c;
            font-size: 0.59rem;
            margin-top: 2rem;
            position: relative;
        }

        .status-pill {
            border-radius: 999px;
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 0.35rem 0.65rem;
        }

        .status-success {
            background: var(--mint);
            color: var(--mint-ink);
        }

        .status-warn {
            background: var(--amber);
            color: var(--amber-ink);
        }

        .status-neutral {
            background: #eaf1ff;
            color: #2d5fa9;
        }

        .status-error {
            background: #ffe5e5;
            color: #b83a3a;
        }

        .mono {
            font-family: 'DM Mono', monospace;
        }

        .sidebar-step {
            display: flex;
            gap: 0.7rem;
            margin: 1rem 0;
        }

        .sidebar-step-index {
            align-items: center;
            background: #263847;
            border-radius: 50%;
            color: #83b3ff;
            display: flex;
            flex: 0 0 24px;
            font-family: 'DM Mono', monospace;
            font-size: 0.65rem;
            height: 24px;
            justify-content: center;
        }

        .sidebar-step-text {
            color: #c6d3de;
            font-size: 0.78rem;
            line-height: 1.45;
        }

        div[data-testid="stFileUploader"] section {
            background: #f8fafc;
            border: 1px dashed #b8c8d7;
            border-radius: 12px;
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 9px;
            font-family: 'Manrope', sans-serif;
            font-weight: 700;
            min-height: 2.65rem;
        }

        .stButton > button[kind="primary"] {
            background: var(--blue);
            border: 1px solid var(--blue);
        }

        .stButton > button[kind="primary"]:hover {
            background: var(--blue-dark);
            border-color: var(--blue-dark);
        }

        [data-testid="stMetricValue"] {
            font-family: 'Manrope', sans-serif;
        }

        .footer-note {
            color: #84909a;
            font-size: 0.74rem;
            line-height: 1.6;
            margin-top: 2.5rem;
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _initialize_state() -> None:
    create_db()
    if "recipient_rows" not in st.session_state:
        st.session_state.recipient_rows = [
            {"name": "Asha Rao", "email": "asha@example.com"},
            {"name": "John Doe", "email": "john@example.com"},
        ]
    if "active_job_id" not in st.session_state:
        st.session_state.active_job_id = None
    if "upload_signature" not in st.session_state:
        st.session_state.upload_signature = None


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN without importing pandas.
            return ""
    except Exception:
        pass
    return str(value).strip()


def _parse_csv(uploaded_file: Any) -> tuple[list[dict[str, str]], str | None]:
    try:
        raw = uploaded_file.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw))
        headers = {(_safe_text(header)).lower(): header for header in (reader.fieldnames or [])}
        name_header = next((headers[key] for key in ("name", "recipient_name", "full_name") if key in headers), None)
        email_header = next((headers[key] for key in ("email", "recipient_email", "email_address") if key in headers), None)
        if not name_header or not email_header:
            return [], "CSV must include name and email columns."

        rows = []
        for row in reader:
            name = _safe_text(row.get(name_header))
            email = _safe_text(row.get(email_header))
            if name or email:
                rows.append({"name": name, "email": email})
        if not rows:
            return [], "The CSV does not contain any recipient rows."
        return rows, None
    except UnicodeDecodeError:
        return [], "This file is not UTF-8 encoded. Please export the CSV as UTF-8."
    except csv.Error as exc:
        return [], f"Could not read the CSV: {exc}"


def _rows_from_editor(value: Any) -> list[dict[str, str]]:
    if hasattr(value, "to_dict"):
        value = value.to_dict(orient="records")
    if isinstance(value, dict):
        value = [value]
    rows = []
    for row in value or []:
        if not isinstance(row, dict):
            continue
        name = _safe_text(row.get("name"))
        email = _safe_text(row.get("email"))
        if name or email:
            rows.append({"name": name, "email": email})
    return rows


def _job_snapshot(job_id: str):
    with SessionLocal() as db:
        return get_job(db, job_id, offset=0, limit=200)


def _status_class(status_value: str) -> str:
    if status_value in {JobStatus.COMPLETED, "SUCCESS"}:
        return "status-success"
    if status_value == JobStatus.COMPLETED_WITH_ERRORS:
        return "status-warn"
    if status_value in {JobStatus.FAILED, "FAILED"}:
        return "status-error"
    return "status-neutral"


def _status_pill(status_value: str) -> str:
    label = STATUS_LABELS.get(status_value, status_value.title().replace("_", " "))
    return f'<span class="status-pill {_status_class(status_value)}">{label}</span>'


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="brand-mark"><span class="brand-symbol">✦</span><span class="brand-name">certify</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown("### A better handoff")
        st.caption("Generate consistent, print-ready certificates from a simple recipient list.")
        st.divider()
        st.markdown("**How it works**")
        steps = [
            ("01", "Add your event details"),
            ("02", "Import or edit recipients"),
            ("03", "Download every certificate"),
        ]
        for index, text in steps:
            st.markdown(
                f'<div class="sidebar-step"><span class="sidebar-step-index">{index}</span><span class="sidebar-step-text">{text}</span></div>',
                unsafe_allow_html=True,
            )
        st.divider()
        st.caption("Built for fast demos and real operations")
        st.markdown(
            '<div class="mono" style="color:#83b3ff;font-size:.7rem">PDF · ZIP · CSV INPUT</div>',
            unsafe_allow_html=True,
        )


def _render_preview(event_name: str, issue_date: date, first_name: str) -> None:
    display_name = first_name or "Recipient name"
    display_event = event_name or "Your event or program"
    formatted_date = issue_date.strftime("%B %d, %Y")
    st.markdown('<div class="preview-card">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="certificate-preview">
            <div class="certificate-kicker">Certificate of participation</div>
            <div class="certificate-heading">This certificate is proudly presented to</div>
            <div class="certificate-name">{display_name}</div>
            <div class="certificate-event">For completing · {display_event}</div>
            <div class="certificate-date">Issued on {formatted_date}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Live preview · the generated PDF uses the same layout")


def _render_active_job(job_id: str) -> None:
    try:
        snapshot = _job_snapshot(job_id)
    except Exception as exc:
        st.error(f"Could not load this generation job: {exc}")
        return

    st.markdown("### Latest generation")
    header_left, header_right = st.columns([3, 1])
    with header_left:
        st.markdown(f"**{snapshot.event_name}** · {snapshot.created_at.strftime('%b %d, %Y %H:%M')}")
        st.caption(f"Job ID · `{snapshot.job_id}`")
    with header_right:
        st.markdown(_status_pill(snapshot.status), unsafe_allow_html=True)

    metric_columns = st.columns(4)
    metric_data = [
        ("Total", snapshot.total, "recipients"),
        ("Ready", snapshot.succeeded, "PDFs generated"),
        ("Needs review", snapshot.failed, "items with errors"),
        ("Pending", snapshot.pending, "still in queue"),
    ]
    for column, (label, value, note) in zip(metric_columns, metric_data):
        with column:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
                unsafe_allow_html=True,
            )

    if snapshot.pending:
        st.info("This job still has pending items. Refresh the page to check for updates.")

    if snapshot.succeeded:
        with SessionLocal() as db:
            try:
                zip_bytes, zip_name = get_job_certificate_zip(db, job_id)
            except Exception:
                zip_bytes, zip_name = None, None
        if zip_bytes:
            st.download_button(
                "Download all certificates · ZIP",
                data=zip_bytes,
                file_name=zip_name,
                mime="application/zip",
                type="primary",
                use_container_width=True,
                key=f"zip-{job_id}",
            )

    if snapshot.items:
        st.markdown("#### Recipient results")
        for item in snapshot.items:
            row_left, row_mid, row_right = st.columns([2.2, 2.2, 1])
            with row_left:
                st.markdown(f"**{item.recipient_name or 'Unnamed recipient'}**")
                st.caption(item.recipient_email or "No email provided")
            with row_mid:
                if item.error_message:
                    st.caption(item.error_message)
                else:
                    st.markdown(_status_pill(item.status), unsafe_allow_html=True)
            with row_right:
                if item.status == "SUCCESS":
                    with SessionLocal() as db:
                        try:
                            pdf_bytes, filename = get_certificate(db, job_id, item.id)
                        except Exception:
                            pdf_bytes, filename = None, None
                    if pdf_bytes:
                        st.download_button(
                            "PDF",
                            data=pdf_bytes,
                            file_name=filename,
                            mime="application/pdf",
                            key=f"pdf-{job_id}-{item.id}",
                        )
        st.divider()


def _render_recent_jobs(active_job_id: str | None) -> None:
    with SessionLocal() as db:
        jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(6)).all()
    jobs = [job for job in jobs if job.id != active_job_id]
    if not jobs:
        return
    with st.expander("Recent generation history", expanded=False):
        for job in jobs:
            left, middle, right = st.columns([3, 2, 1])
            with left:
                st.markdown(f"**{job.event_name}**")
                st.caption(job.created_at.strftime("%b %d, %Y at %H:%M"))
            with middle:
                st.markdown(_status_pill(job.status), unsafe_allow_html=True)
            with right:
                if st.button("View", key=f"view-{job.id}"):
                    st.session_state.active_job_id = job.id
                    st.rerun()


def main() -> None:
    _initialize_state()
    _inject_styles()
    _render_sidebar()

    st.title("Make every achievement feel official.")
    st.markdown(
        '<div class="hero-copy">Create polished participation certificates for a whole cohort in one pass. Add your event, paste a list, and leave with a ready-to-share ZIP.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="hero-rule"></div>', unsafe_allow_html=True)

    workspace, preview = st.columns([1.45, 0.8], gap="large")
    with workspace:
        st.markdown('<div class="surface-title"><span class="step-number">01</span>Event details</div>', unsafe_allow_html=True)
        st.markdown('<div class="surface-subtitle">Set the details that will appear on every certificate in this batch.</div>', unsafe_allow_html=True)
        event_name = st.text_input(
            "Event or program name",
            value=st.session_state.get("event_name", "Python Bootcamp 2026"),
            placeholder="e.g. Python Bootcamp 2026",
            max_chars=255,
        )
        issue_date = st.date_input("Issue date", value=st.session_state.get("issue_date", date.today()))

        st.markdown('<div style="height:.55rem"></div>', unsafe_allow_html=True)
        st.markdown('<div class="surface-title"><span class="step-number">02</span>Recipient list</div>', unsafe_allow_html=True)
        st.markdown('<div class="surface-subtitle">Upload a CSV or edit the table directly. Only <span class="mono">name</span> and <span class="mono">email</span> columns are needed.</div>', unsafe_allow_html=True)

        template = "name,email\nAsha Rao,asha@example.com\nJohn Doe,john@example.com\n"
        template_left, upload_right = st.columns([1, 1.6])
        with template_left:
            st.download_button(
                "Download CSV template",
                data=template,
                file_name="certificate-recipients-template.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with upload_right:
            uploaded_file = st.file_uploader("Import recipient CSV", type=["csv"], label_visibility="collapsed")

        if uploaded_file:
            signature = (uploaded_file.name, uploaded_file.size)
            if signature != st.session_state.upload_signature:
                parsed_rows, error = _parse_csv(uploaded_file)
                if error:
                    st.error(error)
                else:
                    st.session_state.recipient_rows = parsed_rows
                    st.session_state.upload_signature = signature
                    st.success(f"Loaded {len(parsed_rows)} recipient rows from {uploaded_file.name}.")

        edited_rows = st.data_editor(
            st.session_state.recipient_rows,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Recipient name", required=False, max_chars=100),
                "email": st.column_config.TextColumn("Email address", required=False),
            },
            key="recipient_editor",
        )
        current_rows = _rows_from_editor(edited_rows)
        st.session_state.recipient_rows = current_rows
        st.caption(f"{len(current_rows)} recipient row{'s' if len(current_rows) != 1 else ''} ready to process · blank rows are ignored")

        if st.button("Generate certificates", type="primary", use_container_width=True):
            if not event_name.strip():
                st.error("Add an event or program name before generating.")
            elif not current_rows:
                st.error("Add at least one recipient or upload a CSV.")
            else:
                try:
                    request = JobCreateRequest(
                        event_name=event_name,
                        issue_date=issue_date,
                        recipients=[RecipientInput(**row) for row in current_rows],
                    )
                    with st.spinner("Generating your certificates…"):
                        with SessionLocal() as db:
                            created = create_job(db, request)
                        process_job(created.job_id)
                    st.session_state.event_name = event_name
                    st.session_state.issue_date = issue_date
                    st.session_state.active_job_id = created.job_id
                    st.success(f"Generation finished for {created.total} recipients.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Generation could not be started: {exc}")

    with preview:
        st.markdown('<div class="surface-title">Your certificate</div>', unsafe_allow_html=True)
        st.markdown('<div class="surface-subtitle">A quick look at the fixed, print-ready A4 landscape layout.</div>', unsafe_allow_html=True)
        first_name = _safe_text((st.session_state.recipient_rows or [{"name": ""}])[0].get("name"))
        _render_preview(event_name, issue_date, first_name)
        st.markdown(
            '<div style="margin-top:1.5rem;color:#6e7b87;font-size:.8rem;line-height:1.65"><strong style="color:#19242f">Designed for the finish line.</strong><br>Each recipient gets an individual PDF. Successful PDFs are bundled into one download-ready ZIP.</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.active_job_id:
        st.divider()
        _render_active_job(st.session_state.active_job_id)
        _render_recent_jobs(st.session_state.active_job_id)
    else:
        _render_recent_jobs(None)

    st.markdown(
        '<div class="footer-note">Certify · FastAPI-powered generation · Per-recipient validation · PDF and ZIP export</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
