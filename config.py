import os
import json

# --- 1. СЕКРЕТЫ И НАСТРОЙКИ TELEGRAM ---

# Токен бота
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")

# ID каналов. 
# Скрипт ожидает, что в GitHub Secrets/Env они записаны как:
# CHANNEL_ID_AI_AUTOMATION="-10012345678"
# CHANNEL_ID_IT_HUMOR="-10098765432" и т.д.
CHANNEL_IDS = {
    "AI_AUTOMATION": os.getenv("CHANNEL_ID_AI_AUTOMATION"),
    "ANEKDOTY": os.getenv("CHANNEL_ID_ANEKDOTY"),
    "CRYPTO_AIRDROPS": os.getenv("CHANNEL_ID_CRYPTO_AIRDROPS"),
    "CRYPTO_NEWS": os.getenv("CHANNEL_ID_CRYPTO_NEWS"),
    "IT_HUMOR": os.getenv("CHANNEL_ID_IT_HUMOR"),
    "PERSONAL_FINANCE": os.getenv("CHANNEL_ID_PERSONAL_FINANCE"),
    "PRODUCT_GROWTH": os.getenv("CHANNEL_ID_PRODUCT_GROWTH"),
    "PROGRAMMING_DEV": os.getenv("CHANNEL_ID_PROGRAMMING_DEV"),
    "STARTUPS_VC": os.getenv("CHANNEL_ID_STARTUPS_VC"),
    "STOCKS_INVESTING": os.getenv("CHANNEL_ID_STOCKS_INVESTING"),
}

# --- 2. НАСТРОЙКИ ПАРСИНГА (HTML ИСТОЧНИКИ) ---

# Структура:
# "CATEGORY_NAME": [
#    {
#       "name": "Название источника (для логов)",
#       "url": "Ссылка на страницу рубрики/ленты",
#       "link_selector": "CSS селектор, указывающий на ссылку <a> статьи",
#       "base_url": "Базовый URL (если ссылки относительные, напр /news/123)"
#    }
# ]

HTML_SOURCES = {
    "AI_AUTOMATION": [
        {
            "name": "TechCrunch AI",
            "url": "https://techcrunch.com/category/artificial-intelligence/",
            "link_selector": "h3.loop-card__title a", 
            "base_url": "https://techcrunch.com"
        },
        {
            "name": "OpenAI Blog",
            "url": "https://openai.com/news/blog/",
            "link_selector": "a.ui-link-group", # Пример, может меняться
            "base_url": "https://openai.com"
        }
    ],
    "PROGRAMMING_DEV": [
        {
            "name": "Dev.to (Top Week)",
            "url": "https://dev.to/top/week",
            "link_selector": "h2.crayons-story__title a",
            "base_url": "https://dev.to"
        }
    ],
    "IT_HUMOR": [
        {
            # Для Reddit используем старый добрый .rss, так как HTML там сложный
            # Но если нужно парсить HTML, нужен очень хитрый User-Agent
            "name": "Reddit ProgrammerHumor",
            "url": "https://www.reddit.com/r/ProgrammerHumor/top/?t=day",
            "link_selector": "a[data-click-id='body']", # Специфично для Reddit
            "base_url": "https://www.reddit.com"
        }
    ],
    "ANEKDOTY": [
        {
            "name": "Anekdot.ru",
            "url": "https://www.anekdot.ru/last/anekdot/",
            # Anekdot.ru специфичен, там текст прямо в ленте. 
            # Парсер в run_once.py попытается найти ссылку, но для анекдотов
            # часто нужна отдельная логика. Пока оставим как пример блога.
            "link_selector": "div.topicbox a.text", 
            "base_url": "https://www.anekdot.ru"
        }
    ]
    # ... Добавьте остальные категории по аналогии
}

# Заголовки, чтобы притворяться браузером (анти-бот защита)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

