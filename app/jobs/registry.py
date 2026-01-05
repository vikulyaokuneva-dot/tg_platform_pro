# app/jobs/registry.py

from app.jobs.templates import (
    build_simple_post,
    build_wisdom_post,
    build_rss_editorial_post,

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
    # CONTENT
    # ==============================

    "it_humor": {
        "channel": "it_humor",
        "builder": build_simple_post,
        "prefix": "😂 ",
        "source": "IT юмор",
        "hashtags": ["humor", "it"],
    },

    "anekdoty": {
        "channel": "anekdoty",
        "builder": build_simple_post,
        "prefix": "🤣 ",
        "source": "Анекдот дня",
        "hashtags": ["юмор", "анекдоты"],
        "posts_per_day": 10,
        "special_post_every": 10,
        "wisdom_builder": build_wisdom_post,
    },

    "it_rss": {
        "channel": "it_humor",
        "builder": build_rss_editorial_post,
        "feed_url": "https://habr.com/ru/rss/all/all/",
        "hashtags": ["programming", "itnews"],
        "posts_per_day": 2,
        "weight": 2,
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
