# app/core/publisher.py

from app.core.telegram import send_post, send_photo

def publish_job(job_name: str, job: dict):
    ...
    result = builder(job)

    if isinstance(result, dict) and result.get("image"):
        send_photo(channel, result["image"], result["text"])
    else:
        send_post(channel, result)

from app.core.state import load_state, save_state
from app.core.scheduler import mark_published


def publish_job(job_name: str, job: dict):
    state = load_state()

    channel = job.get("channel")
    builder = job.get("builder")

    if not channel or not builder:
        return

    text = builder(job)
    if not text:
        return

    # 📌 НАВИГАЦИЯ (один раз, без pin API)
    if job.get("pin"):
        key = f"navigation_sent::{channel}"
        if state.get(key):
            return

        send_post(channel, text)
        state[key] = True
        save_state(state)
        return

    # 📨 ОБЫЧНЫЙ ПОСТ
    send_post(channel, text)
    mark_published(channel)
