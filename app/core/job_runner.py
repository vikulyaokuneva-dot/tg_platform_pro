from app.core.telegram import send_post
from app.jobs.registry import JOBS

def run_all_jobs():
    for name, job in JOBS.items():
        text = job['builder'](job)
        send_post(job['channel'], text)
        print(f"[JOB] {name} posted")
