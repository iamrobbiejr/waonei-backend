import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "waonei_worker",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

# Core Celery config
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Harare",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Result backend settings
    result_expires=3600,  # 1 hour
    result_persistent=True,

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Rate limiting (optional)
    task_default_rate_limit='10/m',  # 10 tasks per minute
)

# 👇 Windows-safe worker settings (IMPORTANT)
celery_app.conf.worker_pool = "solo"
celery_app.conf.worker_concurrency = 1

# Optional: Task routes for multiple queues
celery_app.conf.task_routes = {
    'app.tasks.process_violation': {'queue': 'ai_processing'},
    'app.tasks.batch_process_violations': {'queue': 'batch_processing'},
    'app.tasks.reprocess_failed_violations': {'queue': 'maintenance'},
}

# Optional: Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'reprocess-failed-every-hour': {
        'task': 'app.tasks.reprocess_failed_violations',
        'schedule': 3600.0,  # Run every hour
    },
    'cleanup-old-pending-every-day': {
        'task': 'app.tasks.cleanup_old_pending',
        'schedule': 86400.0,  # Run daily
    },
}

# 👇 THIS IS THE IMPORTANT LINE - Import tasks to register them
import app.tasks