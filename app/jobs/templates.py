# app/jobs/templates.py

from app.content.static import get_random

def build_simple_post(job) -> str | None:
    prefix = job.get("prefix", "")
    source = job.get("source")

    text = get_random(source)
    if not text:
        return None

    return f"{prefix}{text}"




# ==============================
# IT HUMOR
# ==============================

def build_it_humor_navigation(job=None):
    return (
        "📌 Навигация по каналу «IT юмор»\n\n"

        "😂 Мемы и шутки — #itюмор #memes\n"
        "💻 Программирование — #programming #dev\n"
        "🐞 Баги и фейлы — #bugs #fail\n"
        "🚀 Стартапы — #startup #itlife\n"
        "🧠 Мысли разработчиков — #devlife\n\n"

        "🔗 Внешние ресурсы:\n"
        "• GitHub — https://github.com\n"
        "• Stack Overflow — https://stackoverflow.com\n"
        "• Habr — https://habr.com\n"
        "• Reddit r/programming — https://reddit.com/r/programming\n\n"

        "Нажмите на хештег, чтобы увидеть все посты по теме 👇"
    )


# ==============================
# ANEKDOTY
# ==============================

def build_anekdoty_navigation(job=None):
    return (
        "📌 Навигация по каналу «Анекдот дня»\n\n"

        "🤣 Лучшие анекдоты — #анекдоты\n"
        "😂 Короткие шутки — #юмор\n"
        "😄 Классика — #classic\n\n"

        "🔗 Внешние ресурсы:\n"
        "• anekdot.ru — https://anekdot.ru\n"
        "• bash.im — https://bash.im\n\n"

        "Нажмите на хештег, чтобы посмотреть все шутки 👇"
    )


# ==============================
# CRYPTO NEWS
# ==============================

def build_crypto_news_navigation(job=None):
    return (
        "📌 Навигация по каналу «Crypto News»\n\n"

        "📈 Рынок — #crypto #market\n"
        "🪙 Биткоин — #bitcoin\n"
        "🧠 Аналитика — #analysis\n"
        "⚡️ Новости — #news\n\n"

        "🔗 Внешние ресурсы:\n"
        "• CoinMarketCap — https://coinmarketcap.com\n"
        "• CoinDesk — https://coindesk.com\n"
        "• CoinTelegraph — https://cointelegraph.com\n\n"

        "Нажмите на хештег, чтобы открыть все посты 👇"
    )


# ==============================
# CRYPTO AIRDROPS
# ==============================

def build_crypto_airdrops_navigation(job=None):
    return (
        "📌 Навигация по каналу «Crypto Airdrops»\n\n"

        "🎁 Аирдропы — #airdrop\n"
        "🪂 Активные — #active\n"
        "⏳ Скоро — #upcoming\n"
        "⚠️ Скам — #scam\n\n"

        "🔗 Внешние ресурсы:\n"
        "• Airdrops.io — https://airdrops.io\n"
        "• CoinMarketCap Airdrops — https://coinmarketcap.com/airdrop\n\n"

        "Нажмите на хештег для просмотра 👇"
    )


# ==============================
# AI AUTOMATION
# ==============================

def build_ai_automation_navigation(job=None):
    return (
        "📌 Навигация по каналу «AI Automation»\n\n"

        "🤖 AI инструменты — #ai #tools\n"
        "⚙️ Автоматизация — #automation\n"
        "🧠 ML / LLM — #ml #llm\n"
        "📦 Кейсы — #cases\n\n"

        "🔗 Внешние ресурсы:\n"
        "• OpenAI — https://openai.com\n"
        "• Hugging Face — https://huggingface.co\n"
        "• LangChain — https://langchain.com\n\n"

        "Нажмите на хештег для навигации 👇"
    )


# ==============================
# PERSONAL FINANCE
# ==============================

def build_personal_finance_navigation(job=None):
    return (
        "📌 Навигация по каналу «Personal Finance»\n\n"

        "💰 Экономия — #finance\n"
        "📊 Инвестиции — #investing\n"
        "🏦 Банки — #banking\n"
        "🧾 Налоги — #taxes\n\n"

        "🔗 Внешние ресурсы:\n"
        "• Investopedia — https://investopedia.com\n"
        "• NerdWallet — https://nerdwallet.com\n\n"

        "Нажмите на хештег для просмотра 👇"
    )


# ==============================
# STOCKS & INVESTING
# ==============================

def build_stocks_investing_navigation(job=None):
    return (
        "📌 Навигация по каналу «Stocks & Investing»\n\n"

        "📊 Акции — #stocks\n"
        "📈 Рынок — #market\n"
        "🏦 ETF — #etf\n"
        "🧠 Аналитика — #analysis\n\n"

        "🔗 Внешние ресурсы:\n"
        "• Yahoo Finance — https://finance.yahoo.com\n"
        "• Seeking Alpha — https://seekingalpha.com\n\n"

        "Нажмите на хештег для навигации 👇"
    )


# ==============================
# STARTUPS & VC
# ==============================

def build_startups_vc_navigation(job=None):
    return (
        "📌 Навигация по каналу «Startups & VC»\n\n"

        "🚀 Стартапы — #startup\n"
        "💼 Венчур — #vc\n"
        "📉 Питчи — #pitch\n"
        "🧠 Кейсы — #cases\n\n"

        "🔗 Внешние ресурсы:\n"
        "• Y Combinator — https://ycombinator.com\n"
        "• Crunchbase — https://crunchbase.com\n\n"

        "Нажмите на хештег для просмотра 👇"
    )


# ==============================
# PRODUCT GROWTH
# ==============================

def build_product_growth_navigation(job=None):
    return (
        "📌 Навигация по каналу «Product Growth»\n\n"

        "📈 Рост — #growth\n"
        "🧪 Эксперименты — #experiments\n"
        "📊 Метрики — #metrics\n"
        "🎯 UX — #ux\n\n"

        "🔗 Внешние ресурсы:\n"
        "• Reforge — https://reforge.com\n"
        "• GrowthHackers — https://growthhackers.com\n\n"

        "Нажмите на хештег для навигации 👇"
    )


# ==============================
# PROGRAMMING & DEV
# ==============================

def build_programming_dev_navigation(job=None):
    return (
        "📌 Навигация по каналу «Programming & Dev»\n\n"

        "👨‍💻 Код — #programming\n"
        "⚙️ Backend — #backend\n"
        "🎨 Frontend — #frontend\n"
        "🧠 Архитектура — #architecture\n\n"

        "🔗 Внешние ресурсы:\n"
        "• GitHub — https://github.com\n"
        "• Stack Overflow — https://stackoverflow.com\n"
        "• Dev.to — https://dev.to\n\n"

        "Нажмите на хештег для просмотра 👇"
    )
