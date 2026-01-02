def build_simple_post(job):
    prefix = job.get("prefix", "")
    source = job.get("source", "")
    return f"{prefix}{source}"
