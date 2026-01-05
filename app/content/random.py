# app/content/random.py

import random
from typing import Sequence, TypeVar

T = TypeVar("T")


def pick(items: Sequence[T]) -> T | None:
    if not items:
        return None
    return random.choice(items)

