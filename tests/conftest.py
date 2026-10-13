from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as app_db
from app.main import app


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[None, None, None]:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    app_db.engine = engine
    app_db.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    app_db.create_db()
    yield

    app_db.engine.dispose()


@pytest.fixture
def client(temp_db: None) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
