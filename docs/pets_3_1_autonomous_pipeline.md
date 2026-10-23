# PETS 3.1 — автономный конвейер черновиков

## Назначение

PETS 3.1 готовит оригинальные русскоязычные черновики для канала «Азбука
питомца». Он не публикует их в Telegram. Обычный и GitHub Actions запуск
остаются forced dry-run: `PETS_PUBLISH=0`, cron отсутствует, вызов Telegram
не выполняется.

Конвейер не копирует и не переводит статьи. Адаптер отдаёт только короткие
проверяемые факты с URL, автором/организацией, датой, типом доказательства и
лицензией. Отдельный генератор создаёт самостоятельный текст; затем проходят
валидация фактов, проверка повторов и подбор фотографии Commons.

## Подключённые контракты источников

| ID | Официальный способ доступа | Права и назначение |
| --- | --- | --- |
| `fda_cvm` | [FDA Center for Veterinary Medicine](https://www.fda.gov/animal-veterinary), только официальный структурированный feed/API-wrapper | собственные материалы FDA — `PUBLIC_DOMAIN`; предупреждения о безопасности |
| `openfda` | [openFDA animal & veterinary API](https://api.fda.gov/animalandveterinary/event.json) | данные `CC0`; сигналы безопасности, не медицинские рекомендации |
| `cdc_healthy_pets` | [CDC Healthy Pets](https://www.cdc.gov/healthy-pets/), только официальный структурированный feed/API-wrapper | `PUBLIC_DOMAIN` только для собственных материалов CDC; third-party assets исключаются |
| `frontiers_vet` | [Frontiers in Veterinary Science](https://www.frontiersin.org/journals/veterinary-science/articles) | только article-level `CC_BY`; материалы с исключениями и third-party assets отклоняются |

Старые коммерческие и экспертные сайты остаются `reference_only` либо
`fact_check_only`. Их статьи не становятся сырьём для автоматического рерайта.

## Безопасные стадии

1. `pets_planner` выбирает неповторяющиеся evergreen-темы, чередуя кошек и собак.
2. `pets_sources` возвращает структурированные `Fact`, а не HTML-статью.
3. `pets_facts` проверяет URL, лицензию и доказательность. Лекарства,
   дозировки, экстренная помощь и недостаточно подтверждённые medical claims
   получают `review`.
4. `pets_generator` работает в `mock` по умолчанию. Макет всегда остаётся
   `review`; он не маскируется под готовый пост. Реальный GigaChat возможен
   только одновременно с `PETS_GENERATOR_MODE=gigachat`,
   `PETS_ALLOW_LIVE_AI=1` и `PETS_AI_ENABLED=1`.
5. `pets_images` принимает Commons-фото только с лицензией, автором,
   URL лицензии и доказанными тегами темы. Совпадения вида животного одного
   недостаточно.
6. `PetsStorage` сохраняет факты, тематический план, права на изображение и
   историю в существующей SQLite / ветке `pets-state`.

## GitHub Actions

Workflow **PETS channel (manual dry-run)** принимает три независимых флажка:

- `include_demo_briefs` — только три старых демонстрационных черновика;
- `use_external_sources` — включает официальные source adapters, но всё ещё
  не включает публикацию;
- `use_live_gigachat` — разрешает платный GigaChat. Его можно включать только
  после отдельного согласования владельца.

Артефакт 14 дней хранит `pets_preview.md`, `pets_media/`,
`pets_diagnostics.json`, `pets_sources_report.json` и
`pets_license_report.json`. В них нет токенов, секретов и полных ответов API.

## Что ещё нужно до 10 настоящих черновиков

Реальный сетевой dry-run и GigaChat намеренно не выполнялись в этой ветке:
такое действие требует отдельного подтверждения, поскольку оно обращается к
внешним источникам и может расходовать оплачиваемый лимит. После подтверждения
нужно вручную запустить workflow с `use_external_sources=true` и
`use_live_gigachat=true`, оставить `controlled_publish=false`, затем проверить
артефакт. Только фактически полученные внешние материалы можно считать
результатом критерия «10 новых черновиков».
