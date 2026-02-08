"""
Celery application configuration for async task processing.
"""

from __future__ import annotations

from celery import Celery

from src.config.settings import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()

    app = Celery(
        "macro_sign_service",
        broker=settings.celery.broker_url,
        backend=settings.celery.result_backend,
    )

    app.conf.update(
        task_serializer=settings.celery.task_serializer,
        result_serializer=settings.celery.result_serializer,
        accept_content=settings.celery.accept_content,
        timezone=settings.celery.timezone,
        enable_utc=settings.celery.enable_utc,
        task_track_started=settings.celery.task_track_started,
        task_time_limit=settings.celery.task_time_limit,
        task_soft_time_limit=settings.celery.task_soft_time_limit,
        task_routes={
            "src.queue.tasks.sign_macro_task": {"queue": "signing"},
            "src.queue.tasks.verify_macro_task": {"queue": "verification"},
            "src.queue.tasks.send_webhook_task": {"queue": "webhooks"},
        },
        task_default_queue="default",
    )

    # Auto-discover tasks
    app.autodiscover_tasks(["src.queue"])

    return app


celery_app = create_celery_app()
