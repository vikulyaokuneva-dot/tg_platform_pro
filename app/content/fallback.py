import random
from pathlib import Path

BASE_DIR = Path(__file__).parent / "fallback_images"

FALLBACK_MAP = {
    "it_humor": "it_humor.jpg",
    "programming_dev": "programming.jpg",
    "crypto_news": "crypto.jpg",
    "ai_automation": "ai.jpg",
    "personal_finance": "finance.jpg",
    "startups_vc": "startups.jpg",
}

DEFAULT_IMAGE = "default.jpg"


def get_fallback_image(channel: str) -> str:
    filename = FALLBACK_MAP.get(channel, DEFAULT_IMAGE)
    return str(BASE_DIR / filename)
