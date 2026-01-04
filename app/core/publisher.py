# app/core/publisher.py

from app.telegram.client import send_message
from app.core.state import load_state, save_state


def publish_job(job_name: str, job: dict):
    state = load_state()

    builder = job["builder"]
    channel = job.get("channel")

    text = builder(job)

    if not text or not channel:
        return

    # 🔒 PIN-LOGIC
    if job.get("pin"):
        pinned_key = f"pinned::{channel}"

        if state.get(pinned_key):
            return

        send_message(channel, text, pin=True)
        state[pinned_key] = True
        save_state(state)
        return

    # 📨 Обычная публикация
    send_message(channel, text)
