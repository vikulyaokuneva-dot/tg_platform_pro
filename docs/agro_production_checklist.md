# Agro channel — production checklist (первый реальный запуск)

Статус на 16.09.2026: код готов, публикация ВЫКЛЮЧЕНА (секретов нет,
`AGRO_PUBLISH` не задан). Порядок включения — только по пунктам Rollout.
Архитектура и детали: `docs/agro_channel_implementation.md`.

## 1. Environment (GitHub Actions secrets / серверный env)

| Переменная | Что | Статус |
|---|---|---|
| `AGRO_BOT_TOKEN` | токен нового бота агро-канала (не существующего!) | ❌ не задан — включить после создания бота |
| `AGRO_CHAT_ID` | chat_id канала (формат `-100…` для приватных) | ❌ не задан |
| `AGRO_PUBLISH` | `"1"` — разрешает реальную отправку | ❌ намеренно не задан (по умолчанию dry-run) |
| `AGRO_SOURCES` | csv источников | опц. дефолт `botanichka,agroinvestor,gismeteo` |
| `AGRO_DB_PATH` | файл истории канала | опц. дефолт `data/agro_channel.db` (в кэше workflow `data/`) |
| `AGRO_PUBLISH_LIMIT` / `AGRO_MAX_PER_RUN` / `AGRO_MAX_AGE_DAYS` | лимиты прогона | опц. 1 / 3 / 5 |

Правила:
- [ ] секреты только из Secrets/ENV; в репозиторий не коммитить (`.env` в .gitignore);
- [ ] у нового бота — права `post_messages` в канале, канал добавлен к боту;
- [ ] НЕ использовать `AI_AUTOMATION_*`/prod-пары для агро (и наоборот).

## 2. Sources (состояние проверено dry-run 16.09, логи `_agro_research/`)

- [x] **Ботаничка** — RSS, практический конвейер канала (5/5 → post_ready).
- [x] **Агроинвестор** — RSS рабочий; контент сейчас `news` → копит `news_hold`
      до агро-News lane; журнал старше 5-дневного окна честно отклоняется.
- [x] **Gismeteo** — discovery/fetch/extract рабочие; вердикт честный `news`
      (в practical не продавливаем). Основной поставщик news-полосы после этапа 2.
- [ ] **Своё Фермерство** — `research required`: Nuxt SPA, no SSR links,
      robots `Disallow: /api/`, sitemap/RSS 404. Не подключать без API-исследования.

## 3. Safety (подтверждено кодом/прогонами)

- [x] DB isolation: агро пишет только в `AGRO_DB_PATH`; SHA256+mtime prod-БД
      не меняются за прогон (prod_readiness §B); `storage.py` не изменён.
- [x] Telegram routing: `credentials(channel)`; канал выбирает СВОЮ пару.
- [x] No fallback: `publish_post(channel="agro")` без секретов → честный стоп;
      `send_message` без явного чата/токена → стоп (env-fallback удалён);
      тесты `test_agro_publish_refuses_without_credentials`,
      `test_send_message_no_prod_chat_fallback`.
- [x] Dedup: внутриканальный (canonical+case_id+статусы) — повтор не публикует;
      между каналами — изоляция файлов; раса-сейф claim/release общий.
- [x] Dry-run по умолчанию: job публикует только при `AGRO_PUBLISH=1` и
      `DRY_RUN!=1` (конвенция runner). Планировщик и prod-workflow не менялись.
- [x] Ежесуточный риск нулевой: при текущих секретах job безопасен —
      runner подхватит `jobs/agro` и будет делать dry-run.

## 4. Tests (перед каждым включением)

- [ ] `python -m pytest -q` → все зелёные (база: 111 prod + 21 agro = 132).
- [ ] `python _agro_research/prod_readiness_check.py` (не публикует; транспорт
      перехватывает Telegram) → §B hash неизменен, §C живые счётчики.
- [ ] Классификатор на 4 реальных статьях: `signals_probe.py` (3 practical,
      ньюс-сводки — не practical).
- [ ] Посты: нет выдуманных чисел (гейт «числа ⊆ источника»), нет артефактов,
      ru-language guard, теги только контролируемый словарь, заголовок
      источника сохранён, layout ≠ WB case.

## 5. Rollout (порядок строгий)

1. **Credentials**: создать бота+канал, завести `AGRO_BOT_TOKEN`/`AGRO_CHAT_ID`
   (пока БЕЗ `AGRO_PUBLISH`).
2. **Dry-run в CI**: прогнать `daily_jobs` (или вручную `python runner.py` с
   `DRY_RUN=1`) — проверить `runs/agro` артефакты и summary (`published:0`).
3. **Тестовая публикация** (вне расписания): `AGRO_PUBLISH=1` + один прогон;
   visually сверить пост в канале (форматирование MarkdownV2, ссылка, теги).
   Первая отправка — осознанный action пользователя, не агента.
4. **Наблюдение** 2–3 дня: свежесть/дублей/реакции; `publications` агро-БД;
   лимит 1 пост/прогон не менять раньше времени.
5. **Scheduler**: после наблюдения — включить `AGRO_PUBLISH=1` в workflow-env
   (отдельный коммит; concurrency группа `case-pipeline` уже сериализует
   запуски, при росте — своя группа/кэш `agro-channel.db`).

Откат в любой точке: снять `AGRO_PUBLISH` → канал снова dry-run; код трогать
не нужно. Prod-канал не затронут ни на одном шаге.

## 6. Не делать (осознанные запреты текущего этапа)

- не включать LLM-polish агро-постов (сначала оценка extractive-качества);
- не «чинить» Gismeteo в practical;
- не парсить svoefermerstvo SPA кустарно;
- не объединять БД каналов без новой необходимости.
