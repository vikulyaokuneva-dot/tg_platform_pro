# -*- coding: utf-8 -*-
"""Пост-генерация и финальный security-гейт поста."""
from case_pipeline import postgen

CASE = {
    "company_name": "Ромашка",
    "problem": "Ромашка обрабатывала заявки вручную 4 часа в день.",
    "implementation": "Ромашка подключила AI-обработку заявок в Telegram.",
    "results": ["время обработки сократилось на 45%"],
    "metrics": [{"value": "45%", "evidence": {"quote": "сократилось на 45%"}}],
    "technology": ["Telegram"],
    "source_url": "https://mindbox.ru/journal/cases/romashka/",
    "economic_effect": "",
    "source_domain": "mindbox.ru",
}
SRC = ("Ромашка обрабатывала заявки вручную 4 часа в день. "
       "Ромашка подключила AI-обработку заявок в Telegram. "
       "время обработки сократилось на 45%")


def test_template_structure():
    text, mode, lang_ok = postgen.render_post(CASE, SRC, provider=None)
    assert mode == "template" and lang_ok
    assert "Ромашка" in text
    assert "❗️" in text and "🔧" in text and "📈" in text
    assert "Источник:" in text and CASE["source_url"] in text
    # контролируемый словарь вместо свободных тегов
    assert "#Кейс" in text and "#Продажи" in text and "#Ромашка" in text
    assert "#автоматизация" not in text  # legacy-набор больше не используется
    assert "💼" in text  # CTA-блок


def test_validate_ok():
    text, _, _ = postgen.render_post(CASE, SRC)
    ok, errors = postgen.validate_post(text, CASE, SRC)
    assert ok, errors


def test_invented_number_rejected():
    bad = text_bad = ("Ромашка: рост 973%\n❗️ Проблема: «Ромашка обрабатывала заявки вручную»\n"
                      "💼 Подобную схему можно собрать и под небольшой бизнес.\n")
    ok, errors = postgen.validate_post(bad, CASE, SRC)
    assert not ok and any("numbers" in e for e in errors)


def test_hype_rejected():
    bad = ("Ромашка: революционный прорыв автоматизации!\n"
           "Ромашка подключила AI-обработку заявок в Telegram с результатом 45%.")
    ok, errors = postgen.validate_post(bad, CASE, SRC)
    assert not ok and any("hype" in e for e in errors)


def test_company_missing_rejected():
    bad = "Сократили ручной ввод на 45%. Автоматизация заявки в Telegram за секунды."
    ok, errors = postgen.validate_post(bad, CASE, SRC)
    assert not ok and any("company" in e for e in errors)


def test_cta_selection_domain():
    assert postgen.pick_cta(CASE) is postgen.CTA_SALES  # заявки/CRM-лексика
    other = dict(CASE, problem="Ticket routing in support", implementation="helpdesk AI")
    assert postgen.pick_cta(other) is postgen.CTA_SUPPORT
