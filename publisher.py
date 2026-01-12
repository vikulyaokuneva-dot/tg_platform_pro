from app.core.telegram import send_post


def publish_job(name, job):
    channel = job.get('channel')
    if not channel:
        print('[SKIP] Channel None')
        return
    text = job['builder'](job)
    send_post(channel, text)
