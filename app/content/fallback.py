import random
from pathlib import Path

# Базовая директория с fallback-изображениями
BASE_DIR = Path(__file__).parent / "fallback_images"

# Дефолтная картинка, если ничего не найдено
DEFAULT_IMAGE = "default/cover_pinned.png"


def get_fallback_image(channel: str) -> str:
    """
    Возвращает путь к fallback-изображению для канала.

    Приоритет:
    1. random visual_*.png из папки канала
    2. cover_pinned.png из папки канала
    3. default/cover_pinned.png
    """

    channel_dir = BASE_DIR / channel

    # 1. Пытаемся взять случайный visual_*.png
    if channel_dir.exists() and channel_dir.is_dir():
        visuals = list(channel_dir.glob("visual_*.png"))
        if visuals:
            return str(random.choice(visuals))

        # 2. Если нет visual — берём cover_pinned
        cover = channel_dir / "cover_pinned.png"
        if cover.exists():
            return str(cover)

    # 3. Фолбэк по умолчанию
    return str(BASE_DIR / DEFAULT_IMAGE)
