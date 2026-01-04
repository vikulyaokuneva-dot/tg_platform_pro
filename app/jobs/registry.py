# app/jobs/registry.py

from app.jobs.templates import (
    build_simple_post,

    build_it_humor_navigation,
    build_anekdoty_navigation,
    build_crypto_news_navigation,
    build_crypto_airdrops_navigation,
    build_ai_automation_navigation,
    build_personal_finance_navigation,
    build_stocks_investing_navigation,
    build_startups_vc_navigation,
    build_product_growth_navigation,
    build_programming_dev_navigation,
)


JOBS = {

    # ==============================
    # POSTING JOBS
    # ==============================

    "it_humor": {
        "channel": "it_humor",
        "builder": build_simple_post,
        "prefix": "😂 ",
        "source": "IT юмор",
    },

    "anekdoty": {
        "channel": "anekdoty",
        "builder": build_simple_post,
        "prefix": "🤣 ",
        "source": "Анекдот дня",
    },

    "crypto_news": {
        "channel": "crypto_news",
        "builder": build_simple_post,
        "prefix": "📈 ",
        "source": "Crypto News",
    },

    "crypto_airdrops": {
        "channel": "crypto_airdrops",
        "builder": build_simple_post,
        "prefix": "🎁 ",
        "source": "Airdrops",
    },

    "ai_automation": {
        "channel": "ai_automation",
        "builder": build_simple_post,
        "prefix": "🤖 ",
        "source": "AI Automation",
    },

    "personal_finance": {
        "channel": "personal_finance",
        "builder": build_simple_post,
        "prefix": "💰 ",
        "source": "Personal Finance",
    },

    "stocks_investing": {
        "channel": "stocks_investing",
        "builder": build_simple_post,
        "prefix": "📊 ",
        "source": "Stocks & Investing",
    },

    "startups_vc": {
        "channel": "startups_vc",
        "builder": build_simple_post,
        "prefix": "🚀 ",
        "source": "Startups & VC",
    },

    "product_growth": {
        "channel": "product_growth",
        "builder": build_simple_post,
        "prefix": "📈 ",
        "source": "Product Growth",
    },

    "programming_dev": {
        "channel": "programming_dev",
        "builder": build_simple_post,
        "prefix": "👨‍💻 ",
        "source": "Programming & Dev",
    },


    # ==============================
    # NAVIGATION (PINNED)
    # ==============================

    "it_humor_navigation": {
        "builder": build_it_humor_navigation,
        "channels": ["it_humor"],
        "pin": True,
    },

    "anekdoty_navigation": {
        "builder": build_anekdoty_navigation,
        "channels": ["anekdoty"],
        "pin": True,
    },

    "crypto_news_navigation": {
        "builder": build_crypto_news_navigation,
        "channels": ["crypto_news"],
        "pin": True,
    },

    "crypto_airdrops_navigation": {
        "builder": build_crypto_airdrops_navigation,
        "channels": ["crypto_airdrops"],
        "pin": True,
    },

    "ai_automation_navigation": {
        "builder": build_ai_automation_navigation,
        "channels": ["ai_automation"],
        "pin": True,
    },

    "personal_finance_navigation": {
        "builder": build_personal_finance_navigation,
        "channels": ["personal_finance"],
        "pin": True,
    },

    "stocks_investing_navigation": {
        "builder": build_stocks_investing_navigation,
        "channels": ["stocks_investing"],
        "pin": True,
    },

    "startups_vc_navigation": {
        "builder": build_startups_vc_navigation,
        "channels": ["startups_vc"],
        "pin": True,
    },

    "product_growth_navigation": {
        "builder": build_product_growth_navigation,
        "channels": ["product_growth"],
        "pin": True,
    },

    "programming_dev_navigation": {
        "builder": build_programming_dev_navigation,
        "channels": ["programming_dev"],
        "pin": True,
    },
}
