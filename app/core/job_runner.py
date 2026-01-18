from app.parsers.html_loader import load
from app.parsers.qudata import parse_qudata
from app.parsers.automation_ai import parse_automation_ai
from app.core.publisher import publish
from app.parsers.medium_links import extract_medium_links
from app.parsers.hackernoon_links import extract_hackernoon_links

soup = load("https://towardsdatascience.com/tagged/automation")
links = extract_medium_links(soup)
print("MEDIUM LINKS:", links[:5])

soup = load("https://hackernoon.com/tagged/automation")
links = extract_hackernoon_links(soup)
print("HN LINKS:", links[:5])



URLS = [
    "https://qudata.com/ru/news-ai/tags/automation/",
    "https://automation-ai.pro/",
]


def run_all_jobs():
    print("[START] Job runner started")

    for url in URLS:
        print(f"[LOAD] {url}")

        try:
            soup = load(url)
        except Exception as e:
            print(f"[ERROR] failed to load {url}: {e}")
            continue

        content = {}

        if "qudata.com" in url:
            content = parse_qudata(soup)
        elif "automation-ai.pro" in url:
            content = parse_automation_ai(soup)

        if not content:
            print(f"[SKIP] no content extracted from {url}")
            continue

        print(
            "[CONTENT]",
            "title:", content.get("title"),
            "| text length:", len(content.get("text", "")),
            "| image:", bool(content.get("image")),
        )

        try:
            publish(content)
            print(f"[OK] published from {url}")
        except Exception as e:
            print(f"[ERROR] publish failed for {url}: {e}")

    print("[DONE] Job runner finished")
