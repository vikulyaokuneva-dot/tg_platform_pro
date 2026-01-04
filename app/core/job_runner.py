from app.jobs.registry import JOBS
from app.core.publisher import publish_job
from app.core.scheduler import can_publish, pick_job_with_rules
from app.core.state import load_state, save_state

def run_all_jobs():
    state = load_state()

    # pin navigation once
    for name, job in JOBS.items():
        if job.get("pin"):
            publish_job(name, job)

    # per-channel logic
    for name, job in JOBS.items():
        if not job.get("source"):
            continue

        channel = job["channel"]
        limit = job.get("posts_per_day", 3)

        if not can_publish(channel, limit):
            continue

        # wisdom every 10th post
        counter = state.get(f"counter::{channel}", 0) + 1
        state[f"counter::{channel}"] = counter
        save_state(state)

        if counter % 10 == 0 and job.get("wisdom_builder"):
            publish_job("wisdom", {
                "channel": channel,
                "builder": job["wisdom_builder"]
            })
        else:
            chosen = pick_job_with_rules(JOBS, channel)
            if chosen:
                publish_job("content", chosen)
