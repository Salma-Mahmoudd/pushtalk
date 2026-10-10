import asyncio
import uuid

from celery import Celery
from celery.signals import setup_logging

from pushtalk.core.config import get_settings
from pushtalk.core.logging import configure_logging

PROCESS_MESSAGE = "process_message"

settings = get_settings()

celery_app = Celery(
    "pushtalk", broker=str(settings.celery_broker_url), include=["pushtalk.worker.tasks"]
)
celery_app.conf.update(
    # A task is acknowledged only after it finished: a worker that dies mid-task loses nothing.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One task at a time per worker process, so a long task never holds others back.
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    task_routes={PROCESS_MESSAGE: {"queue": "audio"}},
    task_default_queue="audio",
    task_time_limit=180,
    task_soft_time_limit=150,
    broker_connection_retry_on_startup=True,
)


@setup_logging.connect
def _use_app_logging(**_: object) -> None:
    """Celery logs through the same JSON configuration as the API."""
    configure_logging(settings.log_level, settings.log_format)


async def enqueue_message_processing(message_id: uuid.UUID) -> None:
    """Called by the API after a message is stored; sending to the broker is blocking I/O."""
    await asyncio.to_thread(
        celery_app.send_task, PROCESS_MESSAGE, args=[str(message_id)], queue="audio"
    )
