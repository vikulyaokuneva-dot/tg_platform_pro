import random

WISDOMS = [
    "Терпение — главный инструмент садовода.",
    "Растения учат нас ждать и наблюдать.",
    "Лучший урожай приходит к тем, кто не спешит.",
]


def get_wisdom() -> str:
    return random.choice(WISDOMS)
