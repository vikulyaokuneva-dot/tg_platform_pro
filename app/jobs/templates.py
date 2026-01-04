def build_simple_post(job):
    prefix = job.get("prefix", "")
    source = job.get("source", "")
    return f"{prefix}{source}"

def with_hashtags(text: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{tag}" for tag in hashtags)
    return f"{text}\n\n{tags}"

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
from app.sources import memes, programming, bugs, startups, dev_thoughts

def build_it_humor_post(job):
    source = job["source"]

    if source == "memes":
        text = memes.get_post()
        tags = ["it", "memes", "юмор"]

    elif source == "programming":
        text = programming.get_post()
        tags = ["dev", "programming", "код"]

    elif source == "bugs":
        text = bugs.get_post()
        tags = ["bugs", "fail", "debug"]

    elif source == "startups":
        text = startups.get_post()
        tags = ["startup", "itlife"]

    elif source == "thoughts":
        text = dev_thoughts.get_post()
        tags = ["devlife", "айти"]

    else:
        return None

    return with_hashtags(text, tags)

