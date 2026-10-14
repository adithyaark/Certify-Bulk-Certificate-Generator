from collections.abc import Generator
from pathlib import Path

from sqlalchemy import DateTime, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        database_path = settings.database_url.removeprefix("sqlite:///")
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db() -> None:
    from app.models import Base as ModelsBase

    ModelsBase.metadata.create_all(bind=engine)
    _add_missing_email_columns()


def _add_missing_email_columns() -> None:
    """Add delivery columns to databases created before email delivery existed."""
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("certificate_items")}
        string_type = String(32).compile(dialect=connection.dialect)
        text_type = Text().compile(dialect=connection.dialect)
        datetime_type = DateTime().compile(dialect=connection.dialect)
        additions = {
            # Existing certificates were created before delivery existed, so they
            # must not be sent retroactively when email delivery is enabled.
            "email_status": f"{string_type} NOT NULL DEFAULT 'SKIPPED'",
            "email_error_message": str(text_type),
            "email_sent_at": str(datetime_type),
        }
        added_email_status = False
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE certificate_items ADD COLUMN {name} {definition}"))
                added_email_status = added_email_status or name == "email_status"
        if added_email_status:
            connection.execute(
                text(
                    "UPDATE certificate_items SET email_status = 'SKIPPED' "
                    "WHERE status <> 'PENDING'"
                )
            )


# Keep direct service usage (including the Streamlit entry point and local scripts)
# usable before the FastAPI lifespan has run. The lifespan still calls create_db()
# on every application start, so this is idempotent.
create_db()
