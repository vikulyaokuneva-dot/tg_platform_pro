import random
from pathlib import Path

BASE_DIR = Path(__file__).parent / "fallback_images"

FALLBACK_MAP = {
    "it_memes": "it_memes/cover_pinned.png",
    "ai_inside": "ai_inside/cover_pinned.png",
    "code_daily": "code_daily/cover_pinned.png",
    "startup_chaos": "startup_chaos/cover_pinned.png",
    "dev_life": "dev_life/cover_pinned.png",
    "bug_hunter": "bug_hunter/cover_pinned.png",
    "no_code_lab": "no_code_lab/cover_pinned.png",
    "tech_news": "tech_news/cover_pinned.png",
    "future_stack": "future_stack/cover_pinned.png",
}

DEFAULT_IMAGE = "default/cover_pinned.png"
