import json
from pathlib import Path

STATE_FILE = Path("state.json")

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent_urls": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))

def is_duplicate(url: str) -> bool:
    state = load_state()
    return url in state.get("sent_urls", [])

def mark_sent(url: str):
    state = load_state()
    sent = state.get("sent_urls", [])
    sent.append(url)
    state["sent_urls"] = sent
    save_state(state)
