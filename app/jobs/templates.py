def build_simple_post(job):
    prefix = job.get("prefix", "")
    source = job.get("source", "")
    return f"{prefix}{source}"


def build_it_humor_navigation(job):
    return (
        "📌 Навигация по каналу «IT юмор»\n\n"

        "😂 Мемы и шутки — #itюмор #мемы\n"
        "💻 Программирование — #код #programming\n"
        "🧠 Мысли разработчика — #dev #айти\n"
        "🐞 Баги и фейлы — #bugs\n"
        "🚀 Стартапы и IT-жизнь — #startup #itlife\n\n"

        "🔗 Полезные ресурсы:\n"
        "• GitHub — https://github.com\n"
        "• Stack Overflow — https://stackoverflow.com\n"
        "• Habr — https://habr.com\n\n"

        "Нажмите на нужный хештег, чтобы увидеть все посты по теме 👇"
    )

