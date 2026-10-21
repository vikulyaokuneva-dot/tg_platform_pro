# -*- coding: utf-8 -*-
"""Расширяемые редакционные профили тематических каналов.

Профиль не является медицинским советчиком: он только отправляет рискованные
материалы на review до подготовки или публикации поста.
"""
import re
from collections import Counter


_WORD = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{3,}")
_STOP = {"который", "которая", "которые", "также", "чтобы", "после", "перед",
         "about", "their", "these", "those", "with", "from", "that", "this"}


class EditorialProfile:
    def __init__(self, name, allowed_topics, target_mix, forbidden_patterns,
                 review_patterns, health_patterns):
        self.name = name
        self.allowed_topics = allowed_topics
        self.target_mix = target_mix
        self.forbidden_patterns = [re.compile(p, re.I) for p in forbidden_patterns]
        self.review_patterns = [re.compile(p, re.I) for p in review_patterns]
        self.health_patterns = [re.compile(p, re.I) for p in health_patterns]

    def classify(self, title, text):
        blob = (title or "") + "\n" + (text or "")
        low = blob.lower()
        species = "cat" if re.search(r"\b(кошк|кот[а-я]*|cat|kitten)", low) else \
            "dog" if re.search(r"\b(собак|щен|dog|puppy)", low) else "mixed"
        category = "care"
        for key, terms in self.allowed_topics.items():
            if any(term in low for term in terms):
                category = key
                break
        breed = _breed_from(blob)
        return {"species": species, "category": category, "breed": breed,
                "topic_key": semantic_key(title, text)}

    def review_reasons(self, title, text):
        blob = (title or "") + "\n" + (text or "")
        reasons = []
        for rx in self.forbidden_patterns:
            if rx.search(blob):
                reasons.append("forbidden topic: " + rx.pattern[:45])
        for rx in self.review_patterns:
            if rx.search(blob):
                reasons.append("manual review: " + rx.pattern[:45])
        for rx in self.health_patterns:
            if rx.search(blob):
                reasons.append("veterinary safety: " + rx.pattern[:45])
        return reasons


def semantic_key(title, text=""):
    """Стабильный тематический отпечаток без внешней модели.

    Он намеренно консервативен: exact URL/content hash остаются главным
    дедупом, а этот ключ удерживает очевидный повтор того же совета.
    """
    words = [w.lower() for w in _WORD.findall((title or "") + " " + (text or "")[:500])]
    words = [w for w in words if w not in _STOP]
    return " ".join(sorted(Counter(words).keys())[:8])[:180]


def _breed_from(text):
    patterns = {
        "labrador": r"лабрадор|labrador", "british_shorthair": r"британск\w*\s+короткош",
        "german_shepherd": r"немецк\w*\s+овчарк", "golden_retriever": r"золотист\w*\s+ретривер",
        "maine_coon": r"мейн[- ]?кун", "poodle": r"пудел",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text or "", re.I):
            return name
    return ""


PETS_EXPERT = EditorialProfile(
    name="pets_expert",
    allowed_topics={
        "care": ("уход", "гигиен", "шерст", "котен", "щен", "владельц"),
        "breed": ("пород", "лабрадор", "британск", "овчарк", "мейн", "breed"),
        "behavior": ("поведен", "воспитан", "стресс", "тянет поводок", "оставаться", "training"),
        "nutrition": ("питани", "кормлен", "рацион", "nutrition", "diet"),
        "science": ("исследован", "научн", "study", "science"),
    },
    target_mix={"care": .30, "breed": .25, "behavior": .25, "nutrition": .15, "science": .05},
    forbidden_patterns=(r"мем", r"ставк[аи]", r"разведени[ея].*продаж", r"гарантированн\w* леч"),
    review_patterns=(r"спорн\w*", r"народн\w* средств", r"лучший корм", r"рекламн\w*"),
    health_patterns=(r"диагноз", r"дозировк", r"мг/кг", r"назнач\w* лекар",
                     r"антибиотик", r"лечить дома", r"вылечит"),
)

PROFILES = {PETS_EXPERT.name: PETS_EXPERT}


def get_profile(name):
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError("unknown editorial profile: %s" % name) from exc
