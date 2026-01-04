# app/core/job_runner.py

from app.jobs.registry import JOBS
from app.core.publisher import publish_job
from app.core.scheduler import should_run_now, pick_random_job


def run_all_jobs():
    # 1️⃣ Навигация (однократно)
    for job_name, job in JOBS.items():
        if job.get("pin"):
            publish_job(job_name, job)

    # 2️⃣ Контент по расписанию
    if not should_run_now():
        return

    job = pick_random_job(JOBS)
    if job:
        publish_job("scheduled_content", job)
