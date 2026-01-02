def build_simple_post(job):
    prefix = job.get("prefix", "")
    source = job.get("source", "")
    return f"{prefix}{source}"


def build_it_humor_navigation(job):
    return (
        "📌 Навигация\n\n"
        "😂 IT Юмор | Dev Life\n"
        "Лучшие шутки и мемы про программистов\n\n"
        "🕒 Частота\n"
        "3–5 постов в день\n\n"
        "🧠 Темы\n"
        "• программирование\n"
        "• баги и фиксы\n"
        "• дедлайны\n"
        "• работа в IT\n\n"
        "📩 Связь / реклама\n"
        "@your_username\n\n"
        "🔗 Другие проекты\n"
        "@crypto_news_channel\n"
        "@ai_automation_channel"
    )
