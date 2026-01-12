def build_simple_post(job):
    content = job.get('content') or {}
    title = content.get('title', '')
    text = content.get('text', '')
    return f"{title}\n\n{text}".strip()
