# -*- coding: utf-8 -*-
"""case_pipeline.news — «Новость дня» (отдельная контент-линия поверх ядра).

NEWS_SOURCE_URL (csv, config) → discovery ссылок раздела → fetch/extract (общий)
→ relevance/ad/age/dedup гейты → GigaChat Lite структурированный JSON
{headline_ru, summary_ru, company, facts[]} → evidence (facts ⊆ source,
числа ⊆ source) → Russian Language Guard → короткий пост (2–3 предложения)
→ claim → Telegram.

Безопасность: выдуманные цифры/факты невозможны (валидация по исходнику);
недостаточные доказательства => review; ошибка линии НЕ ломает case-pipeline
(вызывающий изолирует try/except, здесь тоже не бросаем наружу).
"""
import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import ai, config, extraction, hashtags, httpclient, langguard, telegram
from .utils import content_hash, digits_of, domain, extract_numbers, norm_num_text, norm_url, ws_norm

log = logging.getLogger("case_pipeline.news")

RELEVANCE_RX = re.compile(
    r"искусственн|\bии\b|нейросет|нейрон|\bai\b|\bml\b|автоматизац|чат-?бот|робот"
    r"|\bgpt\b|\bllm\b|gigachat|агент\w*|машинн\w*|модел\w*|обучени[ея] модел"
    r"|algorithm|automation|\bneural\b|artificial intelligence", re.I)
ADS_RX = re.compile(r"купить|промокод|% скид|заказать курс|бесплатн\w* вебинар"
                    r"|подпишись|реклама\.*:|скидка \d+%", re.I)

NEWS_SYSTEM = (
    "Ты — редактор русскоязычного Telegram-канала про AI и автоматизацию в бизнесе.\n"
    "По данной НОВОСТИ верни СТРОГО JSON без пояснений:\n"
    '{"headline_ru":"заголовок до 8 слов на русском",'
    '"summary_ru":"2-3 предложения на русском: что произошло; почему важно для '
    'бизнеса/автоматизации; при необходимости короткий практический вывод",'
    '"company":"компания/организация или пусто",'
    '"facts":["точная копия фрагмента текста новости, 40-120 символов, без "'
    'кавычек целиком, без многоточий и обрывов на середине слова"]}\n'
    "ЗАПРЕЩЕНО: любые числа/имена/факты, которых нет в тексте новости; оценки; "
    "кликбейт; дополнительные предложения. Если язык новости английский — "
    "summary_ru пиши по-русски, facts оставь дословно на языке источника."
)

MAX_POST_CHARS = 1200


def _sent_count(t):
    return len(re.findall(r"[.!?…]", t or ""))


def discover(source_url):
    """Ссылки новостей со страницы раздела (универсический эвристический
    парсер; для специфичного сайта можно добавить минимальный adapter)."""
    try:
        _, html = httpclient.fetch(source_url, timeout=45)
    except httpclient.FetchError as e:
        log.warning("news discover %s failed: %s", source_url, e)
        return []
    host = domain(source_url)
    out, seen = [], set()
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    for a in soup.find_all("a", href=True):
        href = urljoin(source_url, a["href"])
        if domain(href) != host:
            continue
        if re.search(r"/(tags?|categories?|authors?|specials|hub|search|login"
                     r"|logout|people|promo|premium|marketing)(/|$|\?)", href, re.I):
            continue
        if not re.search(r"news|article|story|/\d{4}[-/]\d{1,2}", href, re.I):
            continue
        anchor = a.get_text(" ", strip=True)
        if len(anchor) < 20:
            continue
        cu = norm_url(href)
        if cu and cu not in seen:
            seen.add(cu)
            out.append(href)
    return out


def validate_news(v, source_text):
    """Детерминированная проверка AI-сводки: структура, цитаты, числа, объём."""
    if not isinstance(v, dict):
        return ["no json"]
    errs = []
    head = (v.get("headline_ru") or "").strip()
    summ = (v.get("summary_ru") or "").strip()
    if not head or len(head) > 90:
        errs.append("bad headline")
    if not summ or len(summ) > 600:
        errs.append("bad summary")
    elif not (2 <= _sent_count(summ) <= 4):
        errs.append("summary must be 2-3 sentences, got %d" % _sent_count(summ))
    src = ws_norm(source_text)
    facts = v.get("facts")
    if not isinstance(facts, list) or not facts:
        errs.append("no facts")
    else:
        for f in facts[:3]:
            wf = ws_norm(str(f))
            # допуск: AI может обрезать цитату — проверяем дословное вхождение
            # или дословный префикс не короче 30 символов
            if wf in src or (len(wf) >= 30 and wf[:30] in src):
                continue
            errs.append("fact not in source: %r" % str(f)[:40])
    src_norm = norm_num_text(ws_norm(source_text))
    src_nums = extract_numbers(src_norm)
    post_nums = extract_numbers(norm_num_text(ws_norm(head + " " + summ)))
    src_cores = {digits_of(n) for n in src_nums if digits_of(n)}
    invented = [n for n in post_nums if n not in src_nums
                and re.sub(r"[^\d.,]", "", n) not in src_norm
                and digits_of(n) not in src_cores]
    invented = [n for n in invented if re.search(r"\d", n) and n not in {"1", "2", "3"}]
    if invented:
        errs.append("numbers not in source: %s" % invented[:4])
    return errs


def _process_one(storage, art, url, provider, publish):
    try:
        _, html = httpclient.fetch(url)
    except httpclient.FetchError as e:
        log.info("news fetch skip %s: %s", url, e)
        return None
    mid = storage.add(url, "news")
    ext = extraction.extract_from_html(html, url)
    text, title = ext["text"], ext["title"]
    h = content_hash(text)

    def finish(status, reason="", **fields):
        fields.update(status=status, reason=reason[:300])
        storage.update(mid, **fields)
        return {"url": url, "source": "news", "status": status, "reason": reason}

    if ext["quality"] in ("failed", "poor") or len(text) < config.NEWS_MIN_CHARS:
        return finish("rejected", "news: text too short (%d)" % len(text),
                      content_hash=h)
    blob = ws_norm(title + " " + text[:3000])
    if not RELEVANCE_RX.search(blob):
        return finish("rejected", "news: not AI/automation related", content_hash=h)
    if ADS_RX.search(ws_norm(title)):
        return finish("rejected", "news: advertising", content_hash=h)
    pub = (ext.get("published_at") or "")[:10]
    try:
        d = datetime.strptime(pub, "%Y-%m-%d")
        if (datetime.utcnow() - d).days > config.NEWS_MAX_AGE_DAYS:
            return finish("rejected", "news: too old (%s)" % pub, content_hash=h)
    except ValueError:
        pass  # дата не распознана — не блокируем
    if storage.content_duplicated(text, exclude_id=mid):
        return finish("rejected", "news: duplicate content", content_hash=h)
    news_id = "news-" + hashlib.sha256((norm_url(url) + h).encode()).hexdigest()[:12]
    if storage.case_published(news_id):
        return finish("rejected", "news: already published", content_hash=h)
    storage.update(mid, status="classified", classification="news", content_hash=h)

    if not provider.available:
        return finish("review", "news without AI provider (Lite required)")

    raw = provider.complete([
        {"role": "system", "content": NEWS_SYSTEM},
        {"role": "user", "content": "ЗАГОЛОВОК: %s\nURL: %s\n\nТЕКСТ НОВОСТИ:\n%s"
         % (title[:200], url, text[:6000])}])
    v = ai._extract_json(raw)
    # заголовок — тоже данные источника (факты могут дословно быть в нём)
    errs = validate_news(v, title + "\n" + text)
    if errs:
        return finish("review", "news validation: %s" % "; ".join(errs[:2]))

    company = (v.get("company") or "").strip()[:60]
    tags = hashtags.build("news", ws_norm(title + " " + v["summary_ru"]),
                          company or None)
    post = ("📰 НОВОСТЬ ДНЯ\n%s\n\n%s\n\n🔗 %s\n%s" % (
        v["headline_ru"].strip(), v["summary_ru"].strip(), url, hashtags.render(tags)))
    if len(post) > MAX_POST_CHARS:
        return finish("review", "news too long (%d)" % len(post))
    final, lang_ok, note = langguard.ensure_russian(post, provider)
    if not lang_ok:
        return finish("review", "language guard: %s" % note[:200])

    news_json = {"case_id": news_id, "headline": v["headline_ru"],
                 "summary": v["summary_ru"], "facts": v["facts"],
                 "company": company, "source_url": url,
                 "published_at_src": ext.get("published_at") or ""}
    storage.update(mid, status="post_ready", post_text=final, company=company,
                   case_json=json.dumps(news_json, ensure_ascii=False))
    art.write_json("news_%s.json" % news_id, news_json)
    row = {"url": url, "source": "news", "status": "post_ready", "news_id": news_id,
           "hashtags": tags, "company": company}
    if publish:
        if not storage.claim_for_publish(mid):
            row.update(status="post_ready", reason="claim lost (parallel run)")
            return row
        res = telegram.publish_post(final, dry_run=False)
        if res.ok:
            storage.mark_published(mid, res.message_id, config.CHAT_ID, news_id,
                                   hashtags=hashtags.render(tags), content_type="news")
            row.update(status="published", telegram_message_id=res.message_id)
        else:
            storage.release_claim(mid, "review", "publish failed: %s" % (res.error or ""))
            row.update(status="review", reason="publish failed: %s" % res.error)
    return row


def process_news(storage, art, provider, publish=False):
    """Одна новость за запуск. Сначала — уже готовые post_ready новости из БД,
    затем discovery по настроенным источникам. -> row|None.
    Наружу исключения не бросаем (failure isolation)."""
    for m in storage.by_status("post_ready"):
        if (m.get("source") or "") != "news":
            continue
        try:
            nj = json.loads(m.get("case_json") or "{}")
        except Exception:
            nj = {}
        news_id = nj.get("case_id") or ""
        tags = hashtags.build("news", m.get("post_text") or "", m.get("company"))
        row = {"url": m["url"], "source": "news", "news_id": news_id,
               "hashtags": tags, "company": m.get("company") or ""}
        if not publish:
            row.update(status="post_ready", reason="ready news in DB")
            return row
        if storage.case_published(news_id) or not storage.claim_for_publish(m["id"]):
            continue
        res = telegram.publish_post(m["post_text"], dry_run=False)
        if res.ok:
            storage.mark_published(m["id"], res.message_id, config.CHAT_ID, news_id,
                                   hashtags=hashtags.render(tags), content_type="news")
            row.update(status="published", telegram_message_id=res.message_id)
        else:
            storage.release_claim(m["id"], "review", "publish failed: %s" % (res.error or ""))
            row.update(status="review", reason="publish failed: %s" % res.error)
        return row

    for src in config.NEWS_SOURCES:
        for url in discover(src)[:10]:
            known = storage.seen_url(url)
            if known and known["status"] != "failed":
                continue  # уже обработанная новость не пережёвывается
            try:
                row = _process_one(storage, art, url, provider, publish)
            except Exception as e:
                log.warning("news item failed (isolated) %s: %s", url, e)
                continue
            if row is not None:
                return row
    return None
