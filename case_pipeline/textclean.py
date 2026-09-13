# -*- coding: utf-8 -*-
"""case_pipeline.textclean — нейтрализация HTML-артефактов в финальном тексте.

Типовые артефакты извлечения (observed in production):
  * HTML-сущности (&lt;, &amp;, &nbsp; ...) и теги (<br>, </b>);
  * операторные '<'/'>' из текста источника: "ДРР <16%";
  * сломанные склейки после strip-ов: "<16%ДРР", "16%ДРР" (нет пробела).
clean() — безопасная нормализация (разъединение склеек, операторы -> слова);
has_artifacts() — жёсткий гейт: остатки, которые нельзя починить
детерминированно, блокируют публикацию (review).
"""
import html
import re

TAG_RX = re.compile(r"</?[A-Za-z!][^<>\n]{0,60}>")
ENTITY_RX = re.compile(r"&(?:[A-Za-z]{2,10}|#\d{1,5}|x[0-9A-Fa-f]{1,5});")
# склейка: буква/цифра прилипла к оператору '<' '>'
GLUE_ANGLE_RX = re.compile(r"(?<=[^\W\d_])(?=[<>])|(?<=[<>])(?=[^\W\d_])")
# '%' прилип к следующему слову: "16%ДРР" -> "16% ДРР"
GLUE_PCT_RX = re.compile(r"%(?=[^\W\d_])")
# кириллическая межсловная склейка (след strip-а тегов/списков): "заказДРР"
GLUE_CASE_RX = re.compile(r"(?<=[а-яё])(?=[А-ЯЁ])")
# '<' '>' как операторы сравнения перед числом -> русские слова
CMP_NUM_RX = re.compile(r"(?:^|(?<=[\s(«\"'—,:;]))([<>])\s*(?=[\d+−-])")


def _cmp_sub(m):
    return "менее " if m.group(1) == "<" else "более "


def clean(text):
    """Детерминированная нормализация: сущности, теги, склейки, операторы."""
    if not text:
        return text or ""
    t = html.unescape(text)
    t = TAG_RX.sub("", t)
    t = GLUE_ANGLE_RX.sub(" ", t)
    t = GLUE_PCT_RX.sub("% ", t)
    t = GLUE_CASE_RX.sub(" ", t)
    t = CMP_NUM_RX.sub(_cmp_sub, t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def has_artifacts(text):
    """Остаточные артефакты (к применять после clean): живые '<'/'>', теги,
    сущности, склейки '%слово' — публикация такого запрещена."""
    t = text or ""
    if TAG_RX.search(t) or ENTITY_RX.search(t):
        return True
    if re.search(r"%(?=[^\W\d_])", t):          # "16%ДРР"
        return True
    if "<" in t or ">" in t:                    # любая живая угловая скобка
        return True
    return False
