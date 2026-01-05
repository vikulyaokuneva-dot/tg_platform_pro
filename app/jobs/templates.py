# app/jobs/templates.py

from app.content.static import get_random
from app.content.wisdom import get_wisdom
from app.content.rss import fetch
from app.content.editor import shorten


# ==============================
# SIMPLE POSTS (STATIC)
# ==============================

def build_simple_post(job) -> str | None:
    prefix = job.get("prefix", "")
    source = job.get("source")
    hashtags = job.get("hashtags", [])

    text = get_random(source)
    if not text:
        return None

    tags = " ".join(f"#{t}" for t in hashtags)
    return f"{prefix}{text}\n\n{tags}"


# ==============================
# WISDOM / SPECIAL POST
# ==============================

def build_wisdom_post(job) -> str:
    return get_wisdom()


# ==============================
# RSS → EDITORIAL (САД БЕЗ ХЛОПОТ)
# ==============================

def build_rss_editorial_post(job):
    feed_url = job.get("feed_url")
    hashtags = job.get("hashtags", [])

    data = fetch(feed_url)
    if not data:
        return None

    short = shorten(data["text"], 2)
    tags = " ".join(f"#{t}" for t in hashtags)

    return {
        "text": (
            f"<b>{data['title']}</b>\n\n"
            f"{short}\n\n"
            f"{data['link']}\n\n"
            f"{tags}"
        ),
        "image": data.get("image"),
    }


# ==============================
# NAVIGATION BUILDERS
# ==============================

def build_it_humor_navigation(job=None):
    return (
        "📌 Навигация по каналу «IT юмор»\n\n"
        "😂 Юмор — #humor\n"
        "🐞 Баги — #bugs\n"
        "💻 Программирование — #programming\n"
        "⏰ Дедлайны — #deadlines\n"
        "👨‍💻 Работа в IT — #itjob\n\n"
        "Нажмите на тег, чтобы увидеть все посты 👇"
    )


def build_anekdoty_navigation(job=None):
    return (
        "📌 Навигация по каналу «Анекдот дня»\n\n"
        "🤣 Анекдоты — #анекдоты\n"
        "😂 Юмор — #юмор\n"
        "😄 Классика — #classic\n\n"
        "Нажмите на хештег, чтобы посмотреть все шутки 👇"
    )


def build_crypto_news_navigation(job=None):
    return (
        "📌 Навигация по каналу «Crypto News»\n\n"
        "📈 Рынок — #crypto #market\n"
        "🪙 Биткоин — #bitcoin\n"
        "🧠 Аналитика — #analysis\n"
        "⚡️ Новости — #news\n\n"
        "Нажмите на хештег, чтобы открыть все посты 👇"
    )


def build_crypto_airdrops_navigation(job=None):
    return (
        "📌 Навигация по каналу «Crypto Airdrops»\n\n"
        "🎁 Аирдропы — #airdrop\n"
        "🪂 Активные — #active\n"
        "⏳ Скоро — #upcoming\n"
        "⚠️ Скам — #scam\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_ai_automation_navigation(job=None):
    return (
        "📌 Навигация по каналу «AI Automation»\n\n"
        "🤖 AI — #ai\n"
        "⚙️ Автоматизация — #automation\n"
        "🧠 LLM — #llm\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_personal_finance_navigation(job=None):
    return (
        "📌 Навигация по каналу «Personal Finance»\n\n"
        "💰 Финансы — #finance\n"
        "📊 Инвестиции — #investing\n"
        "🧾 Налоги — #taxes\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_stocks_investing_navigation(job=None):
    return (
        "📌 Навигация по каналу «Stocks & Investing»\n\n"
        "📊 Акции — #stocks\n"
        "📈 Рынок — #market\n"
        "🏦 ETF — #etf\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_startups_vc_navigation(job=None):
    return (
        "📌 Навигация по каналу «Startups & VC»\n\n"
        "🚀 Стартапы — #startup\n"
        "💼 Венчур — #vc\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_product_growth_navigation(job=None):
    return (
        "📌 Навигация по каналу «Product Growth»\n\n"
        "📈 Рост — #growth\n"
        "🧪 Эксперименты — #experiments\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_programming_dev_navigation(job=None):
    return (
        "📌 Навигация по каналу «Programming & Dev»\n\n"
        "👨‍💻 Код — #programming\n"
        "⚙️ Backend — #backend\n"
        "🎨 Frontend — #frontend\n\n"
        "Нажмите на хештег для просмотра 👇"
    )
