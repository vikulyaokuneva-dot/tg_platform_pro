# -*- coding: utf-8 -*-
"""Russian Language Guard: RU PASS / EN FAIL / бренды-URL допустимы / retry."""
from case_pipeline import langguard

RU = ("Компания Ромашка сократила расходы на 45% за счёт автоматизации заявок "
      "в CRM. Данные передаются в систему без ручного переноса. Источник: "
      "https://mindbox.ru/journal/cases/romashka/")
EN = ("Acme Corp reduced processing costs by 45 percent thanks to AI powered "
      "workflow automation across its customer relationship management and "
      "support systems according to the annual report published last quarter "
      "by the company leadership team during the fiscal year review.")
RU_BRANDS = ("Salesforce внедрила Agentforce для обработки обращений клиентов, "
             "а IBM сократила время ответа на 30 процентов. Команда использовала "
             "Slack и Jira для координации. Источник: https://ibm.com/case-studies/acme")
EN_DOMINANT = ("The company implemented a new automation platform and trained "
               "employees. Кроме того, сократили расходы. The results were "
               "presented to stakeholders and the board approved further "
               "investment in the infrastructure and support teams.")


class _Translate:
    """Тестовый провайдер: complete() возвращает заранее заданный ответ."""
    available = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete(self, msgs):
        self.calls += 1
        return self.reply


def test_ru_pass():
    ok, why = langguard.guard(RU)
    assert ok, why


def test_en_fail():
    ok, why = langguard.guard(EN)
    assert not ok and "english-dominant" in why


def test_ru_with_latin_brands_and_url_pass():
    ok, why = langguard.guard(RU_BRANDS)
    assert ok, why


def test_english_dominant_mixed_fail():
    ok, _ = langguard.guard(EN_DOMINANT)
    assert not ok


def test_empty_fail():
    assert not langguard.guard("")[0]
    assert not langguard.guard("   ")[0]


def test_retry_once_then_pass():
    prov = _Translate(RU + "\n\nДополнительное русское предложение с выводом для бизнеса.")
    final, ok, note = langguard.ensure_russian(EN, prov)
    assert ok and prov.calls == 1
    assert "Ромашка" in final or "русск" in final  # взят перевод
    assert "45" in final


def test_second_fail_returns_not_ok():
    prov = _Translate(EN)  # «перевод» снова английский
    final, ok, note = langguard.ensure_russian(EN, prov)
    assert not ok and prov.calls == 1
    assert final == EN  # исходный текст не подменён


def test_retry_inventing_numbers_rejected():
    prov = _Translate(RU.replace("45%", "973%") + " Ещё одно русское предложение для объёма текста.")
    final, ok, note = langguard.ensure_russian(EN, prov)
    assert not ok and "invented" in note


def test_no_provider_no_retry():
    final, ok, note = langguard.ensure_russian(EN, None)
    assert not ok and final == EN
