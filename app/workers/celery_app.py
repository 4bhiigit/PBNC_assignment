from celery import Celery
from kombu import Queue

from app.config import get_settings

settings = get_settings()

celery = Celery(
    "doc_intel_worker",
    broker=settings.celery_broker_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_default_queue="ingest",
    task_queues=(
        Queue("ingest", routing_key="ingest.#"),
        Queue("pages", routing_key="pages.#"),
        Queue("finalize", routing_key="finalize.#"),
    ),
    task_routes={
        "app.workers.tasks.process_document": {"queue": "ingest"},
        "app.workers.tasks.process_page": {"queue": "pages"},
        "app.workers.tasks.finalize_document": {"queue": "finalize"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=settings.task_soft_time_limit,
    task_time_limit=settings.task_hard_time_limit,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
