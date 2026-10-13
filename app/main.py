from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.jobs import router
from app.db import create_db, get_db
from app.services.processor import recover_processing_jobs


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db()
    db = next(get_db())
    try:
        recover_processing_jobs(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Bulk Certificate Generator",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
