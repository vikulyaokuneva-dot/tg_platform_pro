# -*- coding: utf-8 -*-
"""Контролируемые хэштеги: словарь, количество, санитизация, вставка в пост."""
from case_pipeline import hashtags


def test_build_case_tags_controlled():
    tags = hashtags.build("case", "внедрили CRM salesforce, обрабатывали заявки", "Mindbox")
    assert tags[0] == "#Кейс"
    assert "#Mindbox" in tags
    assert 3 <= len(tags) <= 5
    ok, errors = hashtags.validate(tags)
    assert ok, errors


def test_news_type_tag():
    tags = hashtags.build("news", "нейросеть автоматизировала отчётность", "Сбер")
    assert tags[0] == "#НовостьДня"
    assert "#Сбер" in tags


def test_domain_detection_priority_and_limit():
    doms = hashtags.detect_domains("рекламные кампании и трафик, плюс склад и доставка")
    assert doms[0] == "#Маркетинг"
    assert len(doms) <= 2


def test_no_domain_fallback():
    tags = hashtags.build("case", "абсолютно непонятный текст без ключевых слов", "AcmeCorp")
    assert hashtags.DOMAIN_FALLBACK in tags
    ok, errors = hashtags.validate(tags)
    assert ok, errors


def test_company_sanitized_no_garbage():
    assert hashtags.company_tag("IBM") == "#IBM"
    assert hashtags.company_tag("  Озон  ") == "#Ozon"
    assert hashtags.company_tag("!!!") is None
    assert hashtags.company_tag("a") is None
    assert hashtags.company_tag("") is None
    assert hashtags.company_tag("ЗапредельноДлинноеНазваниеКомпанииКотороеНеПоместитсяВТег") is None


def test_own_project_only_explicit():
    tags = hashtags.build("case", "заявки crm", "Ромашка", own="#AIDirectorWB")
    assert "#AIDirectorWB" in tags
    tags2 = hashtags.build("case", "заявки crm", "Ромашка")
    assert "#AIDirectorWB" not in tags2  # сам не появляется


def test_apply_to_post_replaces_hashtag_line():
    post = "Текст поста\n\nИсточник: https://x.ru/a\n#AI #автоматизация #кейсбизнеса"
    out = hashtags.apply_to_post(post, ["#Кейс", "#CRM", "#IBM"])
    assert out.endswith("#Кейс #CRM #IBM")
    assert "#автоматизация" not in out
    assert "Источник:" in out


def test_max_five_tags():
    tags = hashtags.build("case", "реклама продажи crm документы hr логистика", "IBM",
                          own="#ShawarmaLab")
    assert len(tags) <= 5


def test_validate_rejects_garbage_and_count():
    ok, errors = hashtags.validate(["#Кейс", "#Мусор!"])
    assert not ok
    ok, errors = hashtags.validate(["#Кейс", "#CRM"])  # < 3
    assert not ok and any("count" in e for e in errors)
