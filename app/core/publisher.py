from app.core.telegram import send_post
from app.core.state import load_state, save_state
from app.core.scheduler import mark_published


def publish_job(job_name: str, job: dict):
    state = load_state()
    channel = job.get("channel")
    text = job["builder"](job)

    if job.get("pin"):
        key = f"pinned::{channel}"
        if state.get(key):
            return
        send_post(channel, text)
        state[key] = True
        save_state(state)
        return

    send_post(channel, text)
    mark_published(channel)
