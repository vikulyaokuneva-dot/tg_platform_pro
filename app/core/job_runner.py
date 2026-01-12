from app.parsers.html_parser import load_html
from app.extractors.article import extract_article
from app.core.state import is_duplicate, mark_sent
from app.core.telegram import send_post

URLS = [
    "https://qudata.com/ru/news-ai/tags/automation/",
    "https://automation-ai.pro/"
]

for url in URLS:
    if is_duplicate(url):
        continue
    soup = load_html(url)
    content = extract_article(soup)  # {title, text, image}
    send_post(content)
    mark_sent(url)

def run_all_jobs():
    for url in URLS:
        soup = load_html(url)
        content = extract_article(soup)

        job = {
            "name": "article",
            "builder": build_article_post,
            "content": content,
        }

        publish_job("article", job)
