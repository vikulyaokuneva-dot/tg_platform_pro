# -*- coding: utf-8 -*-
"""case_pipeline.ai — AI arbitration layer (GigaChat), строго структурированный JSON.

Принцип: RULES = first gate; сюда попадают только needs_review (и пограничные
случаи). AI НЕ «придумывает кейс» — он судит: является ли материал реальным
бизнес-кейсом, и обязан указать дословные цитаты (валидируются детерминированно
в runner-е; недоказуемые цитаты => INVALID-вердикт).

GigaChat включается только при наличии GIGACHAT_API_KEY; иначе NullProvider
(материал остаётся в review и не публикуется). Тесты используют FakeProvider
(не сеть). Транспорт — чистый REST (requests), без зависимости от SDK.
"""
import json
import logging
import re

from . import config

log = logging.getLogger("case_pipeline.ai")

VERDICTS = ("business_case", "how_to", "news", "other")

SYSTEM = (
    "Ты — редактор делового Telegram-канала про AI и автоматизацию в бизнесе.\n"
    "Тебе даны: заголовок, URL, результат детерминированного классификатора и текст статьи.\n"
    "Определи, является ли материал РЕАЛЬНЫМ бизнес-кейсом: одна конкретная "
    "реальная компания + её проблема + конкретное внедрение решения + результат.\n"
    "Не считай кейсом: обучающие how-to, обзоры инструментов, анонсы продуктов, "
    "мнения/интервью, список примеров без единой компании-героя, гипотетические "
    "примеры, самопродвижение вендора.\n"
    "Верни СТРОГО JSON без пояснений:\n"
    '{"decision":"business_case|how_to|news|other","confidence":0..1,'
    '"company":"название или пусто","problem_quote":"дословная цитата из текста (<=240 симв)",'
    '"implementation_quote":"дословная цитата (<=240 симв)",'
    '"result_quote":"дословная цитата или пусто (<=240 симв)","reason":"1-2 предложения"}\n'
    "Цитаты — ТОЛЬКО дословные подстрожки данного текста. Если не уверен — decision=other.\n"
    "Если язык источника английский, поля *_quote оставь на языке источника."
)


def build_ai_request(title, url, text, classifier_result, max_chars=6000):
    user = ("Заголовок: %s\nURL: %s\nКлассификатор(rules): тип=%s, компания=%s, "
            "rationale=%s\n\nТЕКСТ:\n%s" % (
                (title or "")[:200], url, classifier_result.get("type"),
                classifier_result.get("company"),
                "; ".join(classifier_result.get("rationale") or [])[:300],
                (text or "")[:max_chars]))
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]


def _extract_json(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def validate_verdict(v, source_text):
    """Детерминированная проверка AI-вердикта: структура + цитаты в исходнике."""
    if not isinstance(v, dict):
        return None, "no json"
    d = (v.get("decision") or "").strip()
    if d not in VERDICTS:
        return None, "bad decision"
    quotes = {k: v.get(k) for k in ("problem_quote", "implementation_quote", "result_quote") if v.get(k)}
    if d == "business_case":
        # HARD: business_case requires both problem + implementation evidence quotes
        if not quotes.get("problem_quote") or not quotes.get("implementation_quote"):
            return None, "business_case without problem/implementation quotes"
    # SOFT: how_to / news / other verdicts allowed for AI Automation (practical guides,
    # workflow explanations, tool reviews) — no mandatory quote pair required.
    from .utils import ws_norm
    src = ws_norm(source_text)
    for k, q in quotes.items():
        if ws_norm(q) not in src:
            return None, "quote not in source: %s" % k
    try:
        v["confidence"] = max(0.0, min(1.0, float(v.get("confidence") or 0.5)))
    except Exception:
        v["confidence"] = 0.5
    return v, None


class BaseAI:
    available = False
    name = "none"

    def arbitrate(self, title, url, text, classifier_result):
        raise NotImplementedError


class NullProvider(BaseAI):
    name = "null"

    def arbitrate(self, *a, **k):
        return None


class FakeProvider(BaseAI):
    """Для тестов: вердикт внедряется тестом."""
    name = "fake"
    available = True

    def __init__(self, verdict=None):
        self.verdict = verdict

    def arbitrate(self, title, url, text, classifier_result):
        return dict(self.verdict or {})


class GigaChatProvider(BaseAI):
    """REST-клиент GigaChat (проверен живым API): OAuth-токен по Basic-ключу
    (GIGACHAT_API_KEY = base64 client_id:client_secret) + /v1/chat/completions.
    Секреты в заголовках — в тексты ошибок/логи не попадают (в URL их нет)."""
    name = "gigachat"
    available = bool(config.GIGACHAT_KEY)
    # Routine = Lite-tier (базовая GigaChat-2 на персональном скоупе).
    # Pro/Max/Ultra без объективной необходимости НЕ используем.
    MODELS = ("GigaChat-2",)

    def __init__(self):
        self._token = None
        self._token_exp = 0.0

    def _get_token(self):
        import time
        import uuid
        import requests
        now = time.time()
        if self._token and now < self._token_exp - 120:
            return self._token
        r = requests.post(config.GIGACHAT_AUTH_URL,
                          headers={"Authorization": "Basic " + config.GIGACHAT_KEY,
                                   "Content-Type": "application/x-www-form-urlencoded",
                                   "RqUID": str(uuid.uuid4())},
                          data={"scope": config.GIGACHAT_SCOPE,
                                "grant_type": "client_credentials"},
                          timeout=config.GIGACHAT_TIMEOUT,
                          verify=config.GIGACHAT_VERIFY_SSL)
        data = r.json() if r.content else {}
        if r.status_code != 200 or not data.get("access_token"):
            raise RuntimeError("oauth HTTP %s: %s" % (r.status_code,
                                 str(data.get("error") or data.get("detail") or "")[:160]))
        self._token = data["access_token"]
        # expiry в мс epoch (или expires_in в секундах)
        if data.get("expiry"):
            self._token_exp = float(data["expiry"]) / 1000.0
        else:
            self._token_exp = now + float(data.get("expires_in") or 1800) - 60
        log.info("gigachat oauth ok (scope=%s)", config.GIGACHAT_SCOPE)
        return self._token

    def _call(self, messages, model):
        import requests
        payload = {"model": model, "messages": messages, "repetition_penalty": 1}
        r = requests.post(config.GIGACHAT_BASE_URL + "/v1/chat/completions",
                          headers={"Authorization": "Bearer " + self._get_token()},
                          json=payload, timeout=config.GIGACHAT_TIMEOUT,
                          verify=config.GIGACHAT_VERIFY_SSL)
        if r.status_code == 401:
            self._token = None   # протух — следующий вызов обновит
        if r.status_code != 200:
            raise RuntimeError("chat HTTP %s: %s" % (r.status_code, r.text[:200]))
        return r.json()["choices"][0]["message"]["content"]

    def complete(self, messages):
        """Гeneric text completion с candidates-models (как в legacy ai_writer)."""
        if not self.available:
            return None
        models = [config.GIGACHAT_MODEL] + [m for m in self.MODELS if m != config.GIGACHAT_MODEL]
        for model in models:
            try:
                return self._call(messages, model)
            except ImportError:
                log.warning("gigachat SDK not installed")
                return None
            except Exception as e:
                log.warning("gigachat model=%s failed: %s", model, e)
        return None

    def arbitrate(self, title, url, text, classifier_result):
        if not self.available:
            return None
        msgs = build_ai_request(title, url, text, classifier_result)
        raw = self.complete(msgs)
        v = _extract_json(raw)
        if v is None and raw:
            log.warning("gigachat non-json: %r", raw[:160])
        return v


def get_provider(prefer="auto"):
    if prefer == "null":
        return NullProvider()
    if GigaChatProvider.available:
        return GigaChatProvider()
    log.info("GIGACHAT_API_KEY absent -> arbitration disabled (review-lane materials stay in review)")
    return NullProvider()
