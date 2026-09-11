# AI Автоматизация | Бизнес — production case pipeline

Автономный конвейер «нашёл кейс → доказал фактами → опубликовал» для канала
`AI Автоматизация | Бизнес` (chat id `-1003553181515`, bot `@shared_platform_bot`).

## 1. Что это и зачем
Не новостной ретеллер, а разбор бизнес-кейсов внедрения AI/автоматизации:
ПРОБЛЕМА → РЕШЕНИЕ → КАК АВТОМАТИЗИРОВАЛИ → РЕЗУЛЬТАТ → ЦИФРЫ → ПРИМЕНИМОСТЬ → CTA.
Каждый факт поста обязан быть доказан цитатой из исходной статьи (evidence
validator). AI-выдумки не публикуются никогда: детерминированная гейт-проверка
стоит перед публикацией, а не после.

## 2. Архитектура (поток)
```
SOURCES ─► DISCOVERY ─► FETCH ─► EXTRACTION ─► CLASSIFIER V2 (rules-first gate)
   ├─ business_case ─────────────► CASE SCHEMA ─► EVIDENCE VALIDATOR ─► POST ─┬─ TELEGRAM
   ├─ needs_review ─► AI ARBITRATION (GigaChat, опц.) ─► (business_case →↑)   └─ REJECT
   └─ how_to / news / other ────────────────────────────────────────────► REJECT (в БД/отчёт)

NEWS_SOURCE_URL ─► DISCOVERY ─► FETCH ─► EXTRACT ─► гейты ─► GigaChat Lite
   ─► Russian Language Guard ─► Hashtags ─► Dedup ─► TELEGRAM   («Новость дня»)
```
* `RULES = first gate`, AI — судья только для пограничных (`needs_review`) и
  опциональная переработка поста; никогда «придумай кейс».
* Провал валидации CASE/evidence/поста ⇒ материал уходит в `review` (не
  публикуется), а не молча отсекается.
* **Редакционный слой** (поверх ядра, ядро не изменено): обязательный русский
  язык финального поста (`langguard`), контролируемые хэштеги-словарь
  (`hashtags`), отдельная линия «Новость дня» (`news`), журнал публикаций с
  hard/soft dedup и race-safe claim (`storage`), генератор навигации
  (`navigation`, только текст — Telegram/пины не трогает).

## 3. Структура
```
core/context.py                 JobContext (чинит контракт runner.py)
case_pipeline/
  config.py                     все настройки из env
  adapters.py                   MindboxAdapter/IBMAdapter/ZapierAdapter/SalesforceAdapter
                                (+ заготовка Bitrix24 как how-to источник, отключена)
  httpclient.py                 requests: UA, timeout, retry, polite-delay, кэш
  extraction.py                 JSON-LD+OG+trafilatura(strict/default), quality good/partial/poor/failed
  classifier_lib/               замороженный V2 (byte-identical) + SHA256 self-check
  ai.py                         AIProvider: Null/Fake/GigaChat; structured verdict + валидация цитат
  case_model.py                 CASE-схема, детерминированная сборка из цитат
  evidence.py                   validator: цитата∈текст (ws-норм), числа заземлены, компания в тексте
  postgen.py                    RU-шаблон поста (+опц. GigaChat-переработка с post-validation)
  langguard.py                  Russian Language Guard: RU PASS / EN FAIL / 1 retry / review
  hashtags.py                   контролируемый словарь тегов TYPE/DOMAIN/COMPANY/OWN (3–5 на пост)
  news.py                       линия «Новость дня» (настраиваемый NEWS_SOURCE_URL, гейты, Lite)
  navigation.py                 генератор текста навигации по истории публикаций (без Telegram)
  storage.py                    SQLite: дедуп (канон URL + content hash), статусы, publications
                                (журнал: hashtags/content_type/company/claim для race safety)
  telegram.py                   sendMessage, retry, dry-run; токен не логируется
  pipeline.py                   оркестратор: lanes, статусы, артефакты runs/, backlog-очередь
run_case_pipeline.py            CLI entrypoint
jobs/ai_automation/job.py       интеграция в платформу (runner.py), остальные 9 job-ов не тронуты
tests/                          80 unit+integration теста (pytest), офлайн, герметично к секретам
```

## 4. Запуск
```powershell
# dry-run (по умолчанию; ничего не публикует):
python run_case_pipeline.py
# production-режим (≤1 пост за запуск):
$env:CASE_PUBLISH="1"; python run_case_pipeline.py
# только отдельные источники / лимит:
python run_case_pipeline.py --sources mindbox,ibm --limit 1
# проверка бота и явного TEST-сообщения в канал (не считается публикацией):
python run_case_pipeline.py --test-telegram
# счётчики статусов из БД:
python run_case_pipeline.py --status
# «Новость дня»: сгенерировать из NEWS_SOURCE_URL без публикации:
python run_case_pipeline.py --test-news
# текст навигации по истории публикаций (Telegram/пины не трогает):
python run_case_pipeline.py --rebuild-navigation
# платформа целиком (runner, все 10 каналов; ai_automation = этот пайплайн):
$env:DRY_RUN="1"; python runner.py
```
Публикация возможна только при обоих условиях: `CASE_PUBLISH=1` И не `DRY_RUN=1`.

## 5. Environment variables (секретов в коде нет)
| Переменная | Назначение | Default |
|---|---|---|
| `AI_AUTOMATION_BOT_TOKEN` | токен @shared_platform_bot (fallback `POSTER_BOT_TOKEN`) | — (публикация BLOCKED без него) |
| `AI_AUTOMATION_CHAT_ID` | канал | `-1003553181515` |
| `GIGACHAT_API_KEY` | включает AI-арбитраж review-lane и AI-переработку поста (REST на `requests`, SDK не нужен; ключ = base64 client_id:client_secret → OAuth на `GIGACHAT_AUTH_URL`, scope `GIGACHAT_API_PERS`) | — (review остаётся review) |
| `GIGACHAT_MODEL` | модель (кастомные `GIGACHAT_AUTH_URL`/`GIGACHAT_BASE_URL`/`GIGACHAT_SCOPE`) | `GigaChat-2` (Lite-tier; Pro/Max не используются без нужды) |
| `CASE_DB_PATH` | SQLite (единый путь для app и планировщика) | `data/ai_case_pipeline.db` |
| `CASE_RUNS_DIR` | артефакты прогонов | `runs/` |
| `CASE_PUBLISH` | `1` — разрешить публикацию | `0` |
| `CASE_PUBLISH_LIMIT` | макс. постов за запуск | `1` |
| `CASE_MAX_PER_SOURCE` | свежих URL на источник за запуск | `4` |
| `CASE_SOURCES` | csv источников | `mindbox,ibm,zapier,salesforce` |
| `NEWS_SOURCE_URL` | csv разделов «Новости дня» (пока один; архитектура — список) | `https://habr.com/ru/news/` |
| `NEWS_EVERY` | новость после N успешных CASE-публикаций | `5` |
| `NEWS_MIN_CHARS`, `NEWS_MAX_AGE_DAYS` | минимум текста / максимум возраста новости | `400 / 7` |
| `SOFT_DEDUP_DAYS` | окно «недавняя компания» для понижения приоритета | `7` |
| `FETCH_TIMEOUT_SEC`, `FETCH_RETRIES`, `POLITE_DELAY_SEC` | сетевая вежливость | `40/2/1.2` |
| `DRY_RUN` | режим runner-платформы | `0` |

## 6. Как добавить новый источник
Один подкласс в `case_pipeline/adapters.py`: задать `catalog`(ы), регэксп
`url_rx`/`href_rx`, при необходимости `accept()`; зарегистрировать в `ADAPTERS`
и добавить имя в `CASE_SOURCES`. Классификатор, evidence-валидатор, пост-ген
ничего о сайтах не знают — правки ядра не нужны.

## 7. Дедупликация и статусы
* **Hard dedup** (запрет повтора): канонический URL (`scheme://host без
  www/нижний регистр/путь`, utm/ga/fbclid/# выкинуты), content hash (sha256 от
  ws+lower-текста), `case_id`/`news_id` и журнал `publications`
  (`case_published()`). Опубликованный материал не возвращается в очередь.
  Переживает перезапуск (всё в SQLite).
* **Soft dedup** (пониоритет, не запрет): компания из `recent_companies()`
  (окно `SOFT_DEDUP_DAYS`) уходит в конец backlog-очереди; свежий материал
  публикуется раньше. Через окно компания снова равна другим.
* Статусы кандидата: `new → fetched → extracted → classified →
  review|rejected|case_built → post_ready → publishing → published | failed`
  (`failed` после 3 попыток не перебирается; `review` живёт до арбитража/человека).
* **Race safety**: перед отправкой материал атомарно захватывается
  `claim_for_publish()` (`post_ready → publishing`, SQLite `UPDATE ... WHERE
  status='post_ready'`, rowcount). Второй параллельный процесс получает False и
  пропускает. Зависший `publishing` старше часа возвращается в `post_ready`
  (`recover_stale_claims`).
* `--publish` сначала обрабатывает свежие URL источников, затем (если лимит не
  исчерпан) публикует backlog `post_ready`: soft-dedup → confidence DESC.
  Telegram-ошибка НЕ пишет `published` (release_claim → review).

## 7a. Редакционный слой
* **Русский для иностранных источников**: CASE/evidence собираются на языке
  источника, затем `postgen` (GigaChat Lite) делает RU-пост; `langguard`
  проверяет итог. Бренд/продукты/числа/URL сохраняются, перевод не имеет права
  добавить число (сверка цифровых последовательностей).
* **Russian Language Guard** (`langguard.guard`): доля RU-слов ≥0.6 ⇒ PASS
  (латинские бренды/аббревиатуры/URL/хэштеги вычитаются из знаменателя);
  английский доминирует ⇒ FAIL ⇒ 1 retry через Lite ⇒ снова FAIL ⇒ `review`
  (публикация запрещена).
* **Хэштеги** (`hashtags`): контролируемый словарь, 3–5 на пост =
  1 TYPE (`#Кейс`/`#НовостьДня`/`#Разбор`) + 1–2 DOMAIN (`#CRM`,
  `#Маркетинг`, `#Продажи`, `#Клиенты`, `#Документы`, `#HR`, `#Производство`,
  `#Логистика`, `#Финансы`, `#Аналитика`, `#Ecommerce`, fallback
  `#Автоматизация`) + 1 COMPANY (санитизированная, из словаря или чистое имя)
  (+1 OWN при явном указании). AI не задаёт теги свободно: `apply_to_post`
  заменяет хэштег-строку на словарную.
* **Publication history** (`publications`): publication_id, case_id/news_id,
  canonical_url, content_hash, company, content_type, hashtags,
  telegram_message_id, published_at, source_url, status — журнал для
  навигации и аналитики (какие компании/направления/сколько кейсов и новостей).
* **Навигация** (`--rebuild-navigation`): читает историю, группирует реальные
  теги TYPE/DOMAIN/COMPANY + OWN-проекты, пишет `data/navigation.txt` и в
  `runs/<ts>/`. Telegram НЕ трогает (никаких авто-пинов) — текст закрепляет
  человек.

## 7b. «Новость дня» (`news.py`)
* Источник настраивается через `NEWS_SOURCE_URL` (csv; архитектура — список,
  можно добавить источник 2/3 без правок ядра). Дефолт — `habr.com/ru/news/`.
* Pipeline: `NEWS_SOURCE_URL → discovery → fetch → extract → гейты →
  GigaChat Lite (JSON: headline_ru/summary_ru/company/facts) → validate_news →
  Russian Language Guard → hashtags → dedup → Telegram`.
* Гейты допуска (иначе `review`/skip, выдуманных новостей нет): источник
  определён, текст ≥`NEWS_MIN_CHARS`, релевантность AI/автоматизации, не
  реклама, возраст ≤`NEWS_MAX_AGE_DAYS`, content-hash/URL/case_id дедуп,
  `facts` — дословные фрагменты источника, числа summary ⊆ источник,
  summary = 2–3 предложения, пост ≤1200 знаков, guard PASS.
* Счётчик: новость публикуется, когда `count_cases_since_last_news() ≥
  NEWS_EVERY` (по умолчанию 5). Считаются только успешные реальные CASE-посты
  (`publications.ok=1 AND content_type='case'`); dry-run/review/rejected/ошибки
  не увеличивают. Новость — отдельный `content_type='news'`, после неё счётчик
  обнуляется.
* Failure isolation: недоступный/пустой news-источник не ломает CASE-контур
  (`process_news` не бросает наружу; вызов обёрнут в try в `pipeline.run`).

## 8. Quality gates (правила допуска)
1. Классификатор V2 (holdout-80 validated) сказал `business_case` — иначе
   reject/review. V2 не изменяется; его SHA256 сверяется при импорте.
2. Извлечение ≥700 знаков (иначе `review`, посты из огрызков не пишутся).
3. CASE: компания+проблема+внедрение+evidence-цитаты обязательны
   (`validate_case_shape`), и обязателен числовой эффект (метрика или
   числовой результат) — материалы «без цифр» в review: позиционирование
   канала требует экономический эффект.
4. `evidence.validate_case`: каждая цитата — дословная подстрока источника
   (unicode-quote/whitespace нормализованы), каждое число — из источника,
   компания присутствует в тексте. Провал ⇒ `review`, НЕ публикация.
5. Финальный `postgen.validate_post`: в готовом посте ни одного числа вне
   источника, запрещённые хайп-фразы, компания упомянута, длина ≤3900.
6. Лимит 1–2 качественных поста в день (default 1/запуск; в GHA слоты 06/14/22 UTC).

## 9. Что делает AI и как ограничена галлюцинация
* `ai.py::arbitrate` — только для `needs_review`: строгий JSON-вердикт
  {decision, company, problem_quote, implementation_quote, ...}.
  Вердикт валидируется детерминированно (`validate_verdict`): цитаты обязаны
  содержаться в исходном тексте; AI-«бизнес-кейс» с недоказуемой цитатой =
  провал арбитража ⇒ остаётся в review.
* `postgen`-переработка (GigaChat): RU-текст по уже собранным CASE-фактам;
  результат проходит `validate_post` (числа ⊆ источник, анти-хайп, компания).
  Провал ⇒ откат к детерминированному шаблону.
* Без `GIGACHAT_API_KEY`: правила-гейт и шаблоны работают, review-материалы
  копятся в review (не публикуются), английский источник получает пост-шаблон
  с цитатами оригинала в RU-каркасе.

## 10. Источники и их характер (решение на данных holdout-80)
* **Mindbox** (`/journal/cases/`) — RU клиентские кейсы, основной источник.
* **IBM Case Studies** (`/case-studies/`) — EN крупные внедрения.
* **Zapier Customer Stories**, **Salesforce Customer Stories** — EN автоматизация.
* **Bitrix24 Журнал** — по валидации это how-to/обучающие материалы, а не
  клиентские кейсы; в sources НЕ включён (адаптер-заготовка в коде есть).
* robots-этика: только публичные каталоги-страницы, 1 GET на URL, UA браузера,
  `POLITE_DELAY_SEC` между запросами к домену, timeout/retry.

## 11. Планировщик (GitHub Actions / локально)
Production-расписание: **09:00 и 18:00 МСК** = **06:00 и 15:00 UTC**, максимум
1 публикация за запуск; нет качественного материала — тишина (мусор не постится).
Локально (основной режим сегодня):
```powershell
$env:CASE_PUBLISH="1"   # + токены в User env: setx AI_AUTOMATION_BOT_TOKEN ...
# Task Scheduler, 09:00 и 18:00 МСК:
powershell -Command "Set-Location 'D:\Bots TG\tg_platform_10bots'; python run_case_pipeline.py --publish --limit 1"
```
GHA: `.github/workflows/case_pipeline.yml` (отдельный от платформенного
`daily_jobs.yml`, его не трогает) — cron `0 6 * * *` и `0 15 * * *`,
`--publish --limit 1`, concurrency-группа (запрет параллельных прогонов),
`actions/cache` на `data/` (дедуп/история переживают рестарт), секреты
`AI_AUTOMATION_BOT_TOKEN`/`AI_AUTOMATION_CHAT_ID`/`GIGACHAT_API_KEY` + var
`NEWS_SOURCE_URL`. Перед включением: (1) git-репозиторий (папка пока НЕ git),
(2) секреты в repo Secrets, (3) БД-персистентность — cache эвиктится после ~недели
простоя: при нерегулярных запусках лучше внешний volume/хост, иначе возможен
повторный просмотр старых URL (самих републикаций защищённо: publications).

## 12. Troubleshooting
| Симптом | Причина/действие |
|---|---|
| `no bot token` в логе | не задан `AI_AUTOMATION_BOT_TOKEN` |
| `400 chat not found` | бот не админ канала / неверный `AI_AUTOMATION_CHAT_ID` |
| много `failed: fetch` | источник меняет вёрстку — чинится только адаптер |
| всё в `rejected` | классификатор не нашёл кейсов (норма для части страниц каталогов-переключений) |
| `review` с «case/evidence:» | AI/человек должен досмотреть; см. `runs/<ts>/report.md` |
| `classifier integrity check failed` | правка frozen V2 — восстановить копию из `parser_poc_results/classifier_v2_validation` |

## 13. Что ЗАПРЕЩЕНО архитектурой
* публиковать текст с числами, которых нет в источнике (валидаторы блокируют);
* менять `case_pipeline/classifier_lib/*.py` (checksum-гейт);
* трогать 9 существующих каналов и логику `runner.py`;
* хранить секреты в файлах/логах (токен не выводится никогда; только имена env).

## 14. Тесты
```powershell
python -m pytest tests -q      # 80 passed, офлайн, без реальных запросов/постинга
```
Покрытие: извлечение (RU/EN, baseline-repro), классификация 5 lanes +
tamper-checksum, CASE (valid/missing company/missing evidence), evidence
(valid quote / hallucinated quote / hallucinated number), дедуп (URL
variants/hash/statuses/publish bookkeeping), postgen (структура/invented
number/hype/company), telegram mock (ok/400/dry-run/no token), полный
интеграционный прогон с mock-сетью и mock-публикацией + повторный прогон
(dedup proof) + review-lane без AI. Редакционный слой: langguard (RU/EN/бренды/
retry/повторный FAIL), hashtags (словарь/лимит 3–5/санитизация/замена строки),
publication history (поля/hard dedup/счётчик/soft-dedup окно/claim race/stale
recovery), news (настройка источника/генерация 2–3 преддл./выдуманное число→
review/нерелевантное→rejected/дубль не переопубликуется/мёртвый источник не
ломает CASE), navigation (группировка реальных тегов/файл/без Telegram),
soft-dedup приоритет очереди, news-slot на 5-й публикации, backlog-публикация.
Тесты герметичны: autouse-фикстура отключает реальные секреты/провайдеры.
