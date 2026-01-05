import json
from pathlib import Path
from datetime import date

STATE_FILE = Path("runtime_state.json")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def get_today_key(channel: str) -> str:
    return f"{channel}::{date.today().isoformat()}"

def was_used_recently(key: str, value: str) -> bool:
    state = load_state()
    return state.get(key) == value


def mark_used(key: str, value: str):
    state = load_state()
    state[key] = value
    save_state(state)
