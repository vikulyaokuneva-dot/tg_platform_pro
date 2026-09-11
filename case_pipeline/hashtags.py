# -*- coding: utf-8 -*-
"""case_pipeline.hashtags — контролируемый словарь хэштегов канала.

AI/пайплайн НЕ порождает свободные теги: пост получает ровно
1 TYPE + 1–2 DOMAIN + 1 COMPANY (+1 OWN PROJECT при явном указании) = 3–5.
Все теги валидны (без мусора), сохраняются в publication history.
"""
import re

TYPE_TAGS = {"case": "#Кейс", "news": "#НовостьДня", "analysis": "#Разбор"}

# DOMAIN: (тег, regex по тексту кейса/новости). Порядок = приоритет.
DOMAIN_RULES = [
    ("#CRM",        r"\bcrm\b|salesforce|битрикс|amo\b|мегаплан|карточк[аи] клиент"),
    ("#Маркетинг",  r"реклам|маркетинг|кампани|трафик|конверси|рассылк|sms|email-|лидогенера|seo|smm|retarget|соцсет|промо"),
    ("#Продажи",    r"продаж|sales|заявк|сделк|воронк|выручк|revenue|квот|переговор|скидк|ставк"),
    ("#Клиенты",    r"клиент|support|поддержк|helpdesk|ticket|обращени|onboard|удержани|nps|чат-?бот|сервис"),
    ("#Документы",  r"документ|отч[ёе]т|report|invoice|счет|счёт|акт|договор|согласов|бухгалтер|1с\b"),
    ("#HR",         r"\bhr\b|персонал|найм|рекрут|кадр|сотрудник|кандидат|собеседован"
                    r"|обучение персонал"),
    ("#Производство", r"производств|завод|станок|предприяти|выпуск|maintenance|качество"),
    ("#Логистика",  r"логистик|доставк|склад|курьер|маршрут|груз|supply chain|поставок"),
    ("#Финансы",    r"финанс|платеж|платёж|оплат|банк|fraud|мошен|кредит|страхов|budget|бюджет"),
    ("#Аналитика",  r"аналитик|дашборд|прогноз|метрик|\bbi\b|data science|предиктив"),
    ("#Ecommerce",  r"e-?commerce|интернет-магазин|маркетплейс|корзин|заказ|ozon|wildberries"),
]
DOMAIN_FALLBACK = "#Автоматизация"

# Компании: канонические теги (добавляются в словарь, а не генерируются свободно)
KNOWN_COMPANIES = {
    "openai": "#OpenAI", "microsoft": "#Microsoft", "google": "#Google",
    "salesforce": "#Salesforce", "ibm": "#IBM", "mindbox": "#Mindbox",
    "zapier": "#Zapier", "sber": "#Сбер", "сбер": "#Сбер", "сбербанк": "#Сбер",
    "yandex": "#Яндекс", "яндекс": "#Яндекс", "ozon": "#Ozon", "озон": "#Ozon",
    "wildberries": "#Wildberries", "avito": "#Авито", "авито": "#Авито",
    "tinkoff": "#ТБанк", "т-банк": "#ТБанк", "вкусвилл": "#ВкусВилл",
    "vkusvill": "#ВкусВилл", "petrovich": "#Петрович", "петрович": "#Петрович",
    "m video": "#МВидео", "м-видео": "#МВидео", "mvideo": "#МВидео",
    "leroy": "#LeroyMerlin", "лемер": "#LeroyMerlin",
    "chitai": "#ЧитайГород", "читай": "#ЧитайГород",
    "nike": "#Nike", "ikea": "#IKEA", "tesla": "#Tesla", "boeing": "#Boeing",
    "mercadolibre": "#MercadoLibre", "mercari": "#Mercari", "vendavo": "#Vendavo",
    "accenture": "#Accenture", "cvs": "#CVSHealth", "crocs": "#Crocs",
    "trivago": "#Trivago", "sixt": "#SIXT", "skechers": "#Skechers",
    "synthesia": "#Synthesia", "finntrail": "#Finntrail", "bioivt": "#Bioivera",
}

# Собственные проекты канала (публикуются серией «Создаём ИИ Директора ВБ» и т.п.,
# НЕ как чужие кейсы; в навигации показываются всегда).
OWN_PROJECTS = ("#AIDirectorWB", "#ShawarmaLab", "#AIКонсультант")

TAG_RX = re.compile(r"^#[A-Za-zА-Яа-яЁё0-9_]{2,25}$")
MAX_TAGS = 5


def company_tag(name):
    """Санитизация компании в тег. Только словарь или чистое имя без мусора."""
    if not name:
        return None
    low = name.strip().lower()
    for key, tag in KNOWN_COMPANIES.items():
        if key in low:
            return tag
    clean = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]", "", name)
    if not clean or len(clean) < 2 or len(clean) > 25:
        return None
    if re.fullmatch(r"(?i)(the|company|corp|inc|llc|оао|ооо|зао|пАО)", clean):
        return None
    tag = "#" + clean
    return tag if TAG_RX.match(tag) else None


def detect_domains(blob, limit=2):
    hits = [tag for tag, rx in DOMAIN_RULES if re.search(rx, blob, re.I)]
    return hits[:limit]


def build(content_type="case", text_blob="", company=None, own=None):
    """-> list[str] 3–5 контролируемых тегов."""
    tags = [TYPE_TAGS.get(content_type, TYPE_TAGS["case"])]
    doms = detect_domains(text_blob or "")
    if not doms:
        doms = [DOMAIN_FALLBACK]
    tags += doms[:2]
    ct = company_tag(company)
    if ct and ct not in tags:
        tags.append(ct)
    if own:
        ot = own if own in OWN_PROJECTS else None
        if ot and ot not in tags:
            tags.append(ot)
    # минимальный смысл: TYPE + DOMAIN + (COMPANY или вторая DOMAIN)
    if len(tags) < 3 and DOMAIN_FALLBACK not in tags:
        tags.append(DOMAIN_FALLBACK)
    return tags[:MAX_TAGS]


def render(tags):
    return " ".join(tags)


def apply_to_post(text, tags):
    """Заменяет хвостовую хэштег-строку поста на контролируемую (гарантия:
    сколько бы тегов ни сгенерировал AI — в канал уйдут только словарные)."""
    line = render(tags)
    body = re.sub(r"(?m)^#[^\n]*$", "", text or "").rstrip()
    return body + "\n" + line


def validate(tags):
    """Проверка списка тегов для тестов/гейтов. -> (ok, errors)."""
    errors = []
    if not 3 <= len(tags) <= MAX_TAGS:
        errors.append("tag count %d not in 3..%d" % (len(tags), MAX_TAGS))
    allowed = set(TYPE_TAGS.values()) | {t for t, _ in DOMAIN_RULES} \
        | set(KNOWN_COMPANIES.values()) | set(OWN_PROJECTS) | {DOMAIN_FALLBACK}
    for t in tags:
        if t in allowed:
            continue
        if TAG_RX.match(t or "") and company_tag(t[1:]) == t:
            continue  # чистое имя компании (санитизированный тег)
        errors.append("tag not in controlled dictionary: %r" % t)
    if len(set(tags)) != len(tags):
        errors.append("duplicate tags")
    return (not errors), errors
