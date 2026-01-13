def build_article_post(content: dict) -> dict:
    title = content.get("title", "").strip()
    text = content.get("text", "").strip()
    image = content.get("image")

    if not title and not text:
        return {}

    return {
        "title": title,
        "text": text,
        "image": image,
    }
