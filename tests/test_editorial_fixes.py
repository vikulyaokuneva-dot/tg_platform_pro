# -*- coding: utf-8 -*-
"""Регрессии по post-review кейса «Читай-город» (13.09):
1) заголовок-перечисление голых цифр «+56% / +1,4 п. п. / 16%» -> запрещён;
2) HTML-артефакт «<16%ДРР» (скобка/склейка) -> не публикуется, чинится в «менее 16% ДРР»;
3) HTML-теги и сущности -> артефакт;
4) «Цифры»: показатель, не использованный в тексте, -> не выводится;
5) перечень сервисов в «Что автоматизировали» -> формулировка цепочкой-механикой.
"""
from case_pipeline import postgen, textclean
import re

SRC = ("«Читай-город» обрабатывал данные и корректировал ставки. "
       "Выручка с клика выросла на +56%, конверсия +1,4 п. п., ДРР <16%, "
       "часть бюджета шла неэффективно.")

CASE = {
    "company_name": "Читай-город",
    "problem": "Часть рекламного бюджета расходовалась неэффективно.",
    "implementation": "Salesforce, Slack, Zapier",
    "results": ["Выручка с клика выросла на +56%, ДРР <16%"],
    "metrics": [
        {"value": "+56%", "meaning": "", "evidence": {"quote": "выросла на +56%"}},
        {"value": "+1,4 п. п.", "meaning": "", "evidence": {"quote": "конверсия +1,4 п. п."}},
        {"value": "16%", "meaning": "", "evidence": {"quote": "ДРР <16%"}},
    ],
    "technology": ["ML-сегменты"],
    "source_url": "https://mindbox.ru/journal/cases/chtay-gorod-ml/",
    "source_domain": "mindbox.ru",
    "economic_effect": "",
}


# ---------- 2/3. textclean: артефакты ----------
def test_clean_lt_glued_artifact():
    assert textclean.clean("<16%ДРР") == "менее 16% ДРР"
    assert textclean.clean("ДРР<16%") == "ДРР менее 16%"
    assert textclean.clean("конверсии в заказДРР") == "конверсии в заказ ДРР"


def test_clean_html_entities_and_tags():
    out = textclean.clean("ДРР &lt;16%<br>и &amp; ещё")
    assert "<" not in out and ";" not in out and "br" not in out
    assert "менее 16%" in out and "ещё" in out


def test_has_artifacts_gate():
    assert textclean.has_artifacts("эффект <b>роста</b>")
    assert textclean.has_artifacts("значение &lt;16%")
    assert textclean.has_artifacts("ДРР 16%ДРР")        # сломанная склейка
    assert not textclean.has_artifacts("ДРР менее 16%")  # после clean — чисто


# ---------- 1. заголовок с несколькими цифрами через слэш ----------
def test_headline_number_slash_list_rejected():
    bad = ("Читай-город: +56% / +1,4 п. п. / 16%\n"
           "Компания оптимизировала рекламу и выросла на +56%.")
    ok, errors = postgen.validate_post(bad, CASE, SRC)
    assert not ok and any("slash" in e for e in errors)


def test_headline_contextual_numbers_allowed():
    good = ("Читай-город: +56% к выручке с клика и ДРР менее 16%\n"
            "Компания пересчитывала ставки, ДРР держался на уровне 16%, "
            "выручка выросла на +56%.")
    ok, errors = postgen.validate_post(good, CASE, SRC)
    assert ok, errors


# ---------- 4. Цифры вне текста ----------
def test_template_headline_not_bare_slash_list():
    text, mode, lang_ok = postgen.render_post(CASE, SRC, provider=None)
    assert mode == "template" and lang_ok
    first = text.splitlines()[0]
    assert " / " not in first                      # без перечисления цифр
    head = first.split(":", 1)[-1]
    assert re.search(r"[А-Яа-яЁё]{5,}", head)      # есть слово-контекст


def test_digits_only_used_with_context():
    # «голое» число, не использованное в тексте, в блок Цифры не попадает:
    case_bare = dict(CASE, metrics=[{"value": "99%",
                                     "evidence": {"quote": "99%"}}])
    text2, _, _ = postgen.render_post(case_bare, SRC, provider=None)
    assert "99%" not in text2                     # нет контекста -> не выводим
    # использованное с контекстом — выходит отдельной строкой
    text, _, _ = postgen.render_post(CASE, SRC, provider=None)
    digits = [l for l in text.splitlines() if l.startswith("- ")]
    assert digits and all(re.search(r"[А-Яа-яЁё]{3,}", l) for l in digits)


def test_editorial_check_digits_absent_from_body():
    text = ("Заголовок про рост\nТекст поста про автоматизацию без цифр.\n"
            "Цифры:\n- выдуманное 77%\n")
    ok, errors = postgen.editorial_check(text)
    assert not ok and any("digits block" in e for e in errors)


# ---------- 5. список сервисов -> механика ----------
def test_service_list_becomes_chain():
    assert "→" in postgen._mechanics("Salesforce, Slack, Zapier")
    assert "данные" in postgen._mechanics("Salesforce, Slack, Zapier")
    # осмысленная механика остаётся как есть
    mech = "данные → ML-модель → ставка в Директе"
    assert postgen._mechanics(mech) == mech


def test_template_implementation_chain_wording():
    text, _, _ = postgen.render_post(CASE, SRC, provider=None)
    impl_line = [l for l in text.splitlines() if "Что автоматизировали" in l][0]
    assert "→" in impl_line and "данные" in impl_line
