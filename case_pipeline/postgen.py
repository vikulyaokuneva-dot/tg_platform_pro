# -*- coding: utf-8 -*-
"""case_pipeline.postgen — CASE -> пост для канала «AI Автоматизация | Бизнес».

Позиционирование: ПРОБЛЕМА → РЕШЕНИЕ → КАК АВТОМАТИЗИРОВАЛИ → РЕЗУЛЬТАТ →
ЭФФЕКТ → ПРИМЕНИМОСТЬ → CTA. Практический тон, без хайпа.

Два режима:
  1. template — детерминированный RU-каркас, факты — цитаты из CASE (всегда
     доступен, без AI);
  2. ai_polish (если GigaChat доступен) — RU-переработка CASE; результат
     валидируется: НИ одно новое число, компания сохранена, хайп-стоп-фразы.
     Провал валидации => откат к template.

validate_post() обязателен перед публикацией в обоих режимах.
"""
import json
import logging
import re

from . import ai as ai_mod
from . import hashtags, langguard, textclean
from .utils import digits_of, extract_numbers, norm_num_text, ws_norm

log = logging.getLogger("case_pipeline.postgen")

HYPE_RX = re.compile(r"(революцион|меняет всё|всё изменит|будущее уже здесь|"
                     r"невероятн|прорыв|уникальн|инновационн)", re.I)
HASHTAGS = "#AI #автоматизация #кейсбизнеса"  # legacy-константа (заменена словарём hashtags)

CTA_SALES = ("💼 Если у вас сотрудники вручную переносят заявки, документы или "
             "обращения между сервисами — такой процесс обычно поддаётся "
             "автоматизации: заявки → AI-классификация → CRM/Telegram → ответ "
             "клиенту за секунды.")
CTA_SUPPORT = ("💼 Подобные схемы работают и в малом бизнесе: обращения → AI-"
               "маршрутизация → база знаний → ответ или эскалация. Ручной "
               "колл-центр/поддержка — первое, что стоит автоматизировать.")
CTA_DOCS = ("💼 Документы, согласования, отчётность — то же поле боя: шаблоны → "
            "AI-проверка → маршрутизация → контроль. Обычно окупается за "
            "первые недели.")
CTA_GENERIC = ("💼 Подобную схему можно собрать и под небольшой бизнес: данные → "
               "AI-обработка → нужная система → автоматический отклик. "
               "Сила — не в размере компании, а в правильно выбранном процессе.")


def pick_cta(case):
    blob = ws_norm(" ".join([case.get("problem", ""), case.get("implementation", "")] +
                             list(case.get("results") or [])))
    if re.search(r"lead|sales|заявк|crm|pipeline|сделк|выручк|revenue|quota|"
                 r"реклам|маркетинг|ставк|конверси|трафик|click|retarget|кампани|скидк", blob):
        return CTA_SALES
    if re.search(r"document|документ|report|отчёт|invoice|счет|счёт|finance|финанс|compliance|budget|бюджет|согласов", blob):
        return CTA_DOCS
    if re.search(r"support|поддержк|helpdesk|ticket|обращени|call|service", blob):
        return CTA_SUPPORT
    return CTA_GENERIC


def _short(s, n=220):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


PREP_RX = re.compile(r"(?:\s|^)(?:к|на|до|в|за|по|с|у|от|для|без|при)\s*$")


def _num_members(text):
    """(токены чисел, цифровые ядра) — единая мера «число упоминается в тексте»
    для фильтра Цифры и для editorial_check."""
    nums = extract_numbers(norm_num_text(ws_norm(text)))
    cores = {digits_of(n) for n in nums if digits_of(n)}
    return nums, cores


def _num_used(val, nums, cores):
    v = ws_norm(re.sub(r"\s+", "", val or ""))
    return bool(v) and (v in nums or (digits_of(v) in cores if digits_of(v) else False))


def _metric_parts(metric):
    """(значение, короткий контекст из evidence-цитаты источника). Слова —
    только из источника, выдумывания нет."""
    val = textclean.clean((metric.get("value") or "").strip())
    quote = textclean.clean((metric.get("evidence") or {}).get("quote") or "")
    ctx = ""
    idx = quote.find(val)
    if idx > 0:
        words = re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'-]{1,}", quote[:idx])
        ctx = PREP_RX.sub("", " ".join(words[-4:])).strip()
    return val, ctx


# «Что автоматизировали»: цитата-перечисление сервисов без механики подаётся
# цепочкой (тот же каркас, что в выводах канала), с сохранением цитаты.
MECHANISM_RX = re.compile(
    r"(данные|обработк|анализ|модел[ьяи]|алгоритм|правил|\bбот\b|сценар|интеграц|"
    r"маршрутиз|классиф|извлечени|автоответ|настройк|→|data|process|analy|model|"
    r"rule|workflow|trigger|routing|predict|enrich|scoring)", re.I)
SERVICES_LIST_RX = re.compile(
    r"^[^.,;!?]{3,40}(?:,| и) ?[^.,;!?]{2,40}(?:,| и)?[^.,;!?]{0,40}$")


def _mechanics(impl):
    impl = textclean.clean(impl or "")
    if not impl:
        return ""
    has_list = (SERVICES_LIST_RX.match(impl) or impl.count(",") >= 2
                or re.search(r"\s+\w+\s*(?:,| и)\s+\w+\s*(?:,| и)\s+\w+", impl))
    if not MECHANISM_RX.search(impl) and has_list:
        return ("цепочка: данные → AI-обработка → действие в бизнес-системе "
                "(в источнике: %s)" % _short(impl, 160).rstrip("."))
    return impl


def clean_for_publish(text):
    """Нормализация уже сохранённого поста (путь backlog). -> (text, ok)."""
    t = textclean.clean(text or "")
    return t, not textclean.has_artifacts(t)


def tags_for_case(case):
    """Контролируемые теги поста (1 TYPE + 1–2 DOMAIN + 1 COMPANY)."""
    blob = ws_norm(" ".join([case.get("problem", ""), case.get("implementation", ""),
                             " ".join(case.get("results") or []),
                             ", ".join(case.get("technology") or [])]))
    return hashtags.build("case", blob, case.get("company_name"))


def render_template(case, tags=None):
    """RU-каркас; fact-строки — цитаты источника (EN допустимы, дальше guard).

    Редакционные правила (post-review «Читай-город»):
    * заголовок — осмысленная фраза «контекст + цифра» из цитаты источника,
      а не «+56% / +1,4 п. п. / 16%» (перечисление голых цифр запрещено);
    * блок «Цифры» — только показатели, реально использованные в тексте поста
      И имеющие контекст; голые цифры не выводятся;
    * HTML-артефакты/склейки нейтрализуются textclean на всех source-строках."""
    tags = tags or tags_for_case(case)
    comp = textclean.clean(case.get("company_name") or "компания")
    problem = textclean.clean(case.get("problem") or "")
    impl = textclean.clean(case.get("implementation") or "")
    results = [textclean.clean(r) for r in (case.get("results") or []) if r]

    parsed = [_metric_parts(m) for m in (case.get("metrics") or []) if m.get("value")]
    parsed = [(v, c) for v, c in parsed if v]
    body_txt = ws_norm(" ".join([problem, impl] + results))
    body_nums, body_cores = _num_members(body_txt)
    # «использованные с контекстом»: значение реально упоминается в теле поста
    used = [(v, c) for v, c in parsed if c and _num_used(v, body_nums, body_cores)]
    if used:
        v, c = used[0]
        headline = "%s: %s" % (comp, _short("%s %s" % (c, v), 90))
    else:
        headline = "%s: практический эффект автоматизации" % comp

    lines = []
    lines.append("⚡ " + headline)
    lines.append("")
    lines.append("🏢 Кто: %s (%s)" % (comp, case.get("source_domain", "")))
    if problem:
        lines.append("❗️ Проблема: «%s»" % _short(problem, 200))
    if impl:
        mech = _mechanics(impl)
        if mech.startswith("цепочка:"):
            lines.append("🔧 Что автоматизировали: %s" % _short(mech, 240))
        else:
            lines.append("🔧 Что автоматизировали: «%s»" % _short(mech, 220))
    tech = ", ".join((case.get("technology") or [])[:4])
    if tech:
        lines.append("⚙️ Технологии: %s" % tech)
    if results:
        lines.append("📈 Результат: «%s»" % _short(results[0], 200))
    if used:
        lines.append("🔢 Цифры:")
        for v, c in used[:3]:
            lines.append("- %s %s" % (_short(c, 60), v))
    lines.append("")
    lines.append("💡 Вывод для бизнеса: связка «данные → AI-обработка → "
                 "бизнес-система» убирает ручной перенос информации между "
                 "сервисами — самый частый источник потерь времени и денег.")
    lines.append(pick_cta(case))
    lines.append("")
    src = case.get("source_url") or ""
    if src:
        lines.append("Источник: %s" % src)
    lines.append(hashtags.render(tags))
    return "\n".join(lines)


POLISH_SYSTEM_TMPL = (
    "Ты — редактор канала «AI Автоматизация | Бизнес». Перепиши материал "
    "СТРОГО по фактам из переданного JSON CASE, на русском, практическим языком.\n"
    "СТРУКТУРА: заголовок — осмысленная фраза (до 12 слов) с 1–2 главными цифрами "
    "и их пояснением, например «выручка с клика выросла на +56%»; ПЕРЕЧИСЛЕНИЕ "
    "цифр через слэш («+56% / 16%») в заголовке запрещён. Далее: кто компания; "
    "проблема; что автоматизировали и как это работало — ОПИСЫВАЙ МЕХАНИКОЙ "
    "ЦЕПОЧКОЙ «данные → обработка/модель → действие в бизнес-системе», а не "
    "просто списком сервисов; результат; цифры; что отсюда может применить "
    "обычный бизнес; CTA-абзац; ссылка; "
    "хэштеги в последней строке ровно такие: {tags}.\n"
    "Блок «Цифры»: только показатели, которые уже названы в тексте поста и имеют "
    "понятный читателю контекст (по строке на показатель); голые числа без "
    "пояснения — не выводить.\n"
    "Символы '<' и '>' не использовать: пиши «менее 16% ДРР», «более 2 раз»; "
    "HTML-теги, сущности (&lt; и т.п.) и склейки вида «16%ДРР» недопустимы.\n"
    "ЗАПРЕЩЕНО: любые числа/проценты/суммы, которых нет в CASE; усиление формулировок; "
    "фразы «революционный прорыв», «ИИ меняет всё», «это будущее бизнеса»; пересказ-«воду»; "
    "свои дополнительные хэштеги.\n"
    "Если источник английский — весь текст поста (кроме названий/продуктов) переводи на русский.\n"
    "Верни только текст поста (без JSON, без markdown-обёртки)."
)


def render_post(case, source_text, provider=None):
    """-> (text, mode, lang_ok). Кандидаты: ai_polish (если провайдер живой),
    template. Каждый проходит validate_post + Russian Language Guard
    (1 retry). Ни один не прошёл guard -> lang_ok=False (review, не публикация)."""
    tags = tags_for_case(case)
    template = render_template(case, tags)
    provider = provider or ai_mod.get_provider()
    candidates = []
    if type(provider).__name__ == "GigaChatProvider" and provider.available:
        try:
            payload = {k: case.get(k) for k in
                       ("company_name", "problem", "implementation", "technology",
                        "results", "metrics", "economic_effect", "source_url", "source_title")}
            msgs = [{"role": "system", "content": POLISH_SYSTEM_TMPL.format(
                         tags=hashtags.render(tags))},
                    {"role": "user", "content": "CASE JSON:\n" +
                     json.dumps(payload, ensure_ascii=False)[:7000] +
                     "\n\nCTA-блок обязан присутствовать в конце (бизнес-приглашение к "
                     "автоматизации, без агрессивной рекламы)."}]
            text = textclean.clean((provider.complete(msgs) or "").strip())
            if text and len(text) > 300:
                ok, errors = validate_post(text, case, source_text)
                if ok:
                    candidates.append((text, "ai_polish"))
                else:
                    log.info("ai polish rejected: %s", errors[:2])
        except Exception as e:
            log.warning("ai polish failed: %s", e)
    candidates.append((template, "template"))

    for cand, mode in candidates:
        cand = hashtags.apply_to_post(cand, tags)
        final, ok, note = langguard.ensure_russian(cand, provider)
        if not ok:
            log.info("language guard FAIL (%s): %s", mode, note)
            continue
        final = hashtags.apply_to_post(final, tags)
        vok, verr = validate_post(final, case, source_text)
        if not vok:
            log.info("post invalid after guard (%s): %s", mode, verr[:2])
            continue
        if final != cand:
            mode += "+ru"
        return final, mode, True
    return template, "template_langfail", False


def editorial_check(text):
    """Редакционные гейты, не требующие source-текста: HTML-артефакты,
    заголовок-перечисление цифр, «голые» цифры в блоке «Цифры»."""
    errors = []
    if textclean.has_artifacts(text):
        errors.append("html artifact in post")
    first = next((l for l in (text or "").splitlines() if l.strip()), "")
    if re.search(r"\d[\d.,]*\s*/\s*[-+−]?\d", first) or \
            re.search(r"\d[\d.,]*[^\n]{0,25}?\s/\s*[-+−]?\d", first):
        errors.append("headline: bare numbers separated by slashes")
    dm = re.search(r"(?mi)^[^\w\n]*цифры[^\w\n]*:\s*\n"
                   r"((?:[-•*].+(?:\n|$))+)", (text or "") + "\n")
    if dm:
        block = dm.group(1)
        rest = (text or "").replace(block, " ")
        rest_nums, rest_cores = _num_members(rest)
        naked = [n for n in sorted(extract_numbers(norm_num_text(ws_norm(block))))
                 if digits_of(n) and n not in {"1", "2", "3"}
                 and not _num_used(n, rest_nums, rest_cores)]
        if naked:
            errors.append("digits block not used in text: %s" % naked[:4])
    return (not errors), errors


def validate_post(text, case, source_text):
    """Финальный security-гейт поста: ни одного числа вне источника, компания
    упомянута, без хайпа, валидная длина + редакционные правила."""
    errors = []
    if not text or len(text) > 3900:
        errors.append("bad length %s" % (len(text or "")))
    if HYPE_RX.search(text or ""):
        errors.append("hype phrase in post")
    src_norm = norm_num_text(ws_norm(source_text))
    src_nums = extract_numbers(src_norm)
    post_nums = extract_numbers(norm_num_text(ws_norm(text)))
    src_cores = {digits_of(n) for n in src_nums if digits_of(n)}
    invented = [n for n in post_nums if n not in src_nums
                and re.sub(r"[^\d.,]", "", n) not in src_norm
                and digits_of(n) not in src_cores]
    invented = [n for n in invented if re.search(r"\d", n) and n not in
                {"1", "2", "3"}]  # заголовочные счётцы каркаса
    if invented:
        errors.append("numbers not in source: %s" % invented[:5])
    comp = ws_norm(case.get("company_name") or "").split()[0:1]
    if comp and comp[0] not in ws_norm(text):
        errors.append("company missing in post")
    ok_e, err_e = editorial_check(text)
    errors.extend(err_e)
    return (not errors), errors
