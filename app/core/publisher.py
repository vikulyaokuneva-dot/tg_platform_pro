# app/core/publisher.py

from app.telegram.client import send_message


def publish_job(job_name: str, job: dict):
    builder = job["builder"]
    channel = job.get("channel")

    text = builder(job)

    if not text or not channel:
        return

    message_id = send_message(channel, text)

    if job.get("pin"):
        send_message(channel, text, pin=True)
