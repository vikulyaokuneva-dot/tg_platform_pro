# -*- coding: utf-8 -*-
"""case_pipeline.navigation — генератор навигационного сообщения канала.

ВАЖНО: только ГЕНЕРИРУЕТ текст (пишет data/navigation.txt и runs/.../navigation.txt).
Ничего не отправляет в Telegram, pinned-сообщения НЕ трогает — пользователь
проверяет результат и закрепляет вручную.
"""
import io
import logging
import os
from collections import Counter

from . import config, hashtags

log = logging.getLogger("case_pipeline.navigation")


def collect(storage):
    rows = storage.db.execute(
        "SELECT hashtags, content_type, company FROM publications WHERE ok=1").fetchall()
    cnt = Counter()
    n_case = n_news = 0
    for r in rows:
        if (r["content_type"] or "case") == "news":
            n_news += 1
        else:
            n_case += 1
        for t in (r["hashtags"] or "").split():
            cnt[t] += 1
    return cnt, n_case, n_news


def build_text(storage):
    cnt, n_case, n_news = collect(storage)
    type_dom_own = (set(hashtags.TYPE_TAGS.values())
                    | {t for t, _ in hashtags.DOMAIN_RULES} | {hashtags.DOMAIN_FALLBACK}
                    | set(hashtags.OWN_PROJECTS))
    domains = [(t, c) for t, c in cnt.most_common() if t in {d for d, _ in hashtags.DOMAIN_RULES}
               or t == hashtags.DOMAIN_FALLBACK]
    companies = [(t, c) for t, c in cnt.most_common() if t not in type_dom_own]

    L = ["🧭 НАВИГАЦИЯ ПО КАНАЛУ «AI Автоматизация | Бизнес»", ""]
    L.append("📌 Кейсы автоматизации (%d)" % n_case)
    L.append(hashtags.TYPE_TAGS["case"])
    L.append("")
    L.append("📰 Новости дня (%d)" % n_news)
    L.append(hashtags.TYPE_TAGS["news"])
    L.append("")
    if domains:
        L.append("💼 Направления:")
        L.append(" ".join("%s(%d)" % (t, c) for t, c in domains[:12]))
        L.append("")
    if companies:
        L.append("🏢 Компании:")
        L.append(" ".join("%s(%d)" % (t, c) for t, c in companies[:20]))
        L.append("")
    L.append("🚀 Наши проекты:")
    L.append(" ".join(hashtags.OWN_PROJECTS))
    L.append("")
    L.append("Ищите нужное по хэштегам — они у каждого поста.")
    return "\n".join(L)


def rebuild(storage, runs_dir=None):
    """Сгенерировать навигацию, сохранить в data/navigation.txt (и в runs,
    если задан каталог). Возвращает текст. Telegram НЕ трогает."""
    text = build_text(storage)
    out = os.path.join(os.path.dirname(config.DB_PATH), "navigation.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(text)
    if runs_dir:
        with io.open(os.path.join(runs_dir, "navigation.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    log.info("navigation rebuilt -> %s", out)
    return text
