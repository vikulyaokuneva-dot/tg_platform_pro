# PETS 4.3 — Production Readiness

Дата: 2026-10-26. Ветка: `feat/pets-3-1-autonomous`, PR #1.

## Что фактически проверено

Выполнен реальный ограниченный source-only запуск только по PMC OA и Frontiers
через официальные NCBI PMC E-utilities. Использовались новая временная SQLite
и временный каталог `tmp_out/pets_4_3_source_only_pmc_frontiers_20261026`.
`PETS_PUBLISH=0`; GigaChat и Telegram не вызывались; production `pets-state`
не изменялась.

| Показатель | Результат |
| --- | ---: |
| Найдено записей | 22 |
| Удалено как дубликаты DOI/PMCID | 1 |
| Уникальных кандидатов | 21 |
| `editorially_ready` | 1 |
| `needs_editorial_review` | 20 |
| Новых публикаций/AI-вызовов | 0 / 0 |

Единственный пригодный factual brief: *Is the Cat–Owner Relationship Related to
Cat–Wildlife Conflicts?* — кошка, поведение, DOI
`10.3390/ani16172777`, PMC `PMC13565001`, CC BY. Он может быть передан одному
ограниченному вызову GigaChat только после отдельного разрешения владельца;
после этого всё ещё обязательны проверка текста и конкретная лицензированная
фотография. Сейчас он **не является готовой публикацией**.

Причины 20 review-кандидатов: нерелевантная аудитория — 4, медицинская тема —
3, недостаточно фактов — 7, редакционная неопределённость — 2, лицензия — 3,
слишком узкая выборка — 1, ложное совпадение терминов — 1. Это категории
первичной причины, а не повод ослаблять фильтры.

## Очередь и отсутствие дублей

Локальный regression-тест подтверждает, что четыре evergreen-поста и factual
queue изолированы: curated URL не может стать factual queue entry, а factual
запись не требует Python allowlist. В production SQLite сейчас имеются четыре
разрешённые evergreen-записи и две старые demo-записи со статусом `post_ready`.
Их quarantine намеренно **не применялась**, потому что это изменило бы
production state без отдельного согласия. После разрешённой миграции demo будут
переведены в `demo_ready`; опубликованный пост №39 не затрагивается.

## Durable state

Read-only проверка актуальной ветки `pets-state` подтвердила сохранность поста
№39: материал `cat-predictable-space` имеет `status=published`,
`telegram_message_id=39`, а ledger публикаций содержит успешную запись от
`2026-10-25T21:00:47Z`. Восстановление SQLite использует GitHub Contents API;
каждый checkpoint передаёт SHA, а конфликт 409/422 fail-closed. После успешной
отправки сбой checkpoint не переводит материал обратно в очередь, поэтому
дубликат не создаётся.

## Workflow и включение

Текущий `pets_channel.yml` по расписанию не включает `PETS_EXTERNAL_SOURCES`
и `PETS_ALLOW_LIVE_AI`: он не ищет статьи и не запускает GigaChat. Отдельный
`pets_source_replenishment.yml` готовит только source-only артефакт, не получает
bot/GigaChat secrets и не трогает durable SQLite. Его плановый job остаётся
пустым, пока владелец явно не задаст GitHub Variable
`PETS_SOURCE_REPLENISH_ENABLED=1`.

Для ручного controlled replenishment нужны одновременно:

1. `use_external_sources=true` и `use_live_gigachat=true` в manual workflow;
2. `gigachat_generation_limit` в пределах 1–10;
3. новый отдельный checkbox `allow_production_queue=true`;
4. `PETS_STATE_BACKEND=github` и корректные `PETS_STATE_REPOSITORY`,
   `PETS_STATE_BRANCH`, `PETS_STATE_PATH`;
5. `PETS_PUBLISH=0` до отдельного решения о реальной отправке.

`PETS_PUBLISH=1` требуется только для Telegram-доставки. Его не следует
включать вместе с первым AI/queue испытанием.

## Расходы и вывод

Source-only сбор не использует платный AI. Стоимость генерации определяется
моделью и тарифом аккаунта, а не кодом PETS; проект её не знает и не проверял
баланс. Для первого испытания расходы строго ограничены одним вызовом
(`gigachat_generation_limit=1`). Для ориентировочного расчёта нужно умножить
input + output tokens одного preview на тариф подключённой модели; перед
запуском следует проверить баланс и выбранную модель в кабинете GigaChat.
Актуальные правила и цены следует брать только из официальных
[тарифов GigaChat API](https://developers.sber.ru/docs/ru/gigachat/api/tariffs):
они различаются для физлиц, ИП и юрлиц и могут меняться.

В текущем виде источников **не хватает для одного нового поста ежедневно**:
за этот запуск получен один пригодный brief, тогда как целевая очередь — семь.
PR #1 готов к merge только как безопасная инфраструктура при выключенных
`PETS_PUBLISH`, AI и production queue. Он не готов к включению ежедневной
автономной публикации: сначала нужны дополнительные разрешённые evidence
sources или подтверждённое увеличение стабильно пригодных factual briefs.
