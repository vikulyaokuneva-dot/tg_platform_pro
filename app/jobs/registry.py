from app.jobs.templates import build_simple_post

JOBS = {
    "it_humor": {
        "channel": "it_humor",
        "builder": build_simple_post,
        "prefix": "😂 ",
        "source": "IT юмор"
    },
    "anekdoty": {
        "channel": "anekdoty",
        "builder": build_simple_post,
        "prefix": "🤣 ",
        "source": "Анекдот дня"
    },
    "crypto_news": {
        "channel": "crypto_news",
        "builder": build_simple_post,
        "prefix": "📈 ",
        "source": "Crypto News"
    },
    "crypto_airdrops": {
        "channel": "crypto_airdrops",
        "builder": build_simple_post,
        "prefix": "🎁 ",
        "source": "Airdrops"
    },
    "ai_automation": {
        "channel": "ai_automation",
        "builder": build_simple_post,
        "prefix": "🤖 ",
        "source": "AI Automation"
    },
    "personal_finance": {
        "channel": "personal_finance",
        "builder": build_simple_post,
        "prefix": "💰 ",
        "source": "Personal Finance"
    },
    "stocks_investing": {
        "channel": "stocks_investing",
        "builder": build_simple_post,
        "prefix": "📊 ",
        "source": "Stocks & Investing"
    },
    "startups_vc": {
        "channel": "startups_vc",
        "builder": build_simple_post,
        "prefix": "🚀 ",
        "source": "Startups & VC"
    },
    "product_growth": {
        "channel": "product_growth",
        "builder": build_simple_post,
        "prefix": "📈 ",
        "source": "Product Growth"
    },
    "programming_dev": {
        "channel": "programming_dev",
        "builder": build_simple_post,
        "prefix": "👨‍💻 ",
        "source": "Programming & Dev"
    },
}

