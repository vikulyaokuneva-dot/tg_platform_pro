# app/core/job_runner.py

from app.jobs.registry import JOBS
from app.core.scheduler import should_run_now, pick_random_job
from app.core.publisher import publish_job


def run_all_jobs():
    # 1️⃣ Навигация — всегда при старте
    for job_name, job in JOBS.items():
        if job.get("pin"):
            publish_job(job_name, job)

    # 2️⃣ Контент — только по расписанию
    if not should_run_now():
        return

    job = pick_random_job(JOBS)
    publish_job("scheduled_post", job)
