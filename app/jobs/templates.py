# app/jobs/templates.py

from app.content.static import get_all_items
from app.content.cycle import pick_from_cycle
from app.content.wisdom import get_wisdom
from app.content.rss import fetch
from app.content.editor import shorten
from app.content.fallback import get_fallback_image


# ==============================
# HASHTAGS (RU NORMALIZED)
# ==============================

HASHTAGS_RU = {
    "humor": "юмор",
    "bugs": "баги",
    "programming": "программирование",
    "deadlines": "дедлайны",
    "itjob": "работаВIT",

    "ai": "ии",
    "automation": "автоматизация",
    "llm": "llm",

    "crypto": "крипта",
    "market": "рынок",
    "bitcoin": "биткоин",
    "analysis": "аналитика",
    "news": "новости",
    "airdrop": "аирдроп",
    "active": "активные",
    "upcoming": "скоро",
    "scam": "скам",

    "finance": "финансы",
    "investing": "инвестиции",
    "taxes": "налоги",

    "stocks": "акции",
    "etf": "etf",

    "startup": "стартапы",
    "vc": "венчур",

    "growth": "рост",
    "experiments": "эксперименты",

    "backend": "бэкенд",
    "frontend": "фронтенд",
}


def build_tags(hashtags: list[str]) -> str:
    if not hashtags:
        return ""
    return " ".join(f"#{HASHTAGS_RU.get(t, t)}" for t in hashtags)


# ==============================
# SIMPLE POSTS (STATIC)
# ==============================

def build_simple_post(job) -> str | None:
    prefix = job.get("prefix", "")
    source = job.get("source")
    hashtags = job.get("hashtags", [])

    if not source:
        return None

    items = get_all_items(source)
    if not items:
        return None

    text = pick_from_cycle(source, items)
    if not text:
        return None

    tags = build_tags(hashtags)
    return f"{prefix}{text}\n\n{tags}".strip()


# ==============================
# WISDOM / SPECIAL POST
# ==============================

def build_wisdom_post(job) -> str:
    return get_wisdom()


# ==============================
# RSS → EDITORIAL
# ==============================

def build_rss_editorial_post(job):
    feed_url = job.get("feed_url")
    hashtags = job.get("hashtags", [])
    channel = job.get("channel")

    data = fetch(feed_url)
    if not data:
        return None

    short = shorten(data["text"], 2)
    tags = build_tags(hashtags)

    image = data.get("image") or get_fallback_image(channel)

    return {
        "text": (
            f"<b>{data['title']}</b>\n\n"
            f"{short}\n\n"
            f"{data['link']}\n\n"
            f"{tags}"
        ),
        "image": image,
    }


# ==============================
# NAVIGATION BUILDERS (RU)
# ==============================

def build_it_humor_navigation(job=None):
    return (
        "📌 Навигация по каналу «IT юмор»\n\n"
        "😂 Юмор — #юмор\n"
        "🐞 Баги — #баги\n"
        "💻 Программирование — #программирование\n"
        "⏰ Дедлайны — #дедлайны\n"
        "👨‍💻 Работа в IT — #работаВIT\n\n"
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
        "📈 Рынок — #рынок\n"
        "🪙 Биткоин — #биткоин\n"
        "🧠 Аналитика — #аналитика\n"
        "⚡️ Новости — #новости\n\n"
        "Нажмите на хештег, чтобы открыть все посты 👇"
    )


def build_crypto_airdrops_navigation(job=None):
    return (
        "📌 Навигация по каналу «Crypto Airdrops»\n\n"
        "🎁 Аирдропы — #аирдроп\n"
        "🪂 Активные — #активные\n"
        "⏳ Скоро — #скоро\n"
        "⚠️ Скам — #скам\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_ai_automation_navigation(job=None):
    return (
        "📌 Навигация по каналу «AI Automation»\n\n"
        "🤖 AI — #ии\n"
        "⚙️ Автоматизация — #автоматизация\n"
        "🧠 LLM — #llm\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_personal_finance_navigation(job=None):
    return (
        "📌 Навигация по каналу «Personal Finance»\n\n"
        "💰 Финансы — #финансы\n"
        "📊 Инвестиции — #инвестиции\n"
        "🧾 Налоги — #налоги\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_stocks_investing_navigation(job=None):
    return (
        "📌 Навигация по каналу «Stocks & Investing»\n\n"
        "📊 Акции — #акции\n"
        "📈 Рынок — #рынок\n"
        "🏦 ETF — #etf\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_startups_vc_navigation(job=None):
    return (
        "📌 Навигация по каналу «Startups & VC»\n\n"
        "🚀 Стартапы — #стартапы\n"
        "💼 Венчур — #венчур\n\n"
        "Нажмите на хештег для просмотра 👇"
    )


def build_product_growth_navigation(job=None):
    return (
        "📌 Навигация по каналу «Product Growth»\n\n"
        "📈 Рост — #рост\n"
        "🧪 Эксперименты — #эксперименты\n\n"
        "Нажмите на хештег для навигации 👇"
    )


def build_programming_dev_navigation(job=None):
    return (
        "📌 Навигация по каналу «Programming & Dev»\n\n"
        "👨‍💻 Код — #программирование\n"
        "⚙️ Backend — #бэкенд\n"
        "🎨 Frontend — #фронтенд\n\n"
        "Нажмите на хештег для просмотра 👇"
    )
