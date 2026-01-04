import os

POSTER_BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")

CHANNELS = {
    "it_humor": os.getenv("IT_HUMOR_CHAT_ID"),
    "crypto_news": os.getenv("CRYPTO_NEWS_CHAT_ID"),
    "crypto_airdrops": os.getenv("CRYPTO_AIRDROPS_CHAT_ID"),
    "ai_automation": os.getenv("AI_AUTOMATION_CHAT_ID"),
    "personal_finance": os.getenv("PERSONAL_FINANCE_CHAT_ID"),
    "stocks_investing": os.getenv("STOCKS_INVESTING_CHAT_ID"),
    "startups_vc": os.getenv("STARTUPS_VC_CHAT_ID"),
    "product_growth": os.getenv("PRODUCT_GROWTH_CHAT_ID"),
    "programming_dev": os.getenv("PROGRAMMING_DEV_CHAT_ID"),
    "anekdoty": os.getenv("ANEKDOTY_CHAT_ID"),
}

