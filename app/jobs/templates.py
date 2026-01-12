def build_article_post(job):
    c = job["content"]

    text = f"<b>{c['title']}</b>\n\n{c['text']}"
    return {
        "text": text,
        "image": c.get("image"),
    }
