# -*- coding: utf-8 -*-
"""case_pipeline.evidence — deterministic evidence validator.

AI НЕ может незаметно добавить факт: каждая существенная строка CASE обязана
буквально присутствовать в исходном извлечённом тексте (ws-нормализованно),
каждое число обязано присутствовать в тексте. Нарушение => INVALID => материал
не публикуется автоматически.
"""
import re

from .utils import ws_norm, extract_numbers

QUOTE_MIN = 30          # короткие «цитаты» ничего не доказывают


def quote_in_source(quote, source_text):
    q = ws_norm(quote)
    if len(q) < QUOTE_MIN:
        return False
    return q in ws_norm(source_text)


def numbers_grounded(source_text, *texts):
    """Все числовые токены из проверяемых текстов должны встречаться в
    исходнике (после ws-нормализации)."""
    src_nums = extract_numbers(ws_norm(source_text))
    src_norm = ws_norm(source_text)
    for t in texts:
        for tok in extract_numbers(t or ""):
            if tok in src_nums:
                continue
            # токен мог склеиться с единицей измерения иначе: ищем как подстроку
            core = re.sub(r"[^\d.,\-+]", "", tok)
            if core and core in src_norm:
                continue
            return False
    return True


def validate_case(case, source_text):
    """Проверяет весь CASE против исходного текста. -> (ok, list[str] errors)."""
    errors = []
    ev = case.get("evidence") or {}
    checks = []
    for key in ("problem", "implementation"):
        q = (ev.get(key) or {}).get("quote") or ""
        if q:
            checks.append((key, q))
        elif case.get(key):
            checks.append((key, case.get(key)))
    for r in ev.get("results") or []:
        if isinstance(r, dict) and r.get("quote"):
            checks.append(("results", r["quote"]))
    for q in ev.get("metrics") or []:
        checks.append(("metrics", q))
    for sec in (case.get("source_excerpt"), case.get("source_title")):
        pass  # excerpt — сам по себе цитата, проверим отдельно ниже

    for name, q in checks:
        if not quote_in_source(q, source_text):
            errors.append("quote not found in source [%s]: %r" % (name, q[:70]))

    excerpt = case.get("source_excerpt") or ""
    if excerpt and not quote_in_source(excerpt[:200], source_text):
        errors.append("source_excerpt not verbatim")

    # все существенные поля + метрики: числа заземлены в исходнике
    claim_texts = [case.get("problem", ""), case.get("implementation", ""),
                   " ".join(case.get("results") or [])]
    for m in case.get("metrics") or []:
        claim_texts.append((m.get("evidence") or {}).get("quote", "") + " " + m.get("value", ""))
    if case.get("economic_effect"):
        claim_texts.append(case["economic_effect"])
    if not numbers_grounded(source_text, *claim_texts):
        bad = [t for t in claim_texts
               if not all(tok in extract_numbers(ws_norm(source_text)) or
                          re.sub(r"[^\d.,\-+]", "", tok) in ws_norm(source_text)
                          for tok in extract_numbers(t))]
        errors.append("numbers not grounded in source: %s" % (bad[:1],))

    company = (case.get("company_name") or "").strip()
    if company:
        cw = ws_norm(company).split("-")[0].split(" ")[0]
        if cw and cw not in ws_norm(source_text) and cw not in ws_norm(case.get("source_title", "")):
            errors.append("company not present in source: %s" % company)
    return (not errors), errors
