from app.jobs.templates import build_simple_post

JOBS = {
    "it_humor": {
        "channel": "it_humor",
        "builder": build_simple_post,
        "prefix": "😂 ",
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
        "source": "Airdrop"
    },
}
