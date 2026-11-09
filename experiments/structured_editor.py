# -*- coding: utf-8 -*-
"""Isolated A/B experiment for a GigaChat structured editorial response.

Nothing in this module imports or writes production queues, Telegram/VK clients
or SQLite storage.  The source library below intentionally contains just three
pre-verified briefs.  It is therefore an experiment in editing, not a general
web-search implementation.

Run a safe source/preview check:
    python -m experiments.structured_editor --channel agro --topic "Уход за плодовыми деревьями перед зимой" --dry-run

A paid call is impossible unless both --live and --allow-paid-gigachat are
provided and GIGACHAT_API_KEY is available in the process environment.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


CHANNELS = ("agro", "pets", "ai_automation")
TOPIC_ALIASES = {
    "agro": {"уход за плодовыми деревьями перед зимой"},
    "pets": {"как организовать спокойную прогулку с собакой"},
    "ai_automation": {"пример применения ии для обработки клиентских обращений"},
}


class Source(BaseModel):
    id: str
    title: str
    url: str
    claims: list[str] = Field(min_length=1)


class Fact(BaseModel):
    id: str
    source_id: str
    text: str


class FactualBrief(BaseModel):
    """A deliberately small, source-traceable editorial input."""

    channel: Literal["agro", "pets", "ai_automation"]
    topic: str
    category: str
    audience: str
    scope_note: str
    permitted_conclusions: list[str]
    forbidden_conclusions: list[str]
    sources: list[Source] = Field(min_length=1)
    facts: list[Fact] = Field(min_length=2)

    @property
    def source_ids(self) -> set[str]:
        return {source.id for source in self.sources}

    def source_text(self) -> str:
        return "\n".join(fact.text for fact in self.facts)


class StructuredDraft(BaseModel):
    """Native GigaChat JSON Schema contract for experiment B."""

    title: str = Field(min_length=10, max_length=140, description="Русский заголовок без служебных данных")
    body: str = Field(min_length=120, max_length=3200, description="Оригинальный русский текст поста")
    category: str = Field(description="Категория строго из factual brief")
    source_ids: list[str] = Field(min_length=1, description="IDs использованных источников из factual brief")
    image_search_query: str = Field(min_length=4, max_length=180, description="Нейтральный запрос для поиска подходящей фотографии")
    editorial_notes: str = Field(max_length=500, description="Краткие редакционные оговорки, не для читателя")

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("source_ids must be unique")
        if not cleaned:
            raise ValueError("source_ids must not be empty")
        return cleaned


def verified_briefs() -> dict[str, FactualBrief]:
    """Three factual briefs, with public primary/authoritative sources.

    The AGRO brief deliberately has a temperate/cold-climate scope: weather,
    soil and cultivar still require a local check.  The code must not convert
    this into a universal calendar prescription.
    """
    agro = FactualBrief(
        channel="agro",
        topic="Подготовка плодовых деревьев к зиме",
        category="seasonal_gardening",
        audience="владельцы плодовых деревьев в умеренном или холодном климате",
        scope_note=(
            "Только для осеннего периода до промерзания почвы в умеренном/холодном климате. "
            "Сроки зависят от региона, фактической погоды, вида дерева и состояния почвы; "
            "не давать универсальные календарные даты, дозировки или советы по химической защите."
        ),
        permitted_conclusions=[
            "Оценить осеннюю сухость почвы и полить до её промерзания, если это уместно.",
            "Защитить молодые или тонкокорые стволы светлым физическим материалом.",
            "Учитывать риск повреждения грызунами и не прижимать мульчу к стволу.",
        ],
        forbidden_conclusions=[
            "Не обещать зимовку или урожай.",
            "Не называть фиксированные даты, нормы полива, сорта или препараты.",
            "Не применять советы за пределами указанного климата без местной проверки.",
        ],
        sources=[
            Source(
                id="agro_umn_winter_care",
                title="UMN Extension — Planting and transplanting trees and shrubs: winter care",
                url="https://extension.umn.edu/garden-and-home/yard-and-garden/gardening-in-minnesota/planting-and-transplanting-trees-and-shrubs",
                claims=[
                    "Осенью полив уменьшают в начале сезона и проводят обильный полив поздней осенью непосредственно перед промерзанием почвы.",
                    "Поздний интенсивный полив и азотное удобрение могут стимулировать поздний рост, поэтому их не используют для такого стимулирования.",
                    "Физическая защита вокруг ствола помогает снизить зимнее повреждение животными.",
                ],
            ),
            Source(
                id="agro_umn_winter_protection",
                title="UMN Extension — Protecting trees and shrubs in winter",
                url="https://extension.umn.edu/es/node/10431",
                claims=[
                    "При сухой осени источник рекомендует полить растения до промерзания почвы.",
                    "Светлые защитные материалы на молодых стволах отражают солнце и снижают риск солнечных повреждений коры.",
                    "Мульчу оставляют на расстоянии от ствола, а не укладывают вплотную к нему.",
                ],
            ),
        ],
        facts=[
            Fact(id="agro_f1", source_id="agro_umn_winter_care", text="Если осень сухая и почва ещё не промёрзла, поздний обильный полив рассматривают с учётом местной погоды и влажности почвы."),
            Fact(id="agro_f2", source_id="agro_umn_winter_care", text="Не стоит стимулировать поздний нежный рост интенсивным поливом или азотным удобрением в начале осени."),
            Fact(id="agro_f3", source_id="agro_umn_winter_protection", text="Молодым и тонкокорым деревьям может требоваться светлая физическая защита ствола от зимнего солнца."),
            Fact(id="agro_f4", source_id="agro_umn_winter_protection", text="Защита от грызунов и расстояние между мульчей и стволом помогают снизить риск повреждений."),
        ],
    )
    pets = FactualBrief(
        channel="pets",
        topic="Как организовать спокойную прогулку с собакой",
        category="pet_care",
        audience="владельцы домашних собак без острой поведенческой или медицинской проблемы",
        scope_note=(
            "Это бытовая тренировка, а не ветеринарная или поведенческая диагностика. "
            "При боли, выраженном страхе, агрессии или угрозе безопасности нужна очная помощь квалифицированного специалиста."
        ),
        permitted_conclusions=[
            "Поощрять спокойное поведение и свободный поводок.",
            "Начинать с коротких отрезков и постепенно усложнять среду.",
            "Давать собаке безопасные паузы на обнюхивание как часть прогулки.",
        ],
        forbidden_conclusions=[
            "Не обещать исправление поведения за определённый срок.",
            "Не советовать наказания, медикаменты или опасное оборудование.",
            "Не выдавать обычную тренировку за лечение тревоги или агрессии.",
        ],
        sources=[
            Source(
                id="pets_akc_loose_leash",
                title="American Kennel Club — How to Stop Leash Tugging and Biting",
                url="https://www.akc.org/expert-advice/training/solutions-for-dogs-that-tug-on-leashes/",
                claims=[
                    "AKC рекомендует поощрять желательное поведение на поводке, включая нахождение рядом и внимание к владельцу.",
                    "Безопасные паузы на обнюхивание могут быть поощрением и частью обучения прогулке на свободном поводке.",
                    "Постоянное натяжение поводка может усиливать фрустрацию; полезно заранее организовать среду и поощрять желательное поведение.",
                ],
            ),
            Source(
                id="pets_akc_walk",
                title="American Kennel Club — 3 Ways To Improve Your Dog’s Walk",
                url="https://www.akc.org/expert-advice/training/improve-your-dogs-walk/",
                claims=[
                    "AKC описывает свободный поводок как провисание без постоянного натяжения.",
                    "Для обучения предлагают останавливать движение или менять направление, а когда собака возвращается — поощрять и продолжать прогулку.",
                    "Короткие отрезки спокойного движения можно чередовать с разрешёнными паузами на обнюхивание.",
                ],
            ),
        ],
        facts=[
            Fact(id="pets_f1", source_id="pets_akc_loose_leash", text="На прогулке можно поощрять собаку за спокойное движение рядом, внимание к владельцу и свободный поводок."),
            Fact(id="pets_f2", source_id="pets_akc_walk", text="Начинать удобно с коротких отрезков: при натяжении остановиться или спокойно изменить направление, а возвращение к свободному поводку отметить поощрением."),
            Fact(id="pets_f3", source_id="pets_akc_loose_leash", text="Безопасные паузы на обнюхивание можно использовать как часть прогулки и как поощрение, а не запрещать их полностью."),
            Fact(id="pets_f4", source_id="pets_akc_walk", text="Постоянное перетягивание поводка не даёт собаке понятного желательного действия; важнее последовательно отмечать спокойное поведение."),
        ],
    )
    automation = FactualBrief(
        channel="ai_automation",
        topic="Пример применения ИИ для обработки клиентских обращений",
        category="ai_automation",
        audience="руководители и специалисты малого бизнеса",
        scope_note=(
            "Это пример проектирования процесса, а не обещание эффекта и не совет передавать модели персональные или конфиденциальные данные. "
            "Перед внедрением нужно определить границы задач, доступы, ответственного человека и порядок эскалации."
        ),
        permitted_conclusions=[
            "Сначала ограничить роль ИИ классификацией, черновиком ответа и маршрутизацией.",
            "Сохранить человеческое утверждение для чувствительных или спорных ответов.",
            "Документировать область применения, риски, обратную связь и порядок исправления ошибок.",
        ],
        forbidden_conclusions=[
            "Не заявлять, что ИИ полностью заменяет поддержку.",
            "Не обещать рост выручки, скорость или точность без собственных измерений.",
            "Не советовать отправлять персональные данные внешней модели без правовой и технической оценки.",
        ],
        sources=[
            Source(
                id="ai_nist_rmf_core",
                title="NIST AI RMF Core",
                url="https://airc.nist.gov/airmf-resources/airmf/5-sec-core/",
                claims=[
                    "NIST рекомендует определить и документировать область применения системы ИИ с учётом её возможностей и контекста.",
                    "Для ИИ должны быть определены, оценены и документированы процессы человеческого надзора.",
                    "Риски и меры контроля для компонентов, включая стороннее ПО и данные, следует выявлять и документировать.",
                ],
            ),
            Source(
                id="ai_nist_gai_profile",
                title="NIST AI 600-1 — Generative AI Profile",
                url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf",
                claims=[
                    "NIST описывает необходимость тестирования, оценки, валидации и проверки до развёртывания генеративного ИИ.",
                    "Для генеративного ИИ важны мониторинг после внедрения, механизмы обратной связи, исправление ошибок и управление изменениями.",
                    "При работе со сторонними ИИ-сервисами нужно учитывать риски данных, безопасности и прав третьих лиц.",
                ],
            ),
        ],
        facts=[
            Fact(id="ai_f1", source_id="ai_nist_rmf_core", text="Перед запуском нужно зафиксировать, какие типы обращений ИИ обрабатывает, а какие сразу передаёт человеку."),
            Fact(id="ai_f2", source_id="ai_nist_rmf_core", text="Человеческий надзор и понятный путь эскалации должны быть определены для процесса работы с ИИ."),
            Fact(id="ai_f3", source_id="ai_nist_gai_profile", text="Процесс требует предварительной проверки и последующего мониторинга ошибок и обратной связи."),
            Fact(id="ai_f4", source_id="ai_nist_gai_profile", text="Перед передачей данных внешнему ИИ-сервису нужно оценить риски конфиденциальности, безопасности и прав третьих лиц."),
        ],
    )
    return {brief.channel: brief for brief in (agro, pets, automation)}


def resolve_brief(channel: str, topic: str | None = None) -> FactualBrief:
    try:
        brief = verified_briefs()[channel]
    except KeyError as exc:
        raise ValueError("channel must be one of: %s" % ", ".join(CHANNELS)) from exc
    requested_words = set(re.findall(r"[а-яa-z]{4,}", _normalise(topic or "")))
    known_words = set(re.findall(r"[а-яa-z]{4,}", _normalise(brief.topic)))
    requested_roots = {word[:5] for word in requested_words}
    known_roots = {word[:5] for word in known_words}
    # Accept a close owner wording such as "Уход за плодовыми деревьями перед
    # зимой", but do not pretend that an unrelated topic has sources.
    topic_is_covered = (
        not topic or _normalise(topic) in _normalise(brief.topic)
        or len(requested_words & known_words) >= 3
        or len(requested_roots & known_roots) >= 3
        or _normalise(topic or "") in TOPIC_ALIASES[channel]
    )
    if not topic_is_covered:
        raise ValueError(
            "В первой версии доступна только предварительно проверенная тема для %s: %s" % (channel, brief.topic)
        )
    return brief


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("ё", "е")).strip()


def _current_prompt(brief: FactualBrief) -> list[dict[str, str]]:
    """Channel-specific A prompt using current editorial constraints, unchanged.

    The production prompt bases are imported as constants; this wrapper merely
    replaces the live article/CASE with the same factual dossier given to B.
    It does not alter any production prompt or provider.
    """
    evidence = "\n".join("- %s" % fact.text for fact in brief.facts)
    if brief.channel == "agro":
        from case_pipeline.agro import AI_EDIT_SYSTEM
        system = AI_EDIT_SYSTEM
    elif brief.channel == "pets":
        from case_pipeline.pets_generator import factual_brief_prompt
        return [{"role": "user", "content": factual_brief_prompt(_pets_prompt_brief(brief))}]
    else:
        from case_pipeline.postgen import POLISH_SYSTEM_TMPL
        system = POLISH_SYSTEM_TMPL.format(tags="#AI #Автоматизация")
    user = (
        "Тема: %s\n\nПРОВЕРЕННЫЙ ФАКТИЧЕСКИЙ МАТЕРИАЛ:\n%s\n\n"
        "Ограничения: %s\nРазрешённые выводы: %s\nЗапрещённые выводы: %s"
        % (brief.topic, evidence, brief.scope_note, "; ".join(brief.permitted_conclusions), "; ".join(brief.forbidden_conclusions))
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _pets_prompt_brief(brief: FactualBrief) -> dict[str, Any]:
    return {
        "topic": brief.topic,
        "species": "dog",
        "source_url": brief.sources[0].url,
        "limitations": brief.scope_note,
        "allowed_conclusions": "; ".join(brief.permitted_conclusions),
        "forbidden_conclusions": "; ".join(brief.forbidden_conclusions),
        "attribution": "Источники и атрибуция добавляются системой отдельно.",
        "facts": [{"claim": fact.text} for fact in brief.facts],
    }


def _structured_prompt(brief: FactualBrief) -> str:
    facts = "\n".join("- [%s] %s" % (fact.source_id, fact.text) for fact in brief.facts)
    return (
        "Подготовь оригинальный русскоязычный Telegram-черновик только по factual brief. "
        "Не копируй источники. Не добавляй чисел, причинно-следственных связей, медицинских советов, "
        "обещаний результата или фактов вне списка. Верни данные строго по переданной JSON Schema.\n\n"
        "Канал: %s\nТема: %s\nАудитория: %s\nКатегория: %s\n"
        "Контекст применимости: %s\nРазрешено: %s\nЗапрещено: %s\n"
        "Проверенные факты:\n%s\n\n"
        "source_ids должен содержать только ID источников, указанные у использованных фактов; "
        "в body не включай URL, JSON, лицензионные или служебные формулировки."
        % (brief.channel, brief.topic, brief.audience, brief.category, brief.scope_note,
           "; ".join(brief.permitted_conclusions), "; ".join(brief.forbidden_conclusions), facts)
    )


def split_post(raw: str) -> tuple[str, str]:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    title, separator, body = text.partition("\n\n")
    if not separator:
        title, _, body = text.partition("\n")
    return title.strip(), body.strip()


_DISALLOWED_TECHNICAL = re.compile(r"(?:^\s*[\[{]|\"(?:title|body|source_ids)\"\s*:|\bjson\b|\bdoi\b|licensed under)", re.I)
_MEDICAL_OR_PROMISE = re.compile(r"(?:лечит|диагноз|гарантиру|вылечит|всегда|никогда)", re.I)


def validate_reader_post(title: str, body: str, brief: FactualBrief, source_ids: list[str] | None = None) -> list[str]:
    """Mechanical safety gate; semantic fact review remains deliberately visible."""
    errors: list[str] = []
    full = "%s\n%s" % (title.strip(), body.strip())
    if not 10 <= len(title.strip()) <= 140:
        errors.append("title_length")
    if not 120 <= len(body.strip()) <= 3200:
        errors.append("body_length")
    if _DISALLOWED_TECHNICAL.search(full):
        errors.append("technical_metadata_in_reader_text")
    if _MEDICAL_OR_PROMISE.search(full):
        errors.append("medical_or_absolute_claim")
    if source_ids is not None:
        unknown = sorted(set(source_ids) - brief.source_ids)
        if unknown:
            errors.append("unknown_source_ids:%s" % ",".join(unknown))
        if not source_ids:
            errors.append("source_ids_empty")
    # A reproducible anti-hallucination check for new numbers.  It cannot prove
    # every natural-language implication, so successful output is still marked
    # as requiring human factual review in the report.
    allowed_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", brief.source_text()))
    for number in re.findall(r"\d+(?:[.,]\d+)?", full):
        if number not in allowed_numbers:
            errors.append("number_not_in_factual_brief:%s" % number)
            break
    return errors


def validate_structured_draft(draft: StructuredDraft, brief: FactualBrief) -> list[str]:
    errors = validate_reader_post(draft.title, draft.body, brief, draft.source_ids)
    if draft.category != brief.category:
        errors.append("category_mismatch")
    if not draft.image_search_query.strip():
        errors.append("image_search_query_empty")
    return errors


def _usage_to_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    output: dict[str, int] = {}
    for key in ("total_tokens", "prompt_tokens", "completion_tokens"):
        value = getattr(usage, key, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(key)
        if value is not None:
            try:
                output[key] = int(value)
            except (TypeError, ValueError):
                pass
    return output or None


@dataclass
class Result:
    variant: str
    channel: str
    run_number: int
    status: str
    title: str = ""
    body: str = ""
    category: str = ""
    source_ids: list[str] | None = None
    image_search_query: str = ""
    editorial_notes: str = ""
    validation_errors: list[str] | None = None
    fact_review: str = "required_manual_semantic_review"
    elapsed_ms: int = 0
    usage: dict[str, int] | None = None
    retries: int = 0
    error: str = ""
    native_structured_output: bool = False

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def call_current_editor(brief: FactualBrief, run_number: int, provider: Any) -> Result:
    """Variant A: existing REST provider and channel prompt, with no code changes."""
    started = time.perf_counter()
    try:
        raw = provider.complete(_current_prompt(brief))
        title, body = split_post(raw or "")
        errors = validate_reader_post(title, body, brief)
        return Result(
            variant="A_current_editor", channel=brief.channel, run_number=run_number,
            status="passed" if not errors else "review", title=title, body=body,
            category=brief.category, source_ids=sorted(brief.source_ids),
            validation_errors=errors, elapsed_ms=round((time.perf_counter() - started) * 1000),
            usage=getattr(provider, "last_usage", None), native_structured_output=False,
        )
    except Exception as exc:  # no retry: each sample must remain independent
        return Result(
            variant="A_current_editor", channel=brief.channel, run_number=run_number,
            status="error", error="%s: %s" % (type(exc).__name__, str(exc)[:240]),
            validation_errors=["call_failed"], elapsed_ms=round((time.perf_counter() - started) * 1000),
        )


def _sdk_structured_call(prompt: str) -> tuple[Any, StructuredDraft]:
    """Variant B: official SDK native parse + Pydantic response schema."""
    credentials = os.getenv("GIGACHAT_API_KEY")
    if not credentials:
        raise RuntimeError("GIGACHAT_API_KEY is required for a live structured experiment")
    from gigachat import GigaChat

    # `chat.parse` is the current SDK interface.  It sends the response schema
    # to GigaChat and validates the returned JSON into StructuredDraft.
    with GigaChat(
        credentials=credentials,
        model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
        verify_ssl_certs=os.getenv("GIGACHAT_VERIFY_SSL", "0") == "1",
        max_retries=0,
    ) as client:
        completion, parsed = client.chat.parse(prompt, response_format=StructuredDraft, strict=True)
    return completion, parsed


def call_structured_editor(brief: FactualBrief, run_number: int,
                           structured_call: Callable[[str], tuple[Any, StructuredDraft]] = _sdk_structured_call) -> Result:
    started = time.perf_counter()
    try:
        completion, draft = structured_call(_structured_prompt(brief))
        if not isinstance(draft, StructuredDraft):
            draft = StructuredDraft.model_validate(draft)
        errors = validate_structured_draft(draft, brief)
        return Result(
            variant="B_native_structured", channel=brief.channel, run_number=run_number,
            status="passed" if not errors else "review", title=draft.title, body=draft.body,
            category=draft.category, source_ids=draft.source_ids,
            image_search_query=draft.image_search_query, editorial_notes=draft.editorial_notes,
            validation_errors=errors, elapsed_ms=round((time.perf_counter() - started) * 1000),
            usage=_usage_to_dict(getattr(completion, "usage", None)), native_structured_output=True,
        )
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return Result(
            variant="B_native_structured", channel=brief.channel, run_number=run_number,
            status="error", error="%s: %s" % (type(exc).__name__, str(exc)[:240]),
            validation_errors=["native_schema_or_json_error"], elapsed_ms=round((time.perf_counter() - started) * 1000),
            native_structured_output=True,
        )
    except Exception as exc:
        return Result(
            variant="B_native_structured", channel=brief.channel, run_number=run_number,
            status="error", error="%s: %s" % (type(exc).__name__, str(exc)[:240]),
            validation_errors=["structured_call_failed"], elapsed_ms=round((time.perf_counter() - started) * 1000),
            native_structured_output=True,
        )


def dry_run_preview(brief: FactualBrief, requested_topic: str | None) -> dict[str, Any]:
    return {
        "mode": "dry_run",
        "telegram_sent": False,
        "vk_sent": False,
        "gigachat_calls": 0,
        "production_sqlite_written": False,
        "requested_topic": requested_topic or brief.topic,
        "topic_resolution": "preverified_brief_only",
        "limitation": "No source search is implemented. The requested topic must match the pre-verified brief for its channel.",
        "factual_brief": brief.model_dump(),
        "structured_schema": StructuredDraft.model_json_schema(),
    }


def run_comparison(briefs: list[FactualBrief], runs_per_variant: int) -> dict[str, Any]:
    from case_pipeline.ai import GigaChatProvider

    results: list[dict[str, Any]] = []
    for brief in briefs:
        for run_number in range(1, runs_per_variant + 1):
            # Fresh provider avoids sharing OAuth/access state between samples.
            results.append(call_current_editor(brief, run_number, GigaChatProvider()).as_dict())
        for run_number in range(1, runs_per_variant + 1):
            results.append(call_structured_editor(brief, run_number).as_dict())
    summary: dict[str, Any] = {"requested_generations": len(briefs) * runs_per_variant * 2, "by_variant": {}}
    for variant in ("A_current_editor", "B_native_structured"):
        subset = [item for item in results if item["variant"] == variant]
        passed = sum(item["status"] == "passed" for item in subset)
        review = sum(item["status"] == "review" for item in subset)
        errors = sum(item["status"] == "error" for item in subset)
        token_total = sum((item.get("usage") or {}).get("total_tokens", 0) for item in subset)
        summary["by_variant"][variant] = {
            "runs": len(subset), "passed": passed, "review": review, "errors": errors,
            "mechanical_validation_success_percent": round(100 * passed / len(subset), 1) if subset else 0,
            "reported_total_tokens": token_total or None,
        }
    return {
        "mode": "live_experiment", "telegram_sent": False, "vk_sent": False,
        "production_sqlite_written": False, "briefs": [brief.model_dump() for brief in briefs],
        "results": results, "summary": summary,
        "native_structured_output": "GigaChat SDK client.chat.parse(response_format=StructuredDraft, strict=True)",
        "fact_check_limit": "Mechanical guards run automatically; successful outputs still require a human semantic fact review.",
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# GigaChat Structured Editor — эксперимент", ""]
    lines.append("Режим: `%s`" % payload["mode"])
    lines.append("Telegram: не вызывался. VK: не вызывался. Production SQLite: не изменялась.")
    lines.append("")
    if payload["mode"] == "dry_run":
        brief = payload["factual_brief"]
        lines.extend(["## Проверенный factual brief", "", "Тема: %s" % brief["topic"], "", brief["scope_note"], "", "Источники:"])
        for source in brief["sources"]:
            lines.append("- `%s` — [%s](%s)" % (source["id"], source["title"], source["url"]))
        return "\n".join(lines) + "\n"
    lines.extend(["## Сводка", "", "```json", json.dumps(payload["summary"], ensure_ascii=False, indent=2), "```", "", "## Черновики", ""])
    for result in payload["results"]:
        lines.append("### %s — %s / запуск %s" % (result["variant"], result["channel"], result["run_number"]))
        lines.append("")
        lines.append("Статус: `%s`; время: %s мс; токены: `%s`" % (result["status"], result["elapsed_ms"], (result.get("usage") or {}).get("total_tokens", "нет данных")))
        if result.get("title"):
            lines.extend(["", result["title"], "", result.get("body") or ""])
        if result.get("source_ids"):
            lines.append("\nИсточник(и): %s" % ", ".join("`%s`" % item for item in result["source_ids"]))
        if result.get("validation_errors"):
            lines.append("\nПроверка: %s" % ", ".join("`%s`" % item for item in result["validation_errors"]))
        if result.get("error"):
            lines.append("\nОшибка: `%s`" % result["error"])
        lines.append("")
    return "\n".join(lines)


def save_payload(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "structured_editor_report.json"
    md_path = output_dir / "structured_editor_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Isolated GigaChat structured editor experiment")
    parser.add_argument("--channel", choices=(*CHANNELS, "all"), default="all")
    parser.add_argument("--topic", help="Owner topic; v1 accepts only the matching pre-verified brief")
    parser.add_argument("--dry-run", action="store_true", help="Create factual-brief preview without GigaChat")
    parser.add_argument("--live", action="store_true", help="Enable actual paid calls only with --allow-paid-gigachat")
    parser.add_argument("--allow-paid-gigachat", action="store_true", help="Explicit second gate for paid calls")
    parser.add_argument("--runs-per-variant", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--output-dir", type=Path, default=Path("runs") / "structured_editor" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run and args.live:
        raise SystemExit("Choose either --dry-run or --live, not both")
    selected = CHANNELS if args.channel == "all" else (args.channel,)
    if args.topic and len(selected) != 1:
        raise SystemExit("--topic requires one --channel in this first, pre-verified version")
    briefs = [resolve_brief(channel, args.topic) for channel in selected]
    if args.dry_run or not args.live:
        if len(briefs) != 1:
            raise SystemExit("dry-run with --channel all is ambiguous; select one channel")
        payload = dry_run_preview(briefs[0], args.topic)
    else:
        if not args.allow_paid_gigachat:
            raise SystemExit("Paid calls require --allow-paid-gigachat")
        if not os.getenv("GIGACHAT_API_KEY"):
            raise SystemExit("GIGACHAT_API_KEY is absent; no paid call was made")
        payload = run_comparison(briefs, args.runs_per_variant)
    payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    json_path, md_path = save_payload(args.output_dir, payload)
    print(json.dumps({"report": str(json_path), "preview": str(md_path), "mode": payload["mode"], "telegram_sent": False, "vk_sent": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
