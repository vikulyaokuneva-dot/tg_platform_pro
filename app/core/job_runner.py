from app.core.publisher import publish_job
from app.jobs.templates import build_simple_post


def run_all_jobs():
    job = {
        "name": "content",
        "builder": build_simple_post,
        "content": {
            "title": "Платформа запущена",
            "text": "Telegram Content Platform работает корректно 🚀"
        }
    }
    publish_job('content', job)
