# -*- coding: utf-8 -*-
"""case_pipeline.langguard — Russian Language Guard.

Финальный пост канала должен быть на русском. Допустимы: бренды, названия
продуктов, аббревиатуры (CRM/AI/SaaS...), URL, хэштеги — на латинице.
Недопустимо: доминирующий английский текст.

guard(text) -> (ok, reason)
ensure_russian(text, provider) -> (final_text, ok, note)
  FAIL -> один retry через GigaChat (перевод с сохранением чисел/брендов/URL);
  повторный FAIL -> ok=False (вызывающий отправляет материал в review).
Retry безопасен: новые числа запрещены (подмножество чисел исходного поста,
а тот уже прошёл numbers-in-source гейт).
"""
import logging
import re

from .utils import digits_of, extract_numbers, norm_num_text, ws_norm

log = logging.getLogger("case_pipeline.langguard")

CY_RX = re.compile(r"[а-яёА-ЯЁ]")
LAT_WORD_RX = re.compile(r"[A-Za-z][A-Za-z0-9&.'\-]*")
URL_RX = re.compile(r"https?://\S+|www\.\S+", re.I)

# Латинские токены, которые НЕ считаем «английским текстом»: бренды, продукты,
# тех-аббревиатуры, домены. Расширяется словарём hashtags.KNOWN_LATIN.
BASE_OK = {
    "ai", "ml", "llm", "gpt", "chatgpt", "api", "crm", "erp", "saas", "b2b",
    "b2c", "seo", "smm", "ux", "ui", "it", "bi", "kpi", "roi", "nps", "sms",
    "mms", "push", "slack", "notion", "jira", "github", "gitlab", "zoom",
    "telegram", "whatsapp", "instagram", "facebook", "tiktok", "youtube",
    "google", "microsoft", "amazon", "apple", "ibm", "intel", "nvidia",
    "salesforce", "sap", "oracle", "adobe", "tableau", "power", "excel",
    "mindbox", "zapier", "make", "airtable", "monday", "trello", "asana",
    "hubspot", "shopify", "woocommerce", "bitrix24", "yandex", "sber",
    "sberbank", "ozon", "wildberries", "avito", "tinkoff", "alfa",
    "openai", "anthropic", "claude", "gemini", "copilot", "agentforce",
    "gigachat", "giga", "chat", "bot", "bots", "app", "apps", "web",
    "data", "cloud", "one", "two", "pro", "max", "plus", "team", "enterprise",
    "net", "com", "org", "ru", "io", "www", "http", "https",
}

# Порог: доля кириллических слов. 0.6 = нормальный RU-текст с вкраплениями
# брендов проходит; текст, где английский доминирует, — нет.
RU_RATIO_PASS = 0.6


def allowed_latin_extra(tokens):
    """Разрешить дополнительные латинские токены (бренды из словаря хэштегов)."""
    BASE_OK.update(t.lower() for t in tokens)


def guard(text):
    t = text or ""
    if not t.strip():
        return False, "empty text"
    body = URL_RX.sub(" ", t)
    body = re.sub(r"#[\wА-Яа-яЁё]+", " ", body)          # хэштеги
    body = re.sub(r"\b\d[\d.,\s%±x]*\b", " ", body)       # числа/проценты
    words = [w for w in LAT_WORD_RX.findall(body)]
    lat_words = [w for w in words if w.lower().strip(".-'&") not in BASE_OK]
    cy_words = len(re.findall(r"[а-яёА-ЯЁ]{2,}", body))   # реальные RU-слова
    lat_n = len(lat_words)
    if cy_words == 0 and lat_n == 0:
        return False, "no words"
    ratio = cy_words / float(cy_words + lat_n)
    if ratio >= RU_RATIO_PASS:
        return True, "ru_ratio=%.2f" % ratio
    return False, "english-dominant (ru_ratio=%.2f, latin=%s)" % (
        ratio, [w.lower() for w in lat_words[:8]])


TRANSLATE_SYSTEM = (
    "Ты — редактор русскоязычного Telegram-канала. Переведи/перепиши данный пост "
    "НА РУССКИЙ ЯЗЫК. ОБЯЗАТЕЛЬНО сохрани: все числа и проценты без изменений, "
    "названия компаний и продуктов, URL источника, хэштеги, структуру и эмодзи. "
    "ЗАПРЕЩЕНО добавлять новые факты, цифры или усиливать формулировки. "
    "Верни только готовый текст поста, без пояснений."
)


def ensure_russian(text, provider):
    """-> (final_text, ok, note). Один retry при FAIL (если провайдер живой)."""
    ok, why = guard(text)
    if ok:
        return text, True, "pass: %s" % why
    if provider is None or not getattr(provider, "available", False) \
            or not hasattr(provider, "complete"):
        return text, False, why
    try:
        retry = (provider.complete([{"role": "system", "content": TRANSLATE_SYSTEM},
                                    {"role": "user", "content": text[:3800]}]) or "").strip()
    except Exception as e:
        return text, False, "%s (retry error: %s)" % (why, type(e).__name__)
    if not retry or len(retry) < 100:
        return text, False, why + " | retry empty"
    ok2, why2 = guard(retry)
    old_nums = extract_numbers(norm_num_text(ws_norm(text)))
    new_nums = extract_numbers(norm_num_text(ws_norm(retry)))
    old_d = {digits_of(n) for n in old_nums if digits_of(n)}
    # сравнение по цифровой последовательности: формат чисел при переводе
    # меняется ("2,000" -> "2 000"), сами числа — нет
    invented = [n for n in sorted(new_nums)
                if n not in old_nums and digits_of(n) and digits_of(n) not in old_d]
    if ok2 and not invented:
        return retry, True, "retry_pass: %s" % why2
    note = why2 if not ok2 else "retry invented numbers: %s" % invented[:4]
    log.info("language guard retry failed: %s", note)
    return text, False, note
