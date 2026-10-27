# -*- coding: utf-8 -*-
from research.pets_content_quality import analyse_posts, label_post


def test_medical_topic_is_not_auto_eligible_for_original_post():
    result = label_post({"text_excerpt": "У кошки блохи: когда нужен ветеринарный врач"})
    assert result["quality_label"] == "useful_theme"
    assert result["veterinary_review_required"] is True
    assert result["eligible_as_original_topic"] is False


def test_promo_and_meta_posts_are_not_counted_as_topics():
    posts = [
        {"text_excerpt": "Скидка 20%: купите корм сегодня"},
        {"text_excerpt": "Голосуйте за канал в конкурсе"},
        {"text_excerpt": "Как выбрать игрушку для активной собаки"},
    ]
    result = analyse_posts(posts)
    assert result["labels"] == {"advertising_or_promo": 1, "irrelevant_or_meta": 1, "useful_theme": 1}
    assert result["eligible_original_topic_count"] == 1


def test_near_identical_useful_excerpt_is_marked_as_repeat():
    text = "Как выбрать безопасную игрушку для активной домашней собаки на прогулке"
    result = analyse_posts([{"text_excerpt": text}, {"text_excerpt": text + "!"}])
    assert result["labels"] == {"useful_theme": 1, "repeat_or_near_duplicate": 1}
    assert result["eligible_original_topic_count"] == 1
