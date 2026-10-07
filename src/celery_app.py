from celery import Celery

from src.config import settings

celery_app = Celery(
    "hardware",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
