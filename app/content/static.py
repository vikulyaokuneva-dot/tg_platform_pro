import random

CONTENT = {
    "IT юмор": [
        "Когда прод упал, а ты просто фронтендер 😅",
        "Работает — не трогай. Не работает — тоже не трогай.",
        "Dev — это когда гуглишь быстрее других."
    ],
    "Анекдот дня": [
        "— Ты программист?\n— Да.\n— А почему ты молчишь?\n— Я думаю.",
        "Программисты не ошибаются. Они создают новые баги."
    ],
}


def get_random(source: str) -> str | None:
    items = CONTENT.get(source)
    if not items:
        return None
    return random.choice(items)
