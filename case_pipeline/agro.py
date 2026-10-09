# -*- coding: utf-8 -*-
"""case_pipeline.agro — второй канал (jobs/agro): агро-практика.

Линия контента над общим ядром — структурный аналог news.py (у платформы уже
есть прецедент lanes: case-пайплайн + «Новости дня»). Ядро и production-канал
НЕ изменены: discovery — обычные SourceAdapter (RSS подклассы), fetch/extract —
httpclient/extraction, публикация — telegram(channel='agro'), дедуп/история —
тот же storage, но отдельный файл БД (config.AGRO_DB_PATH).

Почему не case_model/postgen: у агро-статей (вырастить/обработать/укрыть) нет
корпоративных problem/implementation/results — натягивать их на модель бизнес-
кейсов означало бы ломать гейты E/F и frozen-классификатор.

ИИ-редактура (следующий этап из старого отчёта — реализован): ПОЛНЫЙ текст
статьи проходит через СУЩЕСТВУЮЩИЙ GigaChatProvider (case_pipeline.ai, того же
провайдера использует AI-канал; второго клиента НЕТ): выбрать 5-7 полезных
советов, сохранить числа/условия, убрать повторы/SEO, короткий заголовок,
вывод, уместные эмодзи (AI_EDIT_SYSTEM). Контракт валидируется
(_edit_contract_ok), при неудаче после повтора — review, сырой текст НЕ
публикуется. Без
провайдера (нет GIGACHAT_API_KEY, напр. в CI) — прежний extractive-макет.
Публикация — двумя сообщениями: фото с короткой подписью + полный текст
(telegram.publish_post с image), чтобы длинный пост не обрезался на caption.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from . import (adapters, ai as ai_mod, case_model, classifier_agro, config,
               extraction, hashtags, httpclient, langguard,
               storage as storage_mod, telegram, textclean, utils)

log = logging.getLogger("case.agro")

SOURCE_LABELS = {"botanichka": "Ботаничка", "agroinvestor": "Агроинвестор",
                 "gismeteo": "Gismeteo", "aif": "АиФ Дача",
                 "supersadovnik": "Суперсадовник", "ogorodnik": "Огородник",
                 "7dach": "7dach"}
# Контролируемый словарь рубрик — из classifier_agro.TOPICS (единый источник).
AGRO_DOMAIN_RULES = [(tag, rx) for _, _, tag, rx in classifier_agro.TOPICS]
AGRO_FALLBACK_DOMAIN = "#Агро"
AGRO_ALLOWED_TAGS = {t for _, _, t, _ in classifier_agro.TOPICS} | {AGRO_FALLBACK_DOMAIN}

# тоньше 300 символов содержательный пост не бывает (лойальность к коротким,
# но полезным инструкциям); ~20-символьные заглушки по-прежнему отсекаются
MIN_BODY_CHARS = 300
MAX_BODY_CHARS = 750          # extractive-fallback: 2 абзаца-потолка
# Потолок всего поста: полный текст уходит отдельным сообщением Telegram
# (4096 с учётом экранирования MarkdownV2), поэтому лимит снят с 1800 до
# 3400 — ИИ-пост на 5-7 советов + вывод спокойно помещается, обрезка не нужна
MAX_POST_CHARS = 3400

# Содержательная полнота (гейт против «вступление вместо поста» — дефект
# msg80/81: длина/структура в порядке, а рекомендаций и вывода нет).
# 1) позиционный гейт: доля слов поста, впервые встречающихся во второй
#    половине исходника. Вырезка начала статьи даёт ~0.02; полноценный пост,
#    отражающий рекомендации/итоги, — существенно выше порога.
#    matched < COMP_MIN_MATCHED (пост сильно перефразирован) — проверка
#    неинформативна и пропускается, её страхует гейт секций.
COMP_MIN_MATCHED = 10
COMP_MIN_TAIL_SHARE = 0.10
# 2) гейт секций: заголовки H2/H3 статьи, найденные в её тексте; пост должен
#    отражать большинство секций (≥2 ключевых слова на секцию). Материал без
#    структуры (секций <3) — проверка не применяется.
COMP_MIN_SECTION_COVER = 0.50
_HEADING_RX = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.I | re.S)
_TAG_RX = re.compile(r"<[^>]+>")
_KW_RX = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё-]{4,}")
# слова-связки в заголовках секций (не несут темы); сравниваются стемами
_SEC_STOP = {"какой", "какие", "каких", "почему", "можно", "нужно", "очень",
             "также", "является", "которые", "который", "перед", "после",
             "этого", "этих"}
_SEC_STOP_STEMS = {w[:5] for w in _SEC_STOP}

_SKIP_PAR_RX = re.compile(r"^(фото|видео|читайте также|подписк|реклама|похожие "
                          r"материалы|источник:)", re.I)


def _age_ok(published_at):
    """Окно свежести по дате статьи (JSON-LD/OG). Дату не распарсили — не
    блокируем (агрегаторы врут в метаданных чаще, чем публикуют старьё)."""
    if not published_at:
        return True
    s = str(published_at).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s[:25])
    except ValueError:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if not m:
            return True
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=config.AGRO_MAX_AGE_DAYS)


def _cut_sentences(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    m = list(re.finditer(r"[.!?…]", cut))
    return cut[:m[-1].end()].strip() if m else cut.rsplit(" ", 1)[0] + "…"


def _pick_paragraphs(text):
    """2 первых содержательных абзаца (дословно из текста источника),
    единый ограниченный блок — оборот на границе предложения."""
    parts, total = [], 0
    for p in re.split(r"\n\s*\n", text or ""):
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) < 120 or _SKIP_PAR_RX.match(p):
            continue
        parts.append(p)
        total += len(p)
        if total >= MAX_BODY_CHARS or len(parts) >= 2:
            break
    if not parts:  # сплошной текст без разбивки — первый «сверх-абзац»
        p = re.sub(r"\s+", " ", text or "").strip()
        if len(p) >= 120:
            parts = [p]
    joined = "\n\n".join(parts)
    return [_cut_sentences(joined, MAX_BODY_CHARS)] if joined else []


_IMG_SRC_RX = re.compile(r"<img[^>]+?src=[\"']([^\"']+)[\"']", re.I)
_IMG_BAD_RX = re.compile(r"logo|icon|sprite|avatar|banner|1x1|pixel|placeholder|"
                         r"blank|loading|\.svg(?:\?|$)", re.I)


def _norm_image(src, page_url):
    """Абсолютизация URL изображения: «//host/...» → https:, относительный
    путь — urljoin по странице. Не-http(s)/data: → '' (фиктивные URL не
    выдумываем — материал уйдёт в missing_image)."""
    src = (src or "").strip()
    if not src or src.lower().startswith("data:"):
        return ""
    if src.startswith("//"):
        src = "https:" + src
    elif not re.match(r"https?://", src):
        src = urljoin(page_url, src)
    return src if src.startswith("http") else ""


def _content_image(html, url):
    """Fallback изображения (контракт TEXT+IMAGE+SOURCE): ext['image']
    (JSON-LD/og) отсутствует — первый содержательный <img> статьи.
    Логотипы/иконки/трекеры отсекаем; фиктивные URL не выдумываем:
    если подходящего нет — пусто (материал уйдёт в missing_image)."""
    for m in _IMG_SRC_RX.finditer(html or ""):
        raw = (m.group(1) or "").strip()
        if not raw or _IMG_BAD_RX.search(raw):
            continue
        src = _norm_image(raw, url)
        if src:
            return src
    return ""


def build_post(title, text, url, source, verdict):
    """Extractive-макет агро-поста (не похож на WB-кейс: заголовок-польза,
    2 абзаца сути, ссылка, контролируемые рубрики)."""
    t = textclean.clean(title or "").strip().rstrip(".!?… ")
    # брендовый хвост заголовка источника («… — Ботаничка») убираем: канал
    # подписан тегом и строкой «Источник:», повтор бессмысленный
    t = re.split(r"\s+[—–]\s+[^—–]{2,30}$", t)[0].strip() or t
    if len(t) > 110:  # обрезка по границе слова, без многоточия/обрыва смысла
        t = t[:110].rsplit(" ", 1)[0].rstrip(",;:—– ")
    # рубрику в заголовок НЕ склеиваем («Технологии выращивания 10 шагов…» —
    # был виден брак публикации msg78): в первой строке только ведущий эмодзи
    # рубрики, имя рубрики живёт в хэштегах
    label = verdict["topics"][0][1] if verdict.get("topics") else ""
    lead = (label.split() or [""])[0]
    emoji = lead if lead and re.match(r"[^\w\s]", lead) else "🌱"
    blob = t + " " + (text or "")[:2500]
    tags = hashtags.build("agro", text_blob=blob, company=SOURCE_LABELS.get(source),
                          domain_rules=AGRO_DOMAIN_RULES,
                          fallback=AGRO_FALLBACK_DOMAIN)
    parts = ["%s %s" % (emoji, t)]
    parts += _pick_paragraphs(text)
    parts.append("Источник: %s" % url)
    parts.append(hashtags.render(tags))
    return "\n\n".join(parts), tags


def _strip_urls_and_tags(post):
    body = re.sub(r"https?://\S+", " ", post)
    body = re.sub(r"(?m)^#[^\n]*$", " ", body)
    return body


def _kw_keys(s):
    """Ключевые слова (≥5 символов) -> префиксы-стемы 5 символов: сглаживают
    разницу словоформ между заголовком секции и текстом поста."""
    return {w[:5] for w in _KW_RX.findall((s or "").lower())} - _SEC_STOP_STEMS


def _article_sections(html, text):
    """Заголовки H2/H3 самой статьи: берём только те, что найдены в
    извлечённом тексте (виджеты «читайте также» в текст статьи не входят —
    их заголовков в нём нет)."""
    if not html or not text:
        return []
    norm = utils.ws_norm(text).lower()
    out = []
    for raw in _HEADING_RX.findall(html):
        h = utils.ws_norm(_TAG_RX.sub(" ", raw))
        if 8 <= len(h) <= 90 and h.lower() in norm and h.lower() not in out:
            out.append(h.lower())
    return out[:12]


def _completeness_errors(post, source_text, html=None):
    """Содержательная полнота поста: он обязан опираться на рекомендации
    ВСЕГО материала, а не только на первые абзацы (регрессия msg80/81:
    extractive-вырезка вступления проходила все прежние гейты — длина,
    структура, числа, теги — и публиковалась без рекомендаций и вывода)."""
    errs = []
    src = utils.ws_norm(source_text or "").lower()
    body = utils.ws_norm(post or "").lower()
    if src and body:
        matched = after = 0
        for w in set(_KW_RX.findall(body)):
            i = src.find(w)
            if i < 0:
                continue
            matched += 1
            if i * 2 > len(src):
                after += 1
        if matched >= COMP_MIN_MATCHED:
            share = after / float(matched)
            if share < COMP_MIN_TAIL_SHARE:
                errs.append("incomplete: %d%% of words from article mid "
                            "(need >= %d%%)" % (round(share * 100),
                                                round(COMP_MIN_TAIL_SHARE * 100)))
    secs = _article_sections(html, source_text)
    if len(secs) >= 3 and body:
        # ключи — по ТЕЛУ поста без строки заголовка: заголовок может называть
        # секцию («нужно ли обрывать»), не отдавая её рекомендации — как в
        # дефектном msg81
        blocks = [b for b in (post or "").split("\n\n") if b.strip()]
        pkeys = _kw_keys("\n\n".join(blocks[1:]) if len(blocks) > 1 else post)
        hit = sum(1 for s in secs if len(_kw_keys(s) & pkeys) >= 2)
        if hit < len(secs) * COMP_MIN_SECTION_COVER:
            errs.append("incomplete: covers %d/%d article sections" %
                        (hit, len(secs)))
    return errs


def editorial_agro(post, source_text, html=None):
    """Редакционные гейты линии: артефакты, язык, числа ⊆ источника, теги —
    только словарь, объём, содержательная полнота (_completeness_errors).
    (Числа при extractive-посте гарантированы конструкцией — гейт проверяет
    регрессию, а не презумпцию.)"""
    errs = []
    if textclean.has_artifacts(post):
        errs.append("artifacts in post")
    ok, info = langguard.guard(post)
    if not ok:
        errs.append("langguard: %s" % info)
    src = utils.ws_norm(source_text or "")
    for m in re.finditer(r"\d[\d.,]{1,}", _strip_urls_and_tags(post)):
        if m.group() not in src:
            errs.append("number not in source: %s" % m.group())
            break
    if len(post) > MAX_POST_CHARS:
        errs.append("post too long: %d" % len(post))
    tags = post.rstrip().rsplit("\n", 1)[-1].split()
    tok, terr = hashtags.validate(tags, extra_allowed=AGRO_ALLOWED_TAGS)
    if not tok:
        errs.extend(terr)
    errs.extend(_completeness_errors(post, source_text, html))
    return errs


def _known_skip(row_status):
    return row_status in ("published", "post_ready", "review", "publishing")


# ---------- ИИ-редактура: ПОЛНЫЙ текст статьи через существующий GigaChatProvider

AI_EDIT_SYSTEM = (
    "Ты — редактор Telegram-канала «Сад без хлопот» (сад, огород, дача).\n"
    "Тебе даны заголовок, URL и ПОЛНЫЙ текст статьи. Изучай материал ЦЕЛИКОМ, "
    "а не только начало.\n"
    "Задача:\n"
    "1. Определи тему и главную пользу статьи для садовода.\n"
    "2. Найди в материале ключевые рекомендации и выбери 5-7 самых полезных "
    "практических советов. Все пункты исходника сохранять не обязательно — "
    "отбирай главное по пользе для садовода; если в источнике действительно "
    "важные последовательные шаги — сохрани их логику и порядок.\n"
    "3. Сохрани условия, ограничения и все числа из источника: НЕ придумывай "
    "советы, дозировки, сроки, температуры и результаты, которых нет в тексте.\n"
    "4. Убери повторы, длинные вступления, SEO-фразы и рекламные вставки; "
    "вступление (2-3 предложения) пиши один раз и не повторяй его внутри "
    "поста и в конце.\n"
    "5. Придумай короткий заголовок без кликбейта и сенсационности.\n"
    "6. Напиши законченную самостоятельную публикацию на естественном русском "
    "языке: после краткого вступления сразу практические рекомендации из "
    "исходника (пост обязан содержать основные советы статьи, а не только "
    "первые абзацы), добавь уместные тематические эмодзи (без эмодзи в "
    "каждом предложении), а в конце — конкретный вывод, что делать читателю.\n"
    "ФОРМАТ: первая строка — короткий заголовок обычным текстом (без "
    "приставок вроде «Тема:» и без маркера «•» в начале); "
    "затем пустая строка; краткое вступление (2-3 предложения); затем КАЖДЫЙ "
    "совет отдельным абзацем, в начале абзаца — «•»; советы НЕ нумеруй и НЕ "
    "собирай несколько советов в одну строку; в конце — отдельный абзац с "
    "выводом. Строку «Источник:» и хэштеги НЕ пиши — они добавляются "
    "автоматически. Длина до 3000 символов. Верни только текст поста, без "
    "markdown-обёрток и пояснений."
)


# ведущий маркер буллета («• …», «- …», «* …») — встречается и в заголовке,
# и внутри склеенных списков (дефект msg83: «Ключевые рекомендации:\n• a\n• b»)
_BULLET_LINE_RX = re.compile(r"^[•\-*–—]\s+")


def _clean_ai_output(raw):
    """Очистка вывода модели перед контрактной проверкой: markdown-фенсы,
    служебные строки «Источник:»/хэштегов (их дописывает _finalize_post —
    иначе будут дубли), жирные/решётки первой строки; маркер «•» в заголовке;
    однострочно-склеенные буллеты разбиваются в отдельные абзацы (иначе
    format_post склеит «• … • …» в одну стену текста)."""
    s = (raw or "").strip()
    s = re.sub(r"^```[A-Za-z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    lines = s.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    while lines:
        last = lines[-1].strip()
        if last and (re.match(r"^(?:\*\*)?Источник\b", last, re.I) or
                     re.fullmatch(r"(?:#\S+\s*)+", last)):
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
        else:
            break
    # буллеты, отделённые одним переносом строки: каждый начинает свой абзац
    split_lines = []
    for i, ln in enumerate(lines):
        if (i and _BULLET_LINE_RX.match(ln.strip())
                and split_lines and split_lines[-1].strip()):
            split_lines.append("")
        split_lines.append(ln)
    lines = split_lines
    if lines:
        head = lines[0].strip()
        head = re.sub(r"^\*\*(.+?)\*\*$", r"\1", head)
        head = re.sub(r"^#{1,6}\s*", "", head)
        # модель иногда пишет «Тема: …»/«Заголовок: …» — это не заголовок
        head = re.sub(r"^(?:Тема|Заголовок)\s*:\s*", "", head, flags=re.I)
        # заголовок-«пункт»: модель нередко оформляет первую строку буллетом
        head = re.sub(r"^[•\-*–—]{1,4}\s*", "", head)
        lines[0] = head
    return "\n".join(lines).strip()


def _edit_contract_ok(post, source_text=None, html=None):
    """Контракт ИИ-редактуры: непустой, первая строка — заголовок, есть
    структура «заголовок + абзацы», объём полноценного поста И
    содержательная полнота (пост опирается на рекомендации всего материала,
    а не только на вступление — _completeness_errors). Слишком длинный или
    неполный результат НЕ режем и НЕ публикуем как успех: он уходит на
    повтор, а затем в review с диагностикой причины."""
    if not post or not post.strip():
        return False, "empty result"
    blocks = [b for b in post.split("\n\n") if b.strip()]
    if len(blocks) < 2:
        return False, "no paragraph structure"
    # нумерованные пункты в одну строку («1. … 2. …») вместо абзацев: рвут
    # подпись к фото и восприятие — формат нарушен, идёт на повтор
    if re.search(r"(?<![\d.,])\d{1,2}[.)]\s", post):
        return False, "enumerated items instead of paragraphs"
    head = re.sub(r"^\*\*(.+?)\*\*$", r"\1",
                  blocks[0].split("\n")[0].strip()).lstrip("#").strip()
    if not head or len(head) > 160:
        return False, "bad headline (%d)" % len(head)
    if len(post) < 300:
        return False, "too short: %d" % len(post)
    if len(post) > MAX_POST_CHARS:
        return False, "too long: %d" % len(post)
    comp = _completeness_errors(post, source_text, html)
    if comp:
        return False, "; ".join(comp)
    return True, ""


def _ai_edit_post(text, title, url, source, provider, attempts=2, html=None):
    """Редактура ПОЛНОГО текста статьи через существующий GigaChatProvider
    (тот же клиент, что у AI-канала; нового ИИ-клиента в проекте нет).
    -> (post_body, note): пустое тело = неудача. Максимум `attempts` вызовов
    (1 повтор — паттерн langguard), бесконечных ретраев нет."""
    user = ("Заголовок: %s\nURL: %s\nИсточник: %s\n\nПОЛНЫЙ ТЕКСТ СТАТЬИ:\n%s"
            % ((title or "").strip()[:300], url, source, text or ""))
    msgs = [{"role": "system", "content": AI_EDIT_SYSTEM},
            {"role": "user", "content": user}]
    note = "empty result"
    for i in range(attempts):
        try:
            raw = provider.complete(msgs)
        except Exception as e:
            note = "error: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("agro ai edit attempt %d/%d: %s", i + 1, attempts, note)
            continue
        post = _clean_ai_output(raw)
        ok, why = _edit_contract_ok(post, text, html)
        if ok:
            return post, ""
        note = why
        log.warning("agro ai edit attempt %d/%d failed: %s", i + 1, attempts, why)
    return "", note


def _finalize_post(row, draft, tags, text, title, url, source, provider,
                   html=None):
    """Итоговый пост. Порядок: кэш (post_text уже готов после прошлой
    попытки) -> ИИ-редактура (живой провайдер) -> extractive-черновик
    (провайдера нет — прежнее поведение; его полноту держит editorial_agro).
    ИИ доступен, но после повтора контракт не пройден -> ('', 'failed', note):
    материал уходит в review, сырой/оборванный/неполный текст НЕ
    публикуется.
    -> (post, ai_state, note); ai_state: cached|edited|skipped|failed."""
    cached = (row.get("post_text") or "").strip()
    if cached:
        return cached, "cached", ""
    if provider is None or not getattr(provider, "available", False) \
            or not callable(getattr(provider, "complete", None)):
        return draft, "skipped", ""
    body, note = _ai_edit_post(text, title, url, source, provider, html=html)
    if not body:
        return "", "failed", note
    post = "%s\n\nИсточник: %s\n%s" % (body.rstrip(), url, hashtags.render(tags))
    return post, "edited", ""


def process_url(st, url, source, publish=False, dry_run=True, provider=None):
    """Один материал агро-линии. -> dict(status, ...) как pipeline.process_candidate.

    provider — существующий ИИ-провайдер (GigaChatProvider/NullProvider);
    по умолчанию резолвится ai_mod.get_provider(). ИИ вызывается ТОЛЬКО после
    всех гейтов (thin/stale/classifier/missing_image) и не влияет на
    URL/image_url/дедуп."""
    out = {"url": url, "source": source, "status": "skipped", "reason": ""}
    mid = st.add(url, source)
    row = st.get(mid) or {}
    if _known_skip(row.get("status")):
        out.update(reason="already %s" % row.get("status"))
        return out
    try:
        _, html = httpclient.fetch(url, timeout=config.FETCH_TIMEOUT_SEC)
        ext = extraction.extract_from_html(html, url)
    except httpclient.FetchError as e:
        st.update(mid, status="failed", reason="fetch: %s" % str(e)[:200])
        out.update(status="failed", reason="fetch")
        return out
    text = ext.get("text") or ""
    st.update(mid, content_hash=utils.content_hash(text))
    if ext.get("quality") == "failed" or len(text) < MIN_BODY_CHARS:
        st.update(mid, status="rejected", reason="thin content (%d)" % len(text))
        out.update(status="rejected", reason="thin")
        return out
    if not _age_ok(ext.get("published_at")):
        st.update(mid, status="rejected", reason="stale: %s" % ext.get("published_at"))
        out.update(status="rejected", reason="stale")
        return out

    verdict = classifier_agro.classify(ext.get("title") or "", text,
                                       ext.get("published_at") or "")
    out["agro_type"] = verdict["type"]
    out["confidence"] = verdict["confidence"]
    if verdict["type"] != "practical":
        news_hold = verdict["type"] == "news"
        st.update(mid, status="news_hold" if news_hold else "rejected",
                  reason="classifier_agro: %s" % verdict["type"])
        out.update(status="news_hold" if news_hold else "rejected")
        return out

    # контракт TEXT+IMAGE+SOURCE: без изображения материал НЕ готовится
    # к публикации (publish=NO, reason=missing_image; в published не попадает)
    image_url = _norm_image(ext.get("image"), url) or _content_image(html, url)
    if not image_url:
        st.update(mid, status="rejected", reason="missing_image")
        out.update(status="rejected", reason="missing_image")
        return out

    # ИИ-редактура ПОЛНОГО текста — после всех гейтов, до редакционной
    # проверки; при неудаче (после повтора) — review, сырое не публикуем
    provider = provider if provider is not None else ai_mod.get_provider()
    draft, tags = build_post(ext.get("title") or "", text, url, source, verdict)
    post, ai_state, ai_note = _finalize_post(row, draft, tags, text,
                                             ext.get("title") or "", url,
                                             source, provider, html=html)
    if ai_state == "failed":
        st.update(mid, status="review", reason="ai edit: %s" % ai_note[:250])
        out.update(status="review", reason="ai edit failed", ai=ai_state)
        return out
    out["ai"] = ai_state
    if ai_state == "edited":
        log.info("agro ai edit ok (%d chars, usage=%s)", len(post),
                 getattr(provider, "last_usage", None))
    errs = editorial_agro(post, text, html)
    if errs:
        st.update(mid, status="review", reason="agro editorial: %s" % "; ".join(errs)[:300])
        out.update(status="review", reason="editorial gate")
        return out
    st.update(mid, status="post_ready", post_text=post, image_url=image_url,
              reason="agro %s%s" % (verdict["type"],
                                    "+ai" if ai_state == "edited" else ""))
    out.update(status="post_ready", hashtags=tags)

    if publish and not dry_run:
        # байты изображения скачиваем и валидируем ДО claim: ошибка скачивания
        # -> status=failed (не в _known_skip — авто-ретрай следующим прогоном),
        # claim не трогаем
        try:
            photo = httpclient.fetch_bytes(image_url)
        except Exception as e:
            st.update(mid, status="failed", reason="image fetch: %s" % str(e)[:200])
            out.update(status="failed", reason="image fetch")
            return out
        if not st.claim_for_publish(mid):
            out.update(reason="claim lost (parallel run)")
            return out
        res = telegram.publish_post(post, dry_run=False, channel="agro",
                                    image=photo)
        if res.ok:
            st.mark_published(mid, res.message_id, config.AGRO_CHAT_ID,
                              case_model.case_id_for(url, text[:2000]),
                              hashtags=hashtags.render(tags), content_type="agro")
            out.update(status="published", telegram_message_id=res.message_id)
        else:
            st.release_claim(mid, "review", "publish failed: %s" % (res.error or ""))
            out.update(status="review", reason="publish failed: %s" % res.error)
    return out


def run(dry_run=True, publish=False, sources=None, st=None,
        limit_per_source=None, provider=None):
    """Один цикл агро-канала. Публикация только publish=1 и AGRO_PUBLISH=1
    (job передаёт), иначе — honest dry-run без отправки. Возвращает summary
    (включая диагностику ИИ: ai_edited/ai_failed/ai_cached/ai_skipped)."""
    st = st or storage_mod.Storage(config.AGRO_DB_PATH)
    srcs = sources or config.AGRO_SOURCES
    per = limit_per_source or config.AGRO_MAX_PER_RUN
    allow_publish = publish and config.AGRO_PUBLISH
    provider = provider if provider is not None else ai_mod.get_provider()
    summary = {"checked": 0, "post_ready": 0, "published": 0, "rejected": 0,
               "review": 0, "news_hold": 0, "failed": 0, "skipped": 0,
               "ai_edited": 0, "ai_failed": 0, "ai_cached": 0,
               "ai_skipped": 0,
               "dry_run": dry_run or not allow_publish}
    published = 0
    for name in srcs:
        ad = adapters.ADAPTERS.get(name)
        if not ad:
            log.warning("agro source %r: адаптер не зарегистрирован (см. отчёт)", name)
            continue
        try:
            urls = ad.discover()
        except Exception as e:
            log.warning("agro discover %s failed: %s", name, e)
            continue
        useful = 0
        # сводные фиды (журнал + новости) отдают старьё первыми: сканируем
        # шире лимита, но свежеческий гейт НЕ ослабляем — stale просто
        # не расходует бюджет источника (до 4x проверок на источник)
        for u in urls[:per * 4]:
            if useful >= per:
                break
            if allow_publish and published >= config.AGRO_PUBLISH_LIMIT:
                break
            r = process_url(st, u, name, publish=allow_publish, dry_run=dry_run,
                            provider=provider)
            summary["checked"] += 1
            key = r.get("status")
            if key in summary:
                summary[key] += 1
            ai_key = r.get("ai")
            if ai_key in ("edited", "failed", "cached", "skipped"):
                summary["ai_" + ai_key] += 1
            if key in ("post_ready", "published", "review", "news_hold"):
                useful += 1
            if r.get("status") == "published":
                published += 1
            log.info("agro %s%s: %s %s", r.get("status"),
                     " [ai=%s]" % ai_key if ai_key else "", name, u[:80])
    return summary
