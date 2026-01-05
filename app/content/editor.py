def shorten(text: str, max_sentences=2) -> str:
    sentences = text.split(".")
    return ".".join(sentences[:max_sentences]).strip() + "."
