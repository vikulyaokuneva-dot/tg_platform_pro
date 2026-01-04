# app/core/scheduler.py

import random
from datetime import datetime

POST_TIMES = [9, 14, 20]  # часы публикаций


def should_run_now() -> bool:
    """
    Проверяет, нужно ли публиковать пост сейчас
    """
    now = datetime.now()
    return now.hour in POST_TIMES and now.minute < 5


def pick_random_job(jobs: dict) -> dict:
    """
    Выбирает случайный job, который является контентным
    """
    content_jobs = [
        job for job in jobs.values()
        if job.get("source") and not job.get("pin")
    ]
    return random.choice(content_jobs)
