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
AGRO_SOURCES = [s.strip() for s in env(
    "AGRO_SOURCES", "botanichka,agroinvestor,gismeteo").split(",") if s.strip()]

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

# ---------- редакционный слой ----------
# Источник «Новости дня»: csv список разделов (пока один; архитектура — список).
NEWS_SOURCES = [u.strip() for u in env("NEWS_SOURCE_URL", "https://habr.com/ru/news/").split(",") if u.strip()]
NEWS_EVERY = int(env("NEWS_EVERY", "5"))            # новость после N успешных CASE-публикаций
NEWS_MIN_CHARS = int(env("NEWS_MIN_CHARS", "400"))  # минимум текста новости
NEWS_MAX_AGE_DAYS = int(env("NEWS_MAX_AGE_DAYS", "7"))
SOFT_DEDUP_DAYS = int(env("SOFT_DEDUP_DAYS", "7"))  # компания/тема «недавняя» окно
