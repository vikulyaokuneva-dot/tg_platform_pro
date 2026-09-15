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


# ===========================================================================
#  СМЫСЛОВОЙ ЗАГОЛОВОК: КТО + ЧТО ПРОИЗОШЛО + ЗА СЧЁТО ЧЕГО
#
#  Заголовок НЕ собирается из списка метрик и не склеивается из сырых слов
#  перед цифрой. Каждая evidence-цитата разбирается на конструкции делового
#  результата:
#    пара "22,9% → 36% доля клиентов…"   -> «доля … выросла с 22,9% до 36%»
#    множитель "×4,3 выручка от …"       -> «выручка … выросла в 4,3 раза»
#    глагол «X выросла на N%»             -> субъект+глагол+цифра дословно
#    дательная "+N% к выручке с клика"    -> дословно (уже грамматично)
#    порог "ДРР не выше 16%"              -> дословно
#    «78% — конверсия в …»                -> реверс с тире
#  Главный результат — по рангу семьи (выручка/продажи > конверсия/повторные
#  > экономика > операционка > прочее), бонус за цифру в заголовке статьи,
#  затем величина. Механизм («за счёт …») — только дословно из evidence или
#  из контрольного лексикона, чьи поверхности найдены в evidence; AI/ML не
#  повышаются: формулировка ровно та, что есть в источнике.
# ===========================================================================

_NAME = r"[\w\-']"
_WORD2 = r"[\w'\-]{2,}"
_PAIR_RX = re.compile(
    r"(\d[\d.,]*)\s*(%|п\.\s?п\.?)?\s*(?:→|->)\s*(\d[\d.,]*)\s*(%|п\.\s?п\.?)?\s+"
    r"([^\W\d_]" + _NAME + r"*(?:\s+[^\W\d_]" + _NAME + r"*){1,6})", re.U)
_MULT_RX = re.compile(
    r"[×]\s*(\d[\d.,]*)\s+([^\W\d_]" + _NAME + r"*(?:\s+[^\W\d_]" + _NAME + r"*){0,6})", re.U)
_GREW_RX = re.compile(
    r"\b(выросл\w*|увеличил\w*|увеличел\w*|увеличен\w*|повысил\w*|снизил\w*|сократил\w*"
    r"|уменьшил\w*|упал\w*|упало|упали|поднял\w*|улучшил\w*|ускорил\w*|ускорил[аи]?|вырост\w*)\b"
    r"\s*(?:\b(на|до|в|за)\b\s*)?[-+\u2212]?(\d[\d.,]*)\s*(%|п\.\s?п\.|минут\w*|часов|часа\b|дней|дня\b|₽|раз\w*)", re.U)
_GREW_RX = re.compile(_GREW_RX.pattern, re.I)
_DELTA_RX = re.compile(
    r"([+\u2212])\s*(\d[\d.,]*)\s*(%|п\.\s?п\.)\s+к\s+((?:" + r"[\w'\-]+" + r"\s){1,5}" + r"[\w'\-]+" + r")", re.U)
_HEADVAL_RX = re.compile(
    r"([+\u2212])\s*(\d[\d.,]*)\s*(%|п\.\s?п\.)\s+((?:" + r"[\w'\-]+" + r"\s){1,5}" + r"[\w'\-]+" + r")", re.U)
_THRESH_RX = re.compile(
    r"\b(ДРР|ROMI|ROI|CPA|CPC)\b[^\d%!]{0,28}?\b(не выше|не более|не должен превышать|менее|ниже)\s*(\d[\d.,]*)\s*(%)", re.U)
_REVERSE_RX = re.compile(
    r"\b(\d[\d.,]*)\s*(%)\s*[—–\-]{1,2}\s*\b(конверсия|доля|выручка|продажи|расходы|рост|маржинальн\w+|open rate|CTOR|CTR)\b"
    r"([^+−×\d%!]{0,50})", re.U)
# «упал/выросла … с A до B»: подлежащее перед глаголом или объект после него
_SLIDE_RX = re.compile(
    r"((?:" + _WORD2 + r"\s){1,4})(выросл\w*|увеличил\w*|повысил\w*|поднял\w*|упал\w*"
    r"|упала|упали|снизил\w*|сократил\w*|уменьшил\w*)\s+с\s+(\d[\d.,]*)\s*(%|п\.\s?п\.?)?\s*"
    r"до\s+(\d[\d.,]*)\s*(%|п\.\s?п\.)", re.I)
_SLIDE2_RX = re.compile(
    r"\b(выросл\w*|увеличил\w*|повысил\w*|поднял\w*|упал\w*|упала|упали|снизил\w*"
    r"|сократил\w*|уменьшил\w*)\s+((?:" + _WORD2 + r"\s){1,3})с\s+(\d[\d.,]*)\s*(%|п\.\s?п\.?)?\s*"
    r"до\s+(\d[\d.,]*)\s*(%|п\.\s?п\.)", re.I)
_REDUCEN_RX = re.compile(
    r"(\d[\d.,]*)\s*%\s+(?:reductions?|cuts?|decreases?|drops?|savings)\s+(?:in|of|on)\s+"
    r"((?:[\w'\-]+\s){1,4}[\w'\-]+)", re.I)
_INCR_EN_RX = re.compile(
    r"(\d[\d.,]*)\s*%\s+(?:increase|boost|lift|growth|gain)s?\s+(?:in|of)\s+"
    r"((?:[\w'\-]+\s){1,4}[\w'\-]+)", re.I)
_REV_EN_RX = re.compile(
    r"\b(recovered|saved|generated|unlocked|boosted)\b\s+\$?(\d[\d.,]*)\s*(K|M|B|bn|mln)?"
    r"\s*(?:of|in)\s+(revenue|sales|costs|time)", re.I)

# (ранг, ключевые слова семьи) — чем меньше ранг, тем сильнее бизнес-смысл
_FAM_RULES = (
    (1, r"arppu|arpu|выручк|ревеню|revenue|gmv|доход"),
    (1, r"продаж|sales|выкуп|прибыл|маржин|profit"),
    (2, r"повторн|покупо?к|retention|удержан|возвращаемост|лояльн|конверси|conversion|open rate|ctor|ctr|вовлеч|engagement"),
    (3, r"дрр|cpa|cpc|стоимост|расход|затрат|cost|бюджет|цена|\broi\b|romi|эконом|₽"),
    (4, r"время|time|минут|час|верстк|обработк|ticket|обращени|ошибк|error|поддержк|скорост|response|точност"),
)
# глагол по головному слову результата; нет в словаре -> тире-конструкция
_HEAD_VERBS = {
    "выручка": ("выросла", "снизилась"), "доля": ("выросла", "снизилась"),
    "конверсия": ("выросла", "упала"), "продажи": ("выросли", "упали"),
    "стоимость": ("выросла", "снизилась"), "расходы": ("выросли", "снизились"),
    "затраты": ("выросли", "снизились"), "время": ("выросло", "сократилось"),
    "число": ("выросло", "снизилось"), "количество": ("выросло", "снизилось"),
    "работа": ("выросла", "сократилась"), "rate": ("вырос", "упал"),
    "дрр": ("вырос", "снизился"), "ромi": ("вырос", "снизился"),
    "база": ("выросла", "снизилась"), "охват": ("вырос", "снизился"),
    "трафик": ("вырос", "снизился"), "чек": ("вырос", "снизился"),
    "прибыль": ("выросла", "снизилась"), "вовлечённость": ("выросла", "снизилась"),
    "точность": ("выросла", "снизилась"), "открываемость": ("выросла", "упала"),
    "ошибки": ("выросли", "сократились"), "обращения": ("выросли", "сократились"),
}
# EN-объекты цитат -> (русское имя, ранг берётся по нему автоматически)
_EN_LEX = (
    ("lead response time", "время ответа на заявки"), ("campaign prep time", "время подготовки кампаний"),
    ("response time", "время ответа"),
    ("support tickets", "обращения в поддержку"), ("tickets", "тикеты поддержки"),
    ("lead sync errors", "ошибки синхронизации"), ("sync errors", "ошибки синхронизации"),
    ("errors", "ошибки"), ("backup work", "ручная работа с бэкапами"),
    ("operational costs", "операционные расходы"), ("costs", "расходы"),
    ("revenue", "выручка"), ("sales", "продажи"),
    ("orders", "заказы"), ("participation", "вовлечённость"), ("accuracy", "точность"),
    ("conversion", "конверсия"), ("adoption", "использование"),
    ("onboarding time", "время онбординга"), ("cumulative downloads", "число скачиваний"),
    ("activation rates", "доля активаций"), ("support", "обращения в поддержку"),
)
_GROW_EN_RX = re.compile(
    r"\b(grew|increased|rose|jumped|improved|boost\w*|up)\b\s*(?:by\s+)?"
    r"(more than|nearly|over)?\s*(\d[\d.,]*)\s*(%)", re.I)
_CUT_EN_RX = re.compile(
    r"\b(cut\w*|slash\w*|reduc\w*|reduction|decreas\w*|saving\w*)\b([^.%\d]{2,50}?)(\d[\d.,]*)\s*(%)", re.I)
_PAIR_EN_RX = re.compile(r"from\s+(\d[\d.,]*)\s*%\s+to\s+(\d[\d.,]*)\s*%\s*(\w+[\w\s]{0,30})", re.I)
_FASTER_EN_RX = re.compile(r"(\d[\d.,]*)\s*%\s+faster\b", re.I)

# механизм: дословная связка из источника (падеж уже правильный)
_MECH_VERB_RX = re.compile(
    r"\b(?:за\s+сч[её]т|благодаря|с\s+помощью|при\s+помощи)\s+("
    r"(?:" + _NAME + r"{2,}\s){0,3}" + _NAME + r"{2,})", re.U)
# механизм: поверхность в evidence -> готовая родительная форма
_MECH_LEX = (
    (r"ml[\s\-]?сегмент", "ML-сегментации"),
    (r"ml[\s\-]?ретаргетинг", "ML-ретаргетинга"),
    (r"повторн\w*\s+(?:покупо?к|заказ)", "повторных покупок"),
    (r"crm[\s\-]?маркетинг", "CRM-маркетинга"),
    (r"(?:автоматическ\w+|авто)\s+рассыл", "автоматических рассылок"),
    (r"программ\w*\s+лояльност", "программы лояльности"),
    (r"триггерн\w*\s+сценар", "триггерных сценариев"),
    (r"маркетинг\s+удержания", "маркетинга удержания"),
    (r"персонализ", "персонализации"),
    (r"pop[\s\-]?up|попап", "попапов"),
    (r"push|пуш", "push-механик"),
    (r"(?:чат|голосов\w+)\s*[\s\-]?\bбот", "чат-бота"),
    (r"скоринг", "скоринга"),
    (r"ретаргетинг", "ретаргетинга"),
    (r"email[\s\-]?рассыл|рассыл", "email-рассылок"),
    (r"сегмент", "сегментации"),
    (r"workflow automation|automation", "автоматизации"),
)
_PREPS = {"к", "от", "до", "без", "для", "после", "за", "счёт", "помощью", "на", "в",
          "по", "при", "около", "более", "менее", "с", "уровне", "благодаря", "из"}
_DANGLING = {"применением", "применение", "использованием", "внедрением", "счету",
             "счёту", "основе", "добавке", "помощь"}
_ANCHOR_VB_RX = re.compile(
    r"(выросл|вырос|увелич|снизил|сократ|повыс|упал|поднял|уменьш|улучш|ускор"
    r"|достиг|дошл|стал|вернул|получил|собир|превыш|не выше|не более|не должен|менее|ниже"
    r"|\bрост\b|\bприрост\b|снижение|падение|увеличение|сокращение)", re.I)
_OBLIG_RX = re.compile(
    r"\b(выручке|выручки|росте|продажах|продажам|покупателю|клиенту|стоимости|заявкам"
    r"|обращениям|применении|применением|верстке|верстку|настройке|бюджете|лояльности"
    r"|покупке|покупкой|конверсии|конверсией|маркетинге|обработке|поддержке|аудитории"
    r"|базе|сценарии|рассылке|сегментации|программе|автоматизации)\b", re.I)
_BAD_START_RX = re.compile(r"^(какие|какой|какая|это|этот|эта|такой|они|он|она|его|её|их|нас|вас)\b")


def _family(text):
    t = ws_norm(text)
    for rank, rx in _FAM_RULES:
        if re.search(rx, t):
            return rank
    return 5


def _mag(num, unit):
    try:
        v = float((num or "0").replace(",", ".").rstrip("."))
    except ValueError:
        return 0.0
    u = (unit or "%").lower()
    if u.startswith("п"):
        return v * 3
    if u.startswith("раз"):
        return v * 100
    return v


def _agree(name, grew=True):
    """Глагол результата по опорному слову имени (первое слово имени или
    первое слово лексикона families); нет в словаре -> None (тире-форма)."""
    for w in ws_norm(name).replace("«", "").replace("»", "").split(" "):
        forms = _HEAD_VERBS.get(w)
        if forms:
            return forms[0] if grew else forms[1]
    return None


def _u(unit):
    """Печатная единица значения: 'п. п.' -> 'п.п.', без висящей точки."""
    u = (unit or "%").strip()
    if u.startswith("п"):
        return "п.п."
    return u.rstrip(".")


def _trim_phrase(phrase, limit=7):
    """Слова фразы-имени: обрезаем на границе следующего блока (с слова с
    заглавной буквы или с цифрой внутри — там уже другая метрика/предложение)
    и на висящих предлогах/прилагательных. Однобуквенные предлоги сохраняем."""
    words = re.findall(r"[^\W\d_][\w'\-]*", phrase or "")
    for i in range(1, len(words)):
        w = words[i]
        if re.match(r"^[A-ZА-ЯЁ]", w) and "-" not in w and "‑" not in w:
            words = words[:i]  # «…клика Задача…», «…действие В некоторых…»
            break
        if re.search(r"\d", w):  # «игре70%» — граница следующего числа
            stem = re.match(r"^[^\W\d_]+", w)
            words = words[:i] + ([stem.group(0)] if stem and len(stem.group(0)) >= 2 else [])
            break
    words = words[:limit]
    while words and (len(words[-1]) < 3 or ws_norm(words[-1]) in _PREPS
                     or ws_norm(words[-1]) in _DANGLING
                     or re.search(r"ые$", ws_norm(words[-1]))):
        words.pop()
    return " ".join(words)


def _result_candidates(val, quote):
    """Все headline-конструкции результата из одной цитаты, содержащие число
    метрики. -> [dict(rank, mag, text)]."""
    out = []
    vd = digits_of(val)

    def push(rank, mag, text):
        text = textclean.clean(re.sub(r"\s{2,}", " ", text)).strip(" ,;:—–-")
        if text.endswith(".") and not text.endswith("п.п."):
            text = text[:-1]
        if not text or (digits_of(text) and vd not in digits_of(text)):
            return
        if rank >= 5:
            return  # заголовок с непонятной семьёй = нет бизнес-смысла
        out.append({"rank": rank, "mag": mag, "text": text})

    for m in _PAIR_RX.finditer(quote):
        if vd not in (digits_of(m.group(1)), digits_of(m.group(3))):
            continue
        a, ua, b, ub, name = m.groups()
        name = _trim_phrase(name)
        ua = ua or "%"
        ub = ub or ua
        unit = ub
        grew = _mag(b, unit) >= _mag(a, ua)
        verb = _agree(name, grew)
        pair = "с %s%s до %s%s" % (a, ua, b, ub)
        if verb:
            push(_family(name), abs(_mag(b, unit) - _mag(a, ua)),
                 "%s %s %s" % (name, verb, pair))
        else:
            push(_family(name), abs(_mag(b, unit) - _mag(a, ua)), "%s — %s" % (name, pair))

    for m in _MULT_RX.finditer(quote):
        if vd != digits_of(m.group(1)):
            continue
        num, name = m.groups()
        name = _trim_phrase(name)
        rank = _family(name)
        if rank >= 5 and _mag(num, "раз") < 2:
            continue
        if not name:
            continue
        push(rank, _mag(num, "раз"),
             "%s %s в %s раза" % (name, _agree(name, True) or "выросла", num))

    for m in _GREW_RX.finditer(quote):
        if vd != digits_of(m.group(3)):
            continue
        verb, p0, num, unit = m.groups()
        subj_raw = quote[:m.start()]
        subj_raw = re.split(r"[.!?,;:\n]", subj_raw)[-1]
        subj = " ".join(re.findall(_NAME + r"{2,}", subj_raw)[-6:])
        fam = _family(subj)
        if fam >= 5:
            continue
        # субъект — от ключевого слова семьи (обрезаем «через год/в итоге»)
        low = ws_norm(subj)
        for _, rx in _FAM_RULES:
            mm = re.search(rx, low)
            if mm:
                subj = " ".join(re.findall(_NAME + r"{2,}", subj[mm.start():])[:6])
                break
        if not subj:
            continue
        u = (unit or "%").rstrip(".")
        if p0:
            prep = p0
        elif u.startswith("раз"):
            prep = "в"
        elif u.startswith(("минут", "час", "дней", "дня", "секунд")):
            prep = "за"
        else:
            prep = "на"
        tail = "%s%%" % num if u == "%" else "%s %s" % (num, u)
        push(fam, _mag(num, unit), "%s %s %s %s" % (subj, verb, prep, tail))

    for m in _DELTA_RX.finditer(quote):
        if vd != digits_of(m.group(2)):
            continue
        sign, num, unit, phrase = m.groups()
        phrase = _trim_phrase(phrase)
        if not phrase or _family(phrase) >= 5:
            continue
        push(_family(phrase), _mag(num, unit), "%s%s%s к %s" % (sign, num, _u(unit), phrase))

    for m in _HEADVAL_RX.finditer(quote):
        if vd != digits_of(m.group(2)):
            continue
        sign, num, unit, phrase = m.groups()
        if ws_norm(phrase).startswith("к "):
            continue
        phrase = _trim_phrase(phrase)
        if not phrase or _family(phrase) >= 5:
            continue
        if re.fullmatch(r"[A-ZА-ЯЁ]{2,}", phrase.split(" ")[0]):
            # метка-аббревиатура — темой вперёд: «ДРР −1,6 п.п.», «CPA −14%»
            push(_family(phrase), _mag(num, unit), "%s %s%s%s" % (phrase, sign, num, _u(unit)))
        else:
            push(_family(phrase), _mag(num, unit), "%s%s%s %s" % (sign, num, _u(unit), phrase))

    for m in _THRESH_RX.finditer(quote):
        if vd != digits_of(m.group(3)):
            continue
        name, words, num, unit = m.groups()
        push(3, _mag(num, unit), "%s %s %s%%" % (name, " ".join(re.findall(_NAME + r"{2,}", words)), num))

    for m in _REVERSE_RX.finditer(quote):
        if vd != digits_of(m.group(1)):
            continue
        num, unit, name, tail = m.groups()
        name = _trim_phrase(name + " " + tail)
        if not name:
            continue
        push(_family(name), _mag(num, unit), "%s — %s%%" % (name, num))

    for rx in (_SLIDE_RX, _SLIDE2_RX):
        for m in rx.finditer(quote):
            g = m.groups()
            if rx is _SLIDE_RX:
                name, verb, a, ua, b, ub = g
            else:
                verb, name, a, ua, b, ub = g
            if vd not in (digits_of(a), digits_of(b)):
                continue
            name = _trim_phrase(name)
            if not name or _family(name) >= 5:
                continue
            ua = ua or "%"
            ub = ub or ua
            grew = _mag(b, ub) >= _mag(a, ua)
            if rx is _SLIDE2_RX:  # «подняла X с A до B» -> именительный + согласованный глагол
                verb = _agree(name, grew) or ("вырос" if grew else "снизился")
            push(_family(name), abs(_mag(b, ub) - _mag(a, ua)),
                 "%s %s с %s%s до %s%s" % (name, verb, a, ua, b, ub))

    # ---- EN-конструкции -> русские имена (числа дословные из цитаты) ----
    for m in _GROW_EN_RX.finditer(quote):
        if vd != digits_of(m.group(3)):
            continue
        num, more = m.group(3), ws_norm(m.group(2) or "")
        pre = ws_norm(quote[:m.start()])[-60:]
        qual = "более чем " if more in ("more than", "over") else ("почти " if more == "nearly" else "")
        for en, ru in _EN_LEX:
            if en in pre:
                verb = _agree(ru, True)
                if verb:
                    push(_family(ru), _mag(num, "%"), "%s %s %sна %s%%" % (ru, verb, qual, num))
                break
    for m in _CUT_EN_RX.finditer(quote):
        if vd != digits_of(m.group(3)):
            continue
        num = m.group(3)
        pre = (ws_norm(quote[max(0, m.start() - 60):m.start()]) + " " + ws_norm(m.group(2)))
        for en, ru in _EN_LEX:
            if en in pre:
                verb = _agree(ru, False)
                if verb:
                    push(_family(ru), _mag(num, "%"), "%s %s на %s%%" % (ru, verb, num))
                else:
                    push(_family(ru), _mag(num, "%"), "%s — на %s%% меньше" % (ru, num))
                break
    for m in _FASTER_EN_RX.finditer(quote):
        if vd != digits_of(m.group(1)):
            continue
        num = m.group(1)
        post = ws_norm(quote[m.end():m.end() + 40])
        pre = ws_norm(quote[max(0, m.start() - 60):m.start()])
        for en, ru in _EN_LEX:
            if en in post or en in pre:
                verb = _agree(ru, False) or "сократилось"
                push(_family(ru), _mag(num, "%") * 2, "%s %s на %s%%" % (ru, verb, num))
                break
    for m in _PAIR_EN_RX.finditer(quote):
        if vd not in (digits_of(m.group(1)), digits_of(m.group(2))):
            continue
        a, b, tail = m.groups()
        ru = None
        ctxw = ws_norm(quote[max(0, m.start() - 60):m.start()]) + " " + ws_norm(tail[:40])
        for en, name in _EN_LEX:
            if en in ctxw:
                ru = name
                break
        if ru:
            verb = _agree(ru, True) or "выросла"
            push(_family(ru), _mag(b, "%") - _mag(a, "%"), "%s %s с %s%% до %s%%" % (ru, verb, a, b))
    for m in _REDUCEN_RX.finditer(quote):
        if vd != digits_of(m.group(1)):
            continue
        num, tail = m.group(1), ws_norm(m.group(2))
        for en, ru in _EN_LEX:
            if en in tail:
                verb = _agree(ru, False)
                if verb:
                    push(_family(ru), _mag(num, "%"), "%s %s на %s%%" % (ru, verb, num))
                else:
                    push(_family(ru), _mag(num, "%"), "%s — на %s%% меньше" % (ru, num))
                break
    for m in _INCR_EN_RX.finditer(quote):
        if vd != digits_of(m.group(1)):
            continue
        num, tail = m.group(1), ws_norm(m.group(2))
        pre = ws_norm(quote[max(0, m.start() - 60):m.start()])
        for en, ru in _EN_LEX:
            if en in tail or en in pre:
                verb = _agree(ru, True)
                if verb:
                    push(_family(ru), _mag(num, "%"), "%s %s на %s%%" % (ru, verb, num))
                break
    for m in _REV_EN_RX.finditer(quote):
        if vd != digits_of(m.group(2)):
            continue
        kind, num, suf, noun = m.groups()
        ru_nom = {"revenue": "выручка", "sales": "продажи", "costs": "расходы",
                  "time": "время"}.get(ws_norm(noun))
        v_ru = {"recovered": "вернул", "saved": "сэкономил", "generated": "принёс",
                "unlocked": "дал", "boosted": "увеличил"}.get(ws_norm(kind))
        ru_gen = {"выручка": "выручки", "продажи": "продаж", "расходы": "расходов",
                  "время": "времени"}.get(ru_nom or "", "")
        suf_ru = {"k": "тыс", "m": "млн", "b": "млрд", "bn": "млрд",
                  "mln": "млн"}.get(ws_norm(suf or ""), "")
        if ru_gen and v_ru:
            push(_family(ru_nom), float(num or 0) * 60,
                 "%s $%s %s %s" % (v_ru, num, (suf_ru + " ").rstrip(), ru_gen))
    return out


def _headline_mechanism(case, head_text):
    """«за счёт X» — только подтверждённый evidence: поверхность из
    контрольного лексикона (с готовым родительным падежом), иначе дословная
    связка источника. AI/ML не повышаются: entry срабатывает лишь по
    реальному слову в evidence."""
    blob = textclean.clean(" ".join([case.get("implementation") or "",
                                     case.get("solution") or "",
                                     case.get("problem") or "",
                                     " ".join(case.get("results") or [])]))
    low = ws_norm(blob)
    head_low = ws_norm(head_text)
    for rx, gen in _MECH_LEX:
        if re.search(rx, low):
            core = ws_norm(gen).split(" ")[0]
            if core and core in head_low:
                continue  # механизм уже назван в самом результате — не тавтология
            return "за счёт " + gen
    m = _MECH_VERB_RX.search(blob)
    if m:
        whole = ws_norm(m.group(0))
        phrase = " ".join(re.findall(r"[\w'\-]{2,}", m.group(1))[:3])
        if not phrase or digits_of(phrase) or len(phrase) > 34:
            return ""
        if whole.startswith("благодаря"):
            cand = "благодаря " + phrase
        elif "помощью" in whole or "помощи" in whole:
            cand = "с помощью " + phrase
        else:
            cand = "за счёт " + phrase
        if ws_norm(phrase).split(" ")[0] in head_low:
            return ""
        return cand
    return ""


def _candidate_map(case):
    """value(очищ.) -> отсортированные качественные headline-конструкции этого
    значения. Один источник конструкций и для заголовка, и для блока «Цифры»."""
    m = {}
    for mtr in case.get("metrics") or []:
        val = textclean.clean((mtr.get("value") or "").strip())
        quote = textclean.clean((mtr.get("evidence") or {}).get("quote") or "")
        if not val or not quote:
            continue
        lst = [c for c in _result_candidates(val, quote) if not headline_issues(c["text"])]
        if lst:
            m.setdefault(val, []).extend(lst)
    for v in m:
        seen, uniq = set(), []
        for c in sorted(m[v], key=lambda c: (c["rank"], -c["mag"])):
            if c["text"] not in seen:
                seen.add(c["text"])
                uniq.append(c)
        m[v] = uniq
    return m


def _semantic_headline(case, comp, cmap=None):
    """-> строка заголовка (без «⚡» и без «Компания: ») или "". Каждая
    конструкция обязана пройти headline_issues(): в заголовок не попадает
    то, что не прошло бы и в публикацию."""
    cmap = cmap if cmap is not None else _candidate_map(case)
    title_digits = digits_of(ws_norm(case.get("source_title") or ""))
    cands, seen = [], set()
    for i, mtr in enumerate(case.get("metrics") or []):
        val = textclean.clean((mtr.get("value") or "").strip())
        for c in cmap.get(val, []):
            if c["text"] in seen:
                continue
            seen.add(c["text"])
            c["idx"] = i
            c["title"] = 1 if digits_of(val) and digits_of(val) in title_digits else 0
            cands.append(c)
    if not cands:
        return ""
    best = sorted(cands, key=lambda c: (c["rank"], -c["title"], -c["mag"], c["idx"]))[0]
    text = best["text"]
    mech = _headline_mechanism(case, text)
    if mech:
        trial = "%s — %s" % (text, mech)
        if len(re.findall(r"[\w'\-]{2,}", ws_norm(trial))) <= 13 and len(trial) <= 96 \
                and not headline_issues(trial):
            text = trial
    return text


def _head_body(line):
    """Сама смысловая часть заголовка из первой строки поста: без ведущих
    символов («⚡», markdown) и без префикса «Компания: »."""
    b = re.sub(r"^[^\wЁёА-Яа-яA-Za-z]+", "", (line or "").strip())
    m = re.match(r"^([^:\n]{2,48}?):\s+(.+)$", b, re.S)
    if m and len(re.findall(_WORD2, ws_norm(m.group(1)))) <= 4:
        return m.group(2)
    return b


def headline_issues(body):
    """Редакционный гейт заголовка: НЕ грамматический checker, а
    детерминированный стоп-лист мусорных структур — перечисление цифр через
    слэш, «сырая» пара со стрелкой, число без русского контекста, обрывок
    падежа без продолжения, начало с местоимения, суп из аббревиатур.
    Возвращает список ошибок (пусто = ок)."""
    errs = []
    b = ws_norm(body or "")
    if not b.strip():
        return errs
    if re.search(r"\d[\d.,]*\s*/\s*[-+\u2212]?\d", b) or \
            re.search(r"\d[\d.,]*[^\n]{0,25}?\s/\s*[-+\u2212]?\d", b):
        errs.append("headline: bare numbers separated by slashes")
    if "→" in b or "->" in b:
        errs.append("headline: raw metric pair — пишите «с X до Y» словами")
    has_num = bool(re.search(r"\d", b))
    if has_num and not re.search(r"[а-яё]{3,}", b):
        errs.append("headline: цифра без русского контекста")
    if _BAD_START_RX.match(b):
        errs.append("headline: начало с местоимения/вопросительного слова")
    if has_num and not _ANCHOR_VB_RX.search(b):
        toks = b.split(" ")
        for j, t in enumerate(toks):
            if not _OBLIG_RX.fullmatch(t.strip(".,;:!?«»%")):
                continue
            pre = [x.strip(".,;:!?") for x in toks[max(0, j - 2):j]]
            if any(p in _PREPS for p in pre):
                continue  # косвенный падеж легален: «+34% к выручке…»
            if j == 0 or any(re.search(r"\d", x) for x in toks[j + 1:j + 5]):
                errs.append("headline: обрывок падежа «%s…»" % t)
                break
    abbs = {w for w in re.findall(r"[A-ZА-ЯЁ]{2,6}", body or "")}
    if len(abbs) >= 2 and len(re.findall(r"[а-яё]{3,}", b)) < 2:
        errs.append("headline: суп из аббревиатур")
    return errs


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
    # заголовок и блок «Цифры» строятся одним смысловым механизмом из
    # evidence-конструкций; legacy «контекст+цифра» — только если он проходит
    # тот же гейт качества headline_issues()
    cmap = _candidate_map(case)
    hl_body = _semantic_headline(case, comp, cmap)
    if not hl_body:
        for v, c in used:
            cand = _short("%s %s" % (c, v), 90)
            if cand and not headline_issues(cand):
                hl_body = cand
                break
    if not hl_body:
        hl_body = "практический эффект автоматизации"
    headline = "%s: %s" % (comp, hl_body)

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
        shown = set()
        for v, c in used[:3]:
            if cmap.get(v):
                # у значения есть осмысленные конструкции: показываем лучшую
                # из ещё не показанных; повтор (тот же текст у другой метрики)
                # пропускаем — legacy-обрывок вместо него не печатаем
                cand = next((t["text"] for t in cmap[v] if t["text"] not in shown), None)
                if cand:
                    shown.add(cand)
                    lines.append("- " + _short(cand, 90))
                continue
            line = "- %s %s" % (_short(c, 60), v)
            if line not in shown:
                shown.add(line)
                lines.append(line)
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
    "СТРУКТУРА: заголовок строится по смыслу, а не по списку цифр: КТО + "
    "ЧТО ПРОИЗОШЛО (главный измеримый бизнес-результат) + ЗА СЧЁТО ЧЕГО "
    "(короткая причина, подтверждённая CASE). До 12 слов, цифры — словами в "
    "предложении: «CNS: выручка с покупателя выросла на 34% — за счёт "
    "повторных покупок», «доля клиентов с повторными покупками выросла с "
    "22,9% до 36%». ЗАПРЕЩЕНО в заголовке: перечисление цифр через слэш "
    "(«+56% / 16%»), стрелка «→» и пары вида «22,9% → 36%», обрывки в "
    "косвенном падеже без сказуемого («выручке на покупателя ARPPU»), "
    "заголовок из одной цифры, слова AI/ИИ/ML/нейросети — если в CASE нет "
    "тех же слов (не повышай уровень утверждений источника; «автоматические "
    "рассылки» остаётся рассылками). Далее: кто компания; "
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
    errors.extend(headline_issues(_head_body(first)))
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
    # заголовок не имеет права повышать уровень утверждения источника:
    # AI/ИИ/ML-формулировка допустима, только если то же слово есть в source/evidence
    hl = ws_norm(_head_body(next((l for l in (text or "").splitlines() if l.strip()), "")))
    srcb = ws_norm(source_text or "") + " " + ws_norm(
        json.dumps(case.get("evidence") or {}, ensure_ascii=False)) + " " + ws_norm(
        " ".join([case.get("implementation") or "", case.get("solution") or "",
                  case.get("source_title") or ""]))
    if re.search(r"\bai\b|\bии\b|нейросет|искусственн", hl) and \
            not re.search(r"\bai\b|artificial|нейросет|искусственн|\bии\b", srcb):
        errors.append("headline: AI-claim not backed by source")
    if re.search(r"\bml\b|машинн", hl) and \
            not re.search(r"\bml\b|machine|машинн", srcb):
        errors.append("headline: ML-claim not backed by source")
    ok_e, err_e = editorial_check(text)
    errors.extend(err_e)
    return (not errors), errors
