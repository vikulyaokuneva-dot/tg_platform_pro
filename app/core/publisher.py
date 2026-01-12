from app.core.telegram import send_post


def publish_job(name, job):
    text = job["builder"](job)
    send_post(text)
