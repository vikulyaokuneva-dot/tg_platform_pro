# -*- coding: utf-8 -*-
"""Качество заголовков Telegram-кейсов (пост-разбор production-кейса CNS
https://mindbox.ru/journal/cases/cns/ , где опубликовался мусор
«⚡ CNS: выручке на покупателя ARPPU 22,9%»).

Заголовок строится из смысла (КТО + главный измеримый результат +
подтверждённый механизм), а не из метрик[:3]. Данные кейсов — реальные
evidence-цитаты выборки. Тесты не требуют точной строки, где допустимы
равноценные варианты: проверяются бизнес-семья цифры, наличие контекста,
запрет сырых пар/обрывков падежа и запрет неподтверждённых AI/ML-claim.
"""
import re

from case_pipeline import postgen

# --- реальный CNS-кейс (field-строки и quotes дословные из source) -----------
CNS = {
    "company_name": "CNS",
    "problem": "Например, создал таблицу со статусами задач, напоминал о дедлайнах и подгонял разработку.",
    "implementation": "В кейсе — как растят ARPPU и долю клиентов с повторными покупками и какие механики помогли окупить платформу в первый месяц после их запуска.",
    "solution": "Для этого внедрили Mindbox, запустили автоматические рассылки, программу лояльности и стали вести аудиторию на более конверсионные страницы с помощью попапов.",
    "results": ["22,9 → 36%доля клиентов с повторными покупками"],
    "technology": [],
    "source_url": "https://mindbox.ru/journal/cases/cns/",
    "source_domain": "mindbox.ru",
    "source_title": "+34% к средней выручке на покупателя. Как бренд сумок CNS за год построил маркетинг удержания - Журнал Mindbox",
    "economic_effect": "",
    "metrics": [
        {"value": "+34%", "meaning": "", "evidence": {"quote":
            "ыми покупками и какие механики помогли окупить платформу в первый месяц после их запуска. +34% к средней выручке на покупателя. Как бренд сумок CNS"}},
        {"value": "22,9%", "meaning": "", "evidence": {"quote":
            "+34% к средней выручке на покупателя (ARPPU) 22,9% → 36% доля клиентов с повторными покупками+30% к общей выручке"}},
        {"value": "36%", "meaning": "", "evidence": {"quote":
            "+34% к средней выручке на покупателя (ARPPU) 22,9% → 36% доля клиентов с повторными покупками+30% к общей выручке"}},
        {"value": "+30%", "meaning": "", "evidence": {"quote":
            "% к средней выручке на покупателя (ARPPU) 22,9% → 36% доля клиентов с повторными покупками+30% к общей выручке"}},
        {"value": "19,8%", "meaning": "", "evidence": {"quote":
            "к общей выручке - ×4,3выручка от CRM‑маркетинга - 5,9 → 19,8%доля CRM‑канала в общей выручке - +34%к средней выручке"}},
    ],
}


def _first(text):
    return text.splitlines()[0]


def _head(case):
    return _first(postgen.render_template(case))


# ---------- 1. главный регресс: непригодный заголовок рождается в render ----
def test_cns_head_is_business_sentence_with_mechanism():
    h = _head(CNS)
    assert h.startswith("⚡ CNS:")
    # главный результат — revenue-семья с цифрой 34 (не лист метрик и не baseline)
    assert re.search(r"выручк\w*.{0,35}34|34.{0,45}выручк", h), h
    # механизм — из evidence (равноценные варианты допустимы, точной строки нет)
    assert re.search(r"повторн|рассыл|лояльн|попап|удержания|CRM", h), h
    assert "22,9" not in h                      # baseline-пара в заголовок не идёт
    assert "→" not in h and "ARPPU" not in h
    assert not postgen.headline_issues(postgen._head_body(h))


def test_old_production_headline_rejected_as_oblique_fragment():
    # ровно тот заголовок, что ушёл в прод 13.09
    bad = "выручке на покупателя ARPPU 22,9%"
    errs = postgen.headline_issues(bad)
    assert errs and any("обрывок" in e for e in errs), errs


def test_bare_baseline_and_term_soup_rejected():
    assert any("без русского контекста" in e for e in postgen.headline_issues("22,9%"))
    assert postgen.headline_issues("ARPPU CTOR CRM")
    # склейка из сырой строки таблицы — тоже мусор
    assert postgen.headline_issues("22,9% → 36% доля клиентов")


def test_baseline_pair_keeps_context():
    # если в кейсе только пара «было → стало» — она обязана стать предложением
    case = dict(
        CNS,
        implementation="", solution="", problem="", results=[],
        source_title="",
        metrics=[{"value": "22,9%", "meaning": "", "evidence": {"quote":
            "22,9% → 36% доля клиентов с повторными покупками"}}],
    )
    h = _head(case)
    assert "доля" in h and "22,9" in h and "36" in h
    assert "→" not in h and re.search(r"с 22,9% до 36%|— с 22,9% до 36%", h), h
    assert not postgen.headline_issues(postgen._head_body(h))


def test_mechanism_never_upgraded_to_ai_without_source():
    # в evidence только «автоматические рассылки» — AI в заголовок не появится
    case = dict(
        CNS,
        implementation="Запустили автоматические рассылки по сегментам базы.",
        solution="", problem="", results=[],
        metrics=[{"value": "+34%", "meaning": "", "evidence": {"quote":
            "итог: +34% к выручке с покупателя в первый месяц"}}],
    )
    h = _head(case)
    assert "34" in h and re.search(r"рассыл", h), h
    assert not re.search(r"\bAI\b|ИИ|нейросет|искусственн|\bML\b", h, re.I)


# ---------- 2. гейт на неподтверждённый AI/ML-claim в заголовке -------------
SRC_NO_AI = ("Компания CNS: выручка с покупателя выросла на 34% после запуска "
             "автоматических рассылок и программы лояльности.")
CASE_MIN = {"company_name": "CNS", "problem": "", "implementation":
            "CNS запустила автоматические рассылки по сегментам.",
            "results": ["выручка с покупателя выросла на 34%"],
            "metrics": [], "evidence": {}, "source_title": "",
            "source_url": "https://mindbox.ru/journal/cases/cns/"}


def test_validate_rejects_ungrounded_ai_claim_in_headline():
    bad = ("CNS: выручка с покупателя выросла на 34% — благодаря AI\n"
           "Компания CNS запустила автоматические рассылки, и выручка "
           "с покупателя выросла на 34%.")
    ok, errors = postgen.validate_post(bad, CASE_MIN, SRC_NO_AI)
    assert not ok and any("AI-claim" in e for e in errors), errors


def test_validate_allows_source_wording():
    good = ("CNS: выручка с покупателя выросла на 34% — за счёт рассылок\n"
            "Компания CNS запустила автоматические рассылки, и выручка "
            "с покупателя выросла на 34%.")
    ok, errors = postgen.validate_post(good, CASE_MIN, SRC_NO_AI)
    assert ok, errors


# ---------- 3. соседние кейсы не сломаны ------------------------------------
def test_chitay_headline_revenue_delta_not_digits():
    case = dict(
        CNS,
        company_name="Читай-город",
        problem="Часть рекламного бюджета расходовалась неэффективно.",
        implementation="ML-ретаргетинг сегментирует аудиторию по вероятности покупки и корректирует ставки.",
        solution="",
        results=["Выручка с клика выросла на +56%"],
        source_title="Как «Читай-город» рост выручки собрал",
        metrics=[{"value": "+56%", "meaning": "", "evidence": {"quote":
            "В рекламных кампаниях Яндекс Директа:+56% к выручке с клика+1,4 п. п. к конверсии в заказДРР не выше 16%"}}],
    )
    h = _head(case)
    assert "56" in h and "выручке с клика" in h and "→" not in h
    assert re.search(r"ML-ретаргетинг|ML-сегмент", h)  # источник говорит ML — можно
    assert not postgen.headline_issues(postgen._head_body(h))


def test_sweetlavka_and_mifa_legacy_quality_ok():
    lavka = dict(
        CNS, company_name="Sweet Lavka",
        implementation="Бот ВКонтакте заменил авторизационные SMS.",
        solution="", problem="", results=[], source_title="",
        metrics=[{"value": "+10%", "meaning": "", "evidence": {"quote":
            "механики возвращают к повторным покупкам - +10%к общей выручке во время игр"}}],
    )
    h = _head(lavka)
    assert "10" in h and "выручке" in h and not postgen.headline_issues(postgen._head_body(h))

    mifa = dict(
        CNS, company_name="МИФа",
        implementation="Контент-менеджер собирает одно письмо за 30 минут — без кода.",
        solution="", problem="", results=["собирает одно письмо за 30 минут"],
        source_title="",
        metrics=[{"value": "30 минут", "meaning": "", "evidence": {"quote":
            "Теперь контент-менеджер собирает одно письмо за 30 минут"}}],
    )
    h = _head(mifa)
    assert "30 минут" in h and not postgen.headline_issues(postgen._head_body(h))


def test_metric_list_and_slash_headlines_still_rejected():
    # поведение гейта E сохранено: список цифр через слэш — ошибка и в gate,
    # и в editorial_check всего поста
    text = ("Читай-город: +56% / +1,4 п. п. / 16%\n"
            "Компания оптимизировала рекламу и выросла на +56%.")
    ok, errors = postgen.editorial_check(text)
    assert not ok and any("slash" in e for e in errors), errors
