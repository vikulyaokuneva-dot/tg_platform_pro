# -*- coding: utf-8 -*-
"""Deterministic, history-aware PETS topic planner.

The planner only proposes evergreen briefs.  It does not create a post until a
source adapter supplies adequate facts and the validator accepts them.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    title: str
    category: str
    species: str
    visual_tags: tuple[str, ...]


_LEGACY_TOPICS = (
    Topic("cat-safe-home-routine", "Кошка в новом доме: как сделать пространство спокойнее", "care", "cat", ("cat", "home", "safe_shelter")),
    Topic("dog-reward-training-basics", "Собака учится через поощрение: с чего начать", "training", "dog", ("dog", "training", "owner")),
    Topic("cat-enrichment-at-home", "Игры и среда: как разнообразить день домашней кошки", "behavior", "cat", ("cat", "enrichment", "home")),
    Topic("dog-walk-safety", "Прогулка с собакой: спокойный чек-лист безопасности", "safety", "dog", ("dog", "walk", "owner")),
    Topic("cat-grooming-observation", "Уход за кошкой: что удобно наблюдать во время груминга", "care", "cat", ("cat", "grooming", "owner")),
    Topic("dog-rest-and-routine", "Отдых и распорядок: зачем собаке предсказуемый день", "behavior", "dog", ("dog", "rest", "home")),
    Topic("cat-carrier-positive-association", "Переноска без спешки: как сделать её привычной частью дома", "training", "cat", ("cat", "carrier", "home")),
    Topic("dog-food-safety-labels", "Безопасность корма: на что смотреть в официальных предупреждениях", "nutrition", "dog", ("dog", "food", "owner")),
    Topic("cat-family-hygiene", "Кошка и гигиена дома: простые привычки для семьи", "safety", "cat", ("cat", "home", "hygiene")),
    Topic("dog-breed-needs", "Порода и индивидуальность собаки: почему универсальных советов мало", "breed", "dog", ("dog", "owner", "home")),
    Topic("cat-food-safety", "Безопасность кошачьего корма: когда проверять официальные уведомления", "nutrition", "cat", ("cat", "food", "owner")),
    Topic("dog-gentle-handling", "Бережное обращение с собакой: как поддержать спокойное взаимодействие", "care", "dog", ("dog", "owner", "home")),
)

# Topic-first catalog: ten owner-facing categories × five practical themes ×
# cats/dogs. It is a planning catalog, not a source of facts or publishable
# prose. A selected topic still needs a factual brief and safety checks.
_CATALOG = (
    ("behavior", "Поведение", ("сигналы спокойствия дома", "как заметить перегрузку", "ритуалы без спешки", "выбор места для отдыха", "спокойное знакомство с гостями")),
    ("training", "Воспитание и привычки", ("маленькие шаги в обучении", "понятное поощрение", "домашний ритуал", "мягкое закрепление навыка", "как закончить занятие вовремя")),
    ("enrichment", "Игры и развлечения", ("игра без суеты", "безопасная игрушка", "смена занятий", "поиск лакомства без спешки", "короткая совместная игра")),
    ("care", "Уход за шерстью", ("привычка к расчёске", "спокойный груминг", "выбор времени для ухода", "знакомство с щёткой", "домашняя рутина ухода")),
    ("nutrition", "Питание и быт", ("спокойное место для миски", "бытовой ритуал кормления", "чистая миска", "наблюдение за привычками", "хранение корма дома")),
    ("activity", "Прогулки и активность", ("спокойная прогулка", "паузы на улице", "подходящий темп", "игра после прогулки", "возвращение домой без спешки")),
    ("facts", "Интересные факты", ("индивидуальные привычки", "язык тела", "зачем питомцу выбор", "разные способы отдыха", "как меняется интерес к игре")),
    ("adaptation", "Новый дом", ("первая тихая зона", "знакомство с комнатами", "ритуал первых дней", "место для укрытия", "мягкое знакомство с семьёй")),
    ("safety", "Безопасность дома", ("проверка проводов", "безопасная зона отдыха", "порядок у окна", "вещи вне доступа", "спокойный домашний чек-лист")),
    ("human", "Питомец и человек", ("уважение к дистанции", "предсказуемое внимание", "семейный ритм", "чтение сигналов", "совместный отдых")),
)


def _catalog_topics():
    items = []
    for category, label, themes in _CATALOG:
        for species, animal, tags in (("cat", "Кошка", ("cat", "home")), ("dog", "Собака", ("dog", "owner"))):
            for number, theme in enumerate(themes, 1):
                key = "%s-%s-%s" % (species, category, number)
                items.append(Topic(key, "%s: %s — %s" % (animal, label.lower(), theme), category, species, tags))
    return tuple(items)


TOPICS = _LEGACY_TOPICS + _catalog_topics()


def choose_topics(storage, limit=10):
    """Return unseen topics while alternating species and avoiding same category."""
    chosen, previous_species, previous_category = [], None, None
    for topic in TOPICS:
        if storage.topic_seen(topic.key) or storage.similar_topic_seen(topic.key):
            continue
        if previous_species == topic.species or previous_category == topic.category:
            continue
        allowed, _ = storage.diversity_allows(topic.category, topic.species)
        if not allowed:
            continue
        chosen.append(topic)
        previous_species, previous_category = topic.species, topic.category
        if len(chosen) >= limit:
            break
    return chosen
