# -*- coding: utf-8 -*-
"""case_pipeline.config — все настройки из env, секреты НЕ хардкодятся.

Env-переменные (документированы в README_CASE_PIPELINE.md):
  AI_AUTOMATION_BOT_TOKEN   токен @shared_platform_bot (fallback: POSTER_BOT_TOKEN)
  AI_AUTOMATION_CHAT_ID     канал публикации (default -1003553181515)
  GIGACHAT_API_KEY          credentials GigaChat (без него AI-слой выключен)
  GIGACHAT_MODEL            модель (default GigaChat-2, fallback GigaChat)
  CASE_DB_PATH              sqlite-путь (default <root>/data/ai_case_pipeline.db)
  CASE_RUNS_DIR             каталог артефактов (default <root>/runs)
  CASE_PUBLISH              "1" разрешает реальную публикацию (иначе dry-run)
  CASE_PUBLISH_LIMIT        максимум постов за запуск (default 1)
  CASE_MAX_PER_SOURCE       максимум свежих URL на источник за запуск (default 4)
  CASE_SOURCES              csv включённых источников (default mindbox,ibm,zapier,salesforce)
  AGRO_SOURCES              csv источников агро-канала (default botanichka,agroinvestor,gismeteo)
  AGRO_BOT_TOKEN            токен бота агро-канала (конвенция платформенных jobs <JOB>_BOT_TOKEN)
  AGRO_CHAT_ID              chat_id агро-канала (конвенция <JOB>_CHAT_ID)
  AGRO_DB_PATH              отдельная sqlite-история агро-канала (default <root>/data/agro_channel.db)
  AGRO_PUBLISH              "1" разрешает реальную публикацию агро (иначе dry-run)
  AGRO_PUBLISH_LIMIT        максимум агро-постов за запуск (default 1)
  AGRO_MAX_PER_RUN          максимум свежих URL на агро-источник за запуск (default 3)
  AGRO_MAX_AGE_DAYS         окно свежести агро-материала по дате публикации (default 5)
  AGRO_VK_DM_ENABLED        "1" — отправлять владельцу готовую VK-версию
                            только после успешной AGRO-публикации (default 0)
  AGRO_VK_DM_CHAT_ID        личный chat_id владельца (GitHub Secret)
  PETS использует общий секрет AI_AUTOMATION_BOT_TOKEN; отдельный
                            PETS_BOT_TOKEN намеренно не поддерживается
  PETS_CHAT_ID              chat_id канала PETS (только env/Secret)
  PETS_DB_PATH              отдельная SQLite-история PETS
  PETS_PUBLISH              "1" разрешает публикацию только при durable state
  PETS_SOURCES              csv одобренных источников (по умолчанию пусто)
  PETS_CONTENT_MODE         evergreen | news (default evergreen)
  PETS_EDITORIAL_PROFILE    профиль редакционной безопасности (pets_expert)
  PETS_STATE_BACKEND        cache (только dry-run) | github (versioned state)
  PETS_STATE_REPOSITORY     private GitHub repository for durable PETS state
  PETS_STATE_BRANCH         isolated state branch (default pets-state)
  PETS_STATE_PATH           SQLite object path in the state branch
  VK_ACCESS_TOKEN           токен VK API (только из GitHub Secret/env)
  VK_GROUP_ID               числовой id сообщества VK без знака «-»
  VK_PUBLISH                "1" разрешает реальную публикацию в VK (default 0)
  VK_PUBLISH_LIMIT          максимум VK-постов за календарные сутки (default 1)
  VK_SELF_CHECK             "1" выполняет только read-only groups.getById (default 0)
  VK_TELEGRAM_URL           необязательная ссылка-приглашение в Telegram
  VK_SOURCE_IMAGES_ALLOWED  "1" — подтверждение прав на повторное размещение
                            изображений источников (default 0)
  FETCH_TIMEOUT_SEC         таймаут HTTP (default 40)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv():
    """Безопасная загрузка <root>/.env: реальные env-переменные имеют приоритет
    (override=False). Значения никогда не логируются и не возвращаются."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip().removeprefix("export ").strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    os.environ.setdefault(k, v)
    except Exception:
        pass  # битый .env не должен ронять процесс; secrets не печатаем


_load_dotenv()


def env(name, default=None):
    v = os.getenv(name)
    return v if v not in (None, "") else default


BOT_TOKEN = env("AI_AUTOMATION_BOT_TOKEN") or env("POSTER_BOT_TOKEN")
CHAT_ID = env("AI_AUTOMATION_CHAT_ID", "-1003553181515")

GIGACHAT_KEY = env("GIGACHAT_API_KEY")
# REST-контракт GigaChat (проверен живым API 2026-09): oauth на ngw + чат на api.giga.chat
GIGACHAT_AUTH_URL = env("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_BASE_URL = env("GIGACHAT_BASE_URL", "https://api.giga.chat")
GIGACHAT_SCOPE = env("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
# Lite-tier: базовая модель GigaChat-2 на персональном скоупе (живой /v1/models
# 2026-09: модели "GigaChat-Lite" в API нет; Pro/Max/Ultra — платные тир-ы,
# для routine-задач НЕ используются).
GIGACHAT_MODEL = env("GIGACHAT_MODEL", "GigaChat-2")
GIGACHAT_TIMEOUT = int(env("GIGACHAT_TIMEOUT_SEC", "60"))
GIGACHAT_VERIFY_SSL = env("GIGACHAT_VERIFY_SSL", "0") == "1"

DB_PATH = env("CASE_DB_PATH", os.path.join(ROOT, "data", "ai_case_pipeline.db"))
RUNS_DIR = env("CASE_RUNS_DIR", os.path.join(ROOT, "runs"))

PUBLISH = env("CASE_PUBLISH", "0") == "1"
PUBLISH_LIMIT = int(env("CASE_PUBLISH_LIMIT", "1"))
MAX_PER_SOURCE = int(env("CASE_MAX_PER_SOURCE", "4"))
SOURCES = [s.strip() for s in env("CASE_SOURCES", "mindbox,ibm,zapier,salesforce").split(",") if s.strip()]
# CI не задаёт AGRO_SOURCES — новые источники попадают через default.
AGRO_SOURCES = [s.strip() for s in env(
    "AGRO_SOURCES", "botanichka,agroinvestor,gismeteo,aif,supersadovnik,"
                    "ogorodnik,7dach").split(",") if s.strip()]

FETCH_TIMEOUT_SEC = int(env("FETCH_TIMEOUT_SEC", "40"))
FETCH_RETRIES = int(env("FETCH_RETRIES", "2"))
POLITE_DELAY_SEC = float(env("POLITE_DELAY_SEC", "1.2"))

# пороги качества извлечения (совпадают с валидированным PoC)
QUALITY_GOOD = 2500
QUALITY_PARTIAL = 700          # == size-gate классификатора

# ---------- AGRO CHANNEL (jobs/agro) ----------
# Секреты ТОЛЬКО из env/secrets (конвенция платформенных jobs):
#   AGRO_BOT_TOKEN / AGRO_CHAT_ID. Пустые значения = канал выключен
#   (lane честно сообщит "не задано" и не тронет production).
AGRO_BOT_TOKEN = env("AGRO_BOT_TOKEN")
AGRO_CHAT_ID = env("AGRO_CHAT_ID")
# Отдельная БД истории: ноль взаимного влияния publication history/dedup
# между каналами без изменения storage.py (та же схема, свой файл).
AGRO_DB_PATH = env("AGRO_DB_PATH", os.path.join(ROOT, "data", "agro_channel.db"))
AGRO_PUBLISH = env("AGRO_PUBLISH", "0") == "1"
AGRO_PUBLISH_LIMIT = int(env("AGRO_PUBLISH_LIMIT", "1"))
AGRO_MAX_PER_RUN = int(env("AGRO_MAX_PER_RUN", "3"))
AGRO_MAX_AGE_DAYS = int(env("AGRO_MAX_AGE_DAYS", "5"))
# Личная отправка — часть успешной AGRO-публикации, а не отдельный pipeline.
# По умолчанию выключена; chat id никогда не попадает в логи или отчёты.
AGRO_VK_DM_ENABLED = env("AGRO_VK_DM_ENABLED", "0") == "1"
AGRO_VK_DM_CHAT_ID = env("AGRO_VK_DM_CHAT_ID")

# ---------- PETS CHANNEL (jobs/pets) ----------
# PETS использует того же управляющего бота, что AI Automation и AGRO
# (GitHub Secret AI_AUTOMATION_BOT_TOKEN). Канал, БД, источники и история
# остаются отдельными. Отдельный PETS_BOT_TOKEN намеренно не читается, чтобы
# не появилось второго бота по ошибке.
PETS_CHAT_ID = env("PETS_CHAT_ID")
PETS_DB_PATH = env("PETS_DB_PATH", os.path.join(ROOT, "data", "pets_channel.db"))
PETS_CANDIDATES_DB_PATH = env("PETS_CANDIDATES_DB_PATH", os.path.join(ROOT, "data", "pets_source_candidates.db"))
PETS_PUBLISH = env("PETS_PUBLISH", "0") == "1"
PETS_PUBLISH_LIMIT = int(env("PETS_PUBLISH_LIMIT", "1"))
PETS_MAX_PER_RUN = int(env("PETS_MAX_PER_RUN", "3"))
PETS_SOURCE_DISABLED_VALUES = {"", "0", "false", "none", "null", "off"}


def pets_source_ids(value):
    """Interpret GitHub's common false/empty placeholders as no source list."""
    return [s.strip() for s in str(value or "").split(",")
            if s.strip().lower() not in PETS_SOURCE_DISABLED_VALUES]


PETS_SOURCES = pets_source_ids(env("PETS_SOURCES", ""))
PETS_EDITORIAL_PROFILE = env("PETS_EDITORIAL_PROFILE", "pets_expert")
PETS_CONTENT_MODE = env("PETS_CONTENT_MODE", "evergreen").strip().lower()
# cache годится для dry-run, но не для гарантий "ровно один раз" в production.
# Реальную отправку разрешает только явно подтверждённый durable backend.
PETS_STATE_BACKEND = env("PETS_STATE_BACKEND", "cache").strip().lower()
PETS_REQUIRE_DURABLE_STATE = env("PETS_REQUIRE_DURABLE_STATE", "1") == "1"
PETS_AI_ENABLED = env("PETS_AI_ENABLED", "0") == "1"
PETS_IMAGE_PROVIDER = env("PETS_IMAGE_PROVIDER", "wikimedia").strip().lower()
PETS_DEMO_BRIEFS = env("PETS_DEMO_BRIEFS", "0") == "1"
# Curated original Russian evergreen queue.  It has no dependency on a paid
# model and is the only PETS content path permitted to publish automatically.
PETS_EVERGREEN_QUEUE = env("PETS_EVERGREEN_QUEUE", "0") == "1"
# PETS 3.1 external sources and paid/editorial AI are independent, explicit
# gates.  They are disabled in every default local and GitHub Actions run.
PETS_EXTERNAL_SOURCES = env("PETS_EXTERNAL_SOURCES", "0") == "1"
PETS_OFFICIAL_SOURCES = pets_source_ids(env("PETS_OFFICIAL_SOURCES", "fda_cvm,openfda,cdc_healthy_pets,frontiers_vet"))
PETS_GENERATOR_MODE = env("PETS_GENERATOR_MODE", "mock").strip().lower()
PETS_ALLOW_LIVE_AI = env("PETS_ALLOW_LIVE_AI", "0") == "1"
PETS_MAX_GIGACHAT_GENERATIONS = int(env("PETS_MAX_GIGACHAT_GENERATIONS", "0"))
# GitHub Contents API keeps PETS state on a dedicated branch. It is versioned
# and uses an optimistic SHA precondition; the workflow concurrency group
# serializes normal runs. Disabled until PETS_STATE_BACKEND=github.
PETS_STATE_REPOSITORY = env("PETS_STATE_REPOSITORY") or env("GITHUB_REPOSITORY")
PETS_STATE_BRANCH = env("PETS_STATE_BRANCH", "pets-state")
PETS_STATE_PATH = env("PETS_STATE_PATH", "pets/pets_channel.db")
PETS_STATE_BASE_BRANCH = env("PETS_STATE_BASE_BRANCH", "main")
PETS_STATE_GITHUB_TOKEN = env("PETS_STATE_GITHUB_TOKEN") or env("GITHUB_TOKEN")
PETS_GITHUB_API_URL = env("PETS_GITHUB_API_URL", "https://api.github.com")

# ---------- VK AGRO AUTOPILOT ----------
# VK не использует Telegram credentials и включается только явным флагом.
# Изображения с сайтов-источников потенциально защищены авторским правом,
# поэтому без отдельного подтверждения прав публикуется только текст.
VK_ACCESS_TOKEN = env("VK_ACCESS_TOKEN")
VK_GROUP_ID = env("VK_GROUP_ID")
VK_PUBLISH = env("VK_PUBLISH", "0") == "1"
VK_PUBLISH_LIMIT = int(env("VK_PUBLISH_LIMIT", "1"))
VK_SELF_CHECK = env("VK_SELF_CHECK", "0") == "1"
VK_TELEGRAM_URL = env("VK_TELEGRAM_URL", "")
VK_SOURCE_IMAGES_ALLOWED = env("VK_SOURCE_IMAGES_ALLOWED", "0") == "1"
VK_API_VERSION = env("VK_API_VERSION", "5.199")
VK_TIMEOUT_SEC = int(env("VK_TIMEOUT_SEC", "30"))
VK_RETRIES = int(env("VK_RETRIES", "2"))

# ---------- редакционный слой ----------
# Источник «Новости дня»: csv список разделов (пока один; архитектура — список).
NEWS_SOURCES = [u.strip() for u in env("NEWS_SOURCE_URL", "https://habr.com/ru/news/").split(",") if u.strip()]
NEWS_EVERY = int(env("NEWS_EVERY", "5"))            # новость после N успешных CASE-публикаций
NEWS_MIN_CHARS = int(env("NEWS_MIN_CHARS", "400"))  # минимум текста новости
NEWS_MAX_AGE_DAYS = int(env("NEWS_MAX_AGE_DAYS", "7"))
SOFT_DEDUP_DAYS = int(env("SOFT_DEDUP_DAYS", "7"))  # компания/тема «недавняя» окно
