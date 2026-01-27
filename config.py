import os

# =========================
# Telegram
# =========================
BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN", "")

# =========================
# GigaChat
# =========================
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2")

# =========================
# Retry/Timeout
# =========================
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "2"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))

# Сколько ссылок брать с каждого источника (чтобы не упираться в "топ-5" и не молчать)
MAX_LINKS_PER_SOURCE = int(os.getenv("MAX_LINKS_PER_SOURCE", "120"))

# =========================
# 1. Каналы (chat_id берутся из env)
# =========================
CHANNEL_IDS = {
    "AI_AUTOMATION": os.getenv("AI_AUTOMATION_CHAT_ID", ""),
    "CRYPTO_NEWS": os.getenv("CRYPTO_NEWS_CHAT_ID", ""),
    "CRYPTO_AIRDROPS": os.getenv("CRYPTO_AIRDROPS_CHAT_ID", ""),
    "PROGRAMMING_DEV": os.getenv("PROGRAMMING_DEV_CHAT_ID", ""),
    "STARTUPS_VC": os.getenv("STARTUPS_VC_CHAT_ID", ""),
    "PRODUCT_GROWTH": os.getenv("PRODUCT_GROWTH_CHAT_ID", ""),
    "PERSONAL_FINANCE": os.getenv("PERSONAL_FINANCE_CHAT_ID", ""),
    "STOCKS_INVESTING": os.getenv("STOCKS_INVESTING_CHAT_ID", ""),
    "IT_HUMOR": os.getenv("IT_HUMOR_CHAT_ID", ""),
    "ANEKDOTY": os.getenv("ANEKDOTY_CHAT_ID", ""),
}

# =========================
# 1.1 Хэштеги и стиль
# =========================
# Эти хэштеги добавляются к тем, что вернёт GigaChat (если вернёт).
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

# Уникальный "бренд-тег" и эмодзи для каждого канала (только ваши)
CHANNEL_META = {
    "AI_AUTOMATION": {"brand_tag": "#ai_auto", "title_emoji": "🤖"},
    "CRYPTO_NEWS": {"brand_tag": "#crypto_news_ru", "title_emoji": "🪙"},
    "CRYPTO_AIRDROPS": {"brand_tag": "#airdrop_hunt", "title_emoji": "🎁"},
    "PROGRAMMING_DEV": {"brand_tag": "#dev_digest", "title_emoji": "💻"},
    "STARTUPS_VC": {"brand_tag": "#startup_watch", "title_emoji": "🚀"},
    "PRODUCT_GROWTH": {"brand_tag": "#growth_lab", "title_emoji": "📈"},
    "PERSONAL_FINANCE": {"brand_tag": "#money_smart", "title_emoji": "💰"},
    "STOCKS_INVESTING": {"brand_tag": "#market_pulse", "title_emoji": "📊"},
    "IT_HUMOR": {"brand_tag": "#it_fun", "title_emoji": "😂"},
    "ANEKDOTY": {"brand_tag": "#anekdot_day", "title_emoji": "😄"},
}

# =========================
# 2. Источники
# Формат:
#  - type: "html" или "rss"
#  - url: страница/фид
#  - link_selector: CSS селектор для ссылок
#  - base_url: нужно если ссылки относительные (для html)
# =========================
SOURCES = {
"AI_AUTOMATION": [
    {
        "name": "TechCrunch AI",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p2",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/2/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p3",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/3/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p4",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/4/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p5",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/5/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p6",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/6/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p7",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/7/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch AI p8",
        "type": "html",
        "url": "https://techcrunch.com/tag/artificial-intelligence/page/8/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
],


"STARTUPS_VC": [
    {
        "name": "TechCrunch Startups",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p2",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/2/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p3",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/3/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p4",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/4/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p5",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/5/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p6",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/6/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p7",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/7/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
    {
        "name": "TechCrunch Startups p8",
        "type": "html",
        "url": "https://techcrunch.com/tag/startups/page/8/",
        "link_selector": "a.post-block__title__link",
        "base_url": "https://techcrunch.com",
    },
],


    "PROGRAMMING_DEV": [
        {
            "name": "Dev.to (Top Week)",
            "type": "html",
            "url": "https://dev.to/top/week",
            "link_selector": "a.crayons-story__hidden-navigation-link",
            "base_url": "https://dev.to",
        }
    ],
    "PRODUCT_GROWTH": [
        {
            "name": "Indie Hackers",
            "type": "html",
            "url": "https://www.indiehackers.com/",
            "link_selector": "a[href^='/post/']",
            "base_url": "https://www.indiehackers.com",
        }
    ],
    "CRYPTO_NEWS": [
        {
            "name": "Cointelegraph",
            "type": "html",
            "url": "https://cointelegraph.com/",
            "link_selector": "a[href^='/news/']",
            "base_url": "https://cointelegraph.com",
        }
    ],
    "CRYPTO_AIRDROPS": [
        {
            "name": "AirdropAlert RSS",
            "type": "rss",
            "url": "https://airdropalert.com/feed/rssfeed",
            "link_selector": "item > link",
            "base_url": "",
        },
    ],
    "IT_HUMOR": [
        {
            "name": "Tproger (Свежее)",
            "type": "html",
            "url": "https://tproger.ru/",
            "link_selector": "a[href^='/articles/']",
            "base_url": "https://tproger.ru",
        }
    ],
    "STOCKS_INVESTING": [
        {
            "name": "Smartlab.news (главная)",
            "type": "html",
            "url": "https://smartlab.news/",
            "link_selector": "a[href^='/i/'], a[href^='/news/'], a[href^='/blog/']",
            "base_url": "https://smartlab.news",
        }
    ],


    "PERSONAL_FINANCE": [
        {
            "name": "CBR (news/events) RSS",
            "type": "rss",
            "url": "http://www.cbr.ru/rss/eventrss",
            "link_selector": "item > link",
            "base_url": "",
        },
        {
            "name": "CBR (press releases) RSS",
            "type": "rss",
            "url": "http://www.cbr.ru/rss/RssPress",
            "link_selector": "item > link",
            "base_url": "",
        },
    ],
    "ANEKDOTY": [
        # RSS ленты (уникальные ссылки, нормально для БД)
        {
            "name": "Anekdot.ru RSS (daily top)",
            "type": "rss",
            "url": "https://www.anekdot.ru/rss/export_j.xml",
            "link_selector": "item > link",
            "base_url": "",
        },
        {
            "name": "Anekdot.ru RSS (no politics)",
            "type": "rss",
            "url": "https://www.anekdot.ru/rss/export_j_non_burning.xml",
            "link_selector": "item > link",
            "base_url": "",
        },
    ],
}
