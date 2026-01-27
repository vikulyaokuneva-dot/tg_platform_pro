import os
import json

# --- 1. СЕКРЕТЫ И НАСТРОЙКИ TELEGRAM ---

# Токен бота
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")

# Ключ GigaChat
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY")

# ID каналов (Исправлено под твой YML)
CHANNEL_IDS = {
    "AI_AUTOMATION": os.getenv("AI_AUTOMATION_CHAT_ID"),
    "ANEKDOTY": os.getenv("ANEKDOTY_CHAT_ID"),
    "CRYPTO_AIRDROPS": os.getenv("CRYPTO_AIRDROPS_CHAT_ID"),
    "CRYPTO_NEWS": os.getenv("CRYPTO_NEWS_CHAT_ID"),
    "IT_HUMOR": os.getenv("IT_HUMOR_CHAT_ID"),
    "PERSONAL_FINANCE": os.getenv("PERSONAL_FINANCE_CHAT_ID"),
    "PRODUCT_GROWTH": os.getenv("PRODUCT_GROWTH_CHAT_ID"),
    "PROGRAMMING_DEV": os.getenv("PROGRAMMING_DEV_CHAT_ID"),
    "STARTUPS_VC": os.getenv("STARTUPS_VC_CHAT_ID"),
    "STOCKS_INVESTING": os.getenv("STOCKS_INVESTING_CHAT_ID"),
}

# --- 1.1. ХЭШТЕГИ И СТИЛЬ ДЛЯ КАНАЛОВ ---
# Хэштеги добавляются к тем, что вернёт GigaChat.
CHANNEL_BASE_HASHTAGS = {
    "AI_AUTOMATION": ["#AI", "#automation"],
    "CRYPTO_NEWS": ["#crypto", "#news"],
    "CRYPTO_AIRDROPS": ["#airdrop", "#crypto"],
    "PROGRAMMING_DEV": ["#programming", "#dev"],
    "STARTUPS_VC": ["#startup", "#vc"],
    "PRODUCT_GROWTH": ["#growth", "#product"],
    "PERSONAL_FINANCE": ["#finance"],
    "STOCKS_INVESTING": ["#stocks", "#investing"],
    "IT_HUMOR": ["#it", "#humor"],
    "ANEKDOTY": ["#anekdot"],
}

# --- 2. НАСТРОЙКИ ПАРСИНГА (HTML ИСТОЧНИКИ) ---

HTML_SOURCES = {
    "AI_AUTOMATION": [
        {
            "name": "TechCrunch AI",
            "url": "https://techcrunch.com/category/artificial-intelligence/",
            "link_selector": "h3.loop-card__title a", 
            "base_url": "https://techcrunch.com"
        }
    ],
    "CRYPTO_NEWS": [
        {
            "name": "Cointelegraph",
            "url": "https://cointelegraph.com/",
            "link_selector": "a.post-card-inline__title-link",
            "base_url": "https://cointelegraph.com"
        }
    ],
    "CRYPTO_AIRDROPS": [
        {
            "name": "Airdrops.io",
            "url": "https://airdrops.io/latest/",
            "link_selector": "div.aidrop-content h3 a",
            "base_url": "https://airdrops.io"
        }
    ],
    "STARTUPS_VC": [
        {
            "name": "TechCrunch Startups",
            "url": "https://techcrunch.com/category/startups/",
            "link_selector": "h3.loop-card__title a",
            "base_url": "https://techcrunch.com"
        }
    ],
    "PERSONAL_FINANCE": [
        {
            "name": "Tinkoff Journal",
            "url": "https://journal.tinkoff.ru/news/",
            "link_selector": "a.card__link",
            "base_url": "https://journal.tinkoff.ru"
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
    "PRODUCT_GROWTH": [
        {
            "name": "Indie Hackers",
            "url": "https://www.indiehackers.com/popular",
            "link_selector": "a.feed-item__title-link",
            "base_url": "https://www.indiehackers.com"
        }
    ],
    "IT_HUMOR": [
        {
            "name": "Tproger Fun",
            "url": "https://tproger.ru/articles/fun/",
            "link_selector": "a.article__link",
            "base_url": "https://tproger.ru"
        }
    ],
    "STOCKS_INVESTING": [
        {
            "name": "Smart-Lab",
            "url": "https://smart-lab.ru/news/",
            "link_selector": "a.topic-title",
            "base_url": "https://smart-lab.ru"
        }
    ],
    # ANEKDOTY пока оставим как пример, но ему нужен особый парсер, 
    # так как там нет структуры "список ссылок -> статья"
    "ANEKDOTY": [] 
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}
