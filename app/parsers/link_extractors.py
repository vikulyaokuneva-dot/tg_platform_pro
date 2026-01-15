from app.parsers.html_loader import load
from app.parsers.qudata import parse_qudata
from app.parsers.automation_ai import parse_automation_ai
from app.parsers.link_extractors import (
    extract_qudata_links,
    extract_automation_ai_links,
)
from app.core.publisher import publish


SOURCES = {
    "qudata": "https://qudata.com/ru/news-ai/tags/automation/",
    "automation_ai": "https://automation-ai.pro/",
}


def run_all_jobs():
    print("[START] Job runner started")

    # --- QUDATA ---
    qudata_list = load(SOURCES["qudata"])
    qudata_links = extract_qudata_links(qudata_list)

    if qudata_links:
        article_url = qudata_links[0]
        print("[ARTICLE] qudata:", article_url)

        soup = load(article_url)
        content = parse_qudata(soup)

        if content:
            publish(content)
            print("[OK] qudata published")
        else:
            print("[SKIP] qudata article empty")

    # --- AUTOMATION-AI ---
    ai_list = load(SOURCES["automation_ai"])
    ai_links = extract_automation_ai_links(ai_list)

    if ai_links:
        article_url = ai_links[0]
        print("[ARTICLE] automation-ai:", article_url)

        soup = load(article_url)
        content = parse_automation_ai(soup)

        if content:
            publish(content)
            print("[OK] automation-ai published")
        else:
            print("[SKIP] automation-ai article empty")

    print("[DONE] Job runner finished")
