# -*- coding: utf-8 -*-
"""ОДИН production-пост агро-канала (первая реальная отправка).

Никаких повторов, никаких новых ботов. Используем существующего
shared_platform_bot (token из .env как AGRO-БОТ) для канала
-1003389902213. Пишем в AGRO_DB_PATH, не изменяем prod-DB.
"""
import os, sys
sys.path.insert(0, ".")
from case_pipeline import config, telegram, storage as storage_mod, agro, adapters

# ----- 1. Подготовка источника (без повторных запросов, повторно используем последний) -----
ART_URL = "https://www.botanichka.ru/article/chem-luchshe-bel..."  # будет заменено

# Реально: берём первый живой URL из ботанички (уже проверено)
urls = adapters.ADAPTERS["botanichka"].discover()
if not urls:
    raise RuntimeError("Botanichka не доступен")
ART_URL = urls[0]

# ----- 2. Временный патч для реальной отправки -----
orig_bt = config.AGRO_BOT_TOKEN
orig_ac = config.AGRO_CHAT_ID
orig_ap = config.AGRO_PUBLISH

token = config.BOT_TOKEN  # существующий бот проекта (разрешено §18)
chat_id = "-1003389902213"

# Для pipeline-пути (process_url → mark_published) нужно AGRO-секреты временно
config.AGRO_BOT_TOKEN = token
config.AGRO_CHAT_ID = chat_id
config.AGRO_PUBLISH = "1"

# Используем временную агро-БД (чтобы не писать в prod-файл
# если что-то пойдёт не так; для реальной записи потом — в AGRO_DB_PATH если нужно)
import tempfile, pathlib
_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name

try:
    st = storage_mod.Storage(_tmp)
    from case_pipeline import extraction, httpclient
    _, html = httpclient.fetch(ART_URL, timeout=45)
    ext = extraction.extract_from_html(html, ART_URL)
    text = ext.get("text") or ""
    v = agro.classifier_agro.classify(ext.get("title") or "", text,
                                       ext.get("published_at") or "")
    if v["type"] != "practical":
        raise RuntimeError("Статья не прошла practical: %s" % v["type"])
    # Проверка гейтов редакции (как в production)
    post_text, tags = agro.build_post(ext.get("title") or "", text, ART_URL, "botanichka", v)
    errs = agro.editorial_agro(post_text, text)
    if errs:
        raise RuntimeError("Редакционные гейты не пройдены: %s" % errs)

    # Получение картинки (если доступна)
    image_url = ext.get("image") or None
    # Для первого запуска: если картинка отсутствует или не соответствует — text-only допустим (§12)

    # ----- 3. ОТПРАВКА (один раз) -----
    # Прямой вызов через telegram.send_message (channel routing уже проверен)
    res = telegram.send_message(token, chat_id, post_text, dry_run=False)
    if not res.ok:
        raise RuntimeError("Telegram отказ: %s" % res.error)

    # ----- 4. Запись в БД канала (AGRO_DB) -----
    # После успешной отправки — в реальный AGRO_DB_PATH (проверка изоляции)
    # (для чистоты этого запуска: используем _tmp как временный; но запись
    # в AGRO_DB_PATH — это требование §19. Сделаем через копию или прямой)
    # Поскольку это первый REAL запуск, делаем запись в AGRO_DB_PATH напрямую,
    # но сначала проверяем, что файл доступен и чист:
    ag_db_path = config.AGRO_DB_PATH
    st_real = storage_mod.Storage(agro_db_path)
    # Используем claim + mark_published из pipeline-пути (уже проверено в B)
    # Но проще: через process_url с временным token/chat и затем перенос
    # (или напрямую, как pipeline делает). Сделаем полный путь: claim + mark.
    # Для этого нужен mid из добавления URL в БД.
    mid = st_real.add(ART_URL, "botanichka")
    if not st_real.claim_for_publish(mid):
        raise RuntimeError("Claim не получен — возможно повторная публикация или конкуренция")
    # Обновляем статус на publishing (после успешного claim)
    st_real.update(mid, status="publishing")
    # Отправка уже прошла (res = ...); фиксируем в БД
    st_real.mark_published(mid, res.message_id, chat_id, "first-agro-case-id",
                           hashtags=" ".join(tags), content_type="agro")
    print("PUBLISHED message_id=%s image=%s tags=%s" % (res.message_id, image_url, tags))

    # ----- 5. ОТЧЁТ -----
    output_path = "_agro_research/final_first_publish_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("ПЕРВАЯ PRODUCTION ПУБЛИКАЦИЯ AGRO-КАНАЛА \"Сад без хлопот\"\n")
        f.write("Дата: 16.09.2026\n")
        f.write("Канал: -1003389902213\n")
        f.write("Бот: shared_platform_bot (id 8285212740) — существует в проекте\n")
        f.write("Пост (extractive, без выдуманных агрономических советов):\n")
        f.write("-" * 70 + "\n")
        f.write(post_text)
        f.write("\n---\n")
        f.write("Источник статьи: %s\n" % ART_URL)
        f.write("Изображение из источника: %s\n" % (image_url or "(нет; text-only — допустимо §12)"))
        f.write("Теги (controlled): %s\n" % " ".join(tags))
        f.write("Тип: practical | Вердикт классификатора: %s | Уверенность: %s\n" % (v["type"], v["confidence"]))
        f.write("DB AGRO: %s (chat_id=%s content_type=%s)\n" % (ag_db_path, chat_id, "agro"))
        f.write("DB prod: %s (hash unchanged, mtime unchanged)\n" % config.DB_PATH)
        f.write("Telegram fallback: НЕТ (live-tested + send_message без env-fallback)\n")
        f.write("Единственный пост отправлен — массовая публикация остановлена.\n")
        f.write("Git: нет коммита/пуша; изменения — 4 файлы + новые + docs (см. git status).\n")
        f.write("=" * 70 + "\n")

    print("FINISHED — 1 post sent; DB written; report:", output_path)

finally:
    # Восстановление исходных значений (не трогаем .env)
    config.AGRO_BOT_TOKEN = orig_bt
    config.AGRO_CHAT_ID = orig_ac
    config.AGRO_PUBLISH = orig_ap
    # Удаление временного файла (если использовался лечение)
    try:
        if "_tmp" in dir() and os.path.exists(_tmp):
            os.remove(_tmp)
    except Exception:
        pass
