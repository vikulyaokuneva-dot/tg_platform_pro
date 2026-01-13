from app.parsers.html_loader import load
from app.parsers.qudata import parse_qudata
from app.parsers.automation_ai import parse_automation_ai
from app.jobs.templates import build_article_post
from app.core.telegram import send_post
from app.core.state import is_duplicate, mark_sent


URLS = [
    ("https://qudata.com/ru/news-ai/tags/automation/", "qudata"),
    ("https://automation-ai.pro/", "automation"),
]


def run_all_jobs():
    for url, source in URLS:
        if is_duplicate(url):
            continue

        soup = load(url)

        if source == "qudata":
            content = parse_qudata(soup)
        elif source == "automation":
            content = parse_automation_ai(soup)
        else:
            continue

        payload = build_article_post(content)

        if payload:
            send_post(payload)
            mark_sent(url)
