import random
from datetime import datetime
from app.core.state import load_state, save_state, get_today_key

def can_publish(channel: str, posts_per_day: int) -> bool:
    state = load_state()
    key = get_today_key(channel)
    return state.get(key, 0) < posts_per_day

def mark_published(channel: str):
    state = load_state()
    key = get_today_key(channel)
    state[key] = state.get(key, 0) + 1
    save_state(state)

def pick_job_with_rules(jobs: dict, channel: str):
    content_jobs = [j for j in jobs.values() if j.get("channel")==channel and j.get("source")]
    weighted = []
    for j in content_jobs:
        weighted.extend([j] * j.get("weight", 1))
    return random.choice(weighted) if weighted else None
