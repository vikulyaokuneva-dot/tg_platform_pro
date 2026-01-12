from app.parsers.html_parser import load_html
from app.extractors.article import extract_article
from app.jobs.templates import build_article_post
from app.core.publisher import publish_job


URLS = [
    "https://example.com/article1",
    "https://example.com/article2",
]


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
