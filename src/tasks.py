import asyncio
from uuid import UUID

from src.celery_app import celery_app
from src.database.session import engine
from src.services.ingestion import process_ingestion_job as _process_ingestion_job


async def _run_in_fresh_loop(job_id: UUID) -> None:
    try:
        await _process_ingestion_job(job_id)
    finally:
        # A sync Celery task owns a short-lived event loop. Release pooled async
        # connections before asyncio.run closes it so the next task can reconnect.
        await engine.dispose()


@celery_app.task(name="src.tasks.process_ingestion_job")
def process_ingestion_job(job_id: str) -> dict[str, str]:
    asyncio.run(_run_in_fresh_loop(UUID(job_id)))
    return {"job_id": job_id, "status": "finished"}
