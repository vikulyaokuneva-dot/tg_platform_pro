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
    # 1. AI & AUTOMATION
    "AI_AUTOMATION": [
        {
            "name": "TechCrunch AI",
            "url": "https://techcrunch.com/category/artificial-intelligence/",
            "link_selector": "h3.loop-card__title a", 
            "base_url": "https://techcrunch.com"
        },
        {
            "name": "The Verge AI",
            "url": "https://www.theverge.com/ai-artificial-intelligence",
            "link_selector": "h2.font-polysans a", # Часто меняется, требует проверки
            "base_url": "https://www.theverge.com"
        }
    ],

    # 2. CRYPTO NEWS (Cointelegraph & CoinDesk)
    "CRYPTO_NEWS": [
        {
            "name": "Cointelegraph",
            "url": "https://cointelegraph.com/",
            "link_selector": "a.post-card-inline__title-link",
            "base_url": "https://cointelegraph.com"
        },
        {
            "name": "CoinDesk",
            "url": "https://www.coindesk.com/",
            "link_selector": "a.card-title", # Может захватывать лишнее, но для начала пойдет
            "base_url": "https://www.coindesk.com"
        }
    ],

    # 3. CRYPTO AIRDROPS
    "CRYPTO_AIRDROPS": [
        {
            "name": "Airdrops.io",
            "url": "https://airdrops.io/latest/",
            "link_selector": "div.aidrop-content h3 a",
            "base_url": "https://airdrops.io"
        }
    ],

    # 4. STARTUPS & VC
    "STARTUPS_VC": [
        {
            "name": "VC.ru (Startups)",
            "url": "https://vc.ru/new", # Лента "Свежее"
            "link_selector": "div.content-title--short a",
            "base_url": "https://vc.ru"
        },
        {
            "name": "TechCrunch Startups",
            "url": "https://techcrunch.com/category/startups/",
            "link_selector": "h3.loop-card__title a",
            "base_url": "https://techcrunch.com"
        }
    ],

    # 5. PERSONAL FINANCE
    "PERSONAL_FINANCE": [
        {
            "name": "Tinkoff Journal (News)",
            "url": "https://journal.tinkoff.ru/news/",
            "link_selector": "a.card__link",
            "base_url": "https://journal.tinkoff.ru"
        }
    ],

    # 6. PROGRAMMING DEV
    "PROGRAMMING_DEV": [
        {
            "name": "Dev.to",
            "url": "https://dev.to/top/week",
            "link_selector": "h2.crayons-story__title a",
            "base_url": "https://dev.to"
        },
        {
            "name": "Habr (Python)",
            "url": "https://habr.com/ru/hub/python/",
            "link_selector": "a.tm-title__link",
            "base_url": "https://habr.com"
        }
    ],

    # 7. PRODUCT GROWTH
    "PRODUCT_GROWTH": [
        {
            "name": "Indie Hackers",
            "url": "https://www.indiehackers.com/popular",
            "link_selector": "a.feed-item__title-link",
            "base_url": "https://www.indiehackers.com"
        }
    ],
    
    # 8. IT HUMOR
    "IT_HUMOR": [
        {
            # Для Reddit лучше использовать JSON API (добавив .json к URL), 
            # но наш парсер заточен под HTML. Reddit HTML сложный.
            # Попробуем альтернативу:
            "name": "Tproger (Fun)",
            "url": "https://tproger.ru/articles/fun/",
            "link_selector": "a.article__link",
            "base_url": "https://tproger.ru"
        }
    ],

    # 9. STOCKS
    "STOCKS_INVESTING": [
        {
            "name": "Smart-Lab",
            "url": "https://smart-lab.ru/news/",
            "link_selector": "a.topic-title",
            "base_url": "https://smart-lab.ru"
        }
    ],

    # 10. ANEKDOTY
    "ANEKDOTY": [
         {
            "name": "Anekdot.ru",
            "url": "https://www.anekdot.ru/last/anekdot/",
            # Тут нет ссылок на отдельные страницы "нового", 
            # тексты лежат прямо в div.text.
            # Для этого канала понадобится доработка в run_once.py, 
            # либо парсинг "лучшего за день", где есть постоянные ссылки.
            "link_selector": "div.topicbox a.text", 
            "base_url": "https://www.anekdot.ru"
        }
    ]
}

# Заголовки, чтобы притворяться браузером (анти-бот защита)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}


