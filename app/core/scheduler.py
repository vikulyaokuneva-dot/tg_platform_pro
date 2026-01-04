# app/core/scheduler.py

import random
from datetime import datetime

POST_HOURS = [9, 14, 20]


def should_run_now() -> bool:
    now = datetime.now()
    return now.hour in POST_HOURS and now.minute < 5


def pick_random_job(jobs: dict) -> dict:
    """
    Выбирает случайный контентный job с учётом весов
    """
    weighted_jobs = []

    for job in jobs.values():
        if job.get("source") and not job.get("pin"):
            weight = job.get("weight", 1)
            weighted_jobs.extend([job] * weight)

    if not weighted_jobs:
        return None

    return random.choice(weighted_jobs)
