import random
from app.core.state import load_state, save_state


def pick_from_cycle(source: str, items: list[str]) -> str | None:
    if not items:
        return None

    state = load_state()
    used = set(state.get(f"used::{source}", []))

    available = [i for i in items if i not in used]

    if not available:
        # цикл завершён — сброс
        used = set()
        available = items

    choice = random.choice(available)

    used.add(choice)
    state[f"used::{source}"] = list(used)
    save_state(state)

    return choice
