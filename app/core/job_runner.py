from app.core.telegram import send_post
from app.jobs.registry import JOBS

def run_all_jobs():
    for name, job in JOBS.items():
        text = job['builder'](job)
        msg_id = send_post(job['channel'], text)
        if msg_id:
            print(f"[JOB] {name} posted")
        else:
            print(f"[JOB] {name} skipped")
