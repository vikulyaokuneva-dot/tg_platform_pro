# PETS 2.0 — реализованная безопасная подготовка

## Что изменено

- Только `.github/workflows/pets_channel.yml` получил `contents: write`.
  Другие workflow не изменялись. В нём применяется временный `${{ github.token }}`
  и только для ветки состояния через GitHub Contents API.
- `case_pipeline/pets_durable_state.py` восстанавливает SQLite из `pets-state`,
  создаёт ветку только при первом запуске, передаёт SHA при записи и не
  перезаписывает состояние при конфликте 409/422. Ошибка восстановления или
  checkpoint блокирует реальную отправку.
- `case_pipeline/pets_briefs.py` содержит три оригинальных русскоязычных черновика.
  Они не являются рерайтом/переводом источника и никогда сами не вызывают Telegram.
- `jobs/pets/job.py` формирует artifact: Markdown-черновики, файлы трёх фото и
  технический результат. Retention — 14 дней.
- PETS не записывает токены, Chat ID или иные идентификаторы получателя в durable
  SQLite. Состояние содержит только материал, дедупликацию, текст, публичные URL
  источников и атрибуцию изображений.

## Ограничения доступа

`github.token` действует только на время конкретного workflow run и в пределах
репозитория. Он не должен заменяться personal access token. Ветку `pets-state`
следует держать в приватном репозитории, закрыть от прямой записи и предоставить
доступ к Actions/artifacts только нужным участникам. Черновики и ссылки не секреты,
но это рабочие материалы, поэтому artifact намеренно живёт лишь 14 дней.

## Безопасное включение dry-run

Установить repository variables: `PETS_STATE_BACKEND=github`,
`PETS_STATE_BRANCH=pets-state`, `PETS_STATE_PATH=pets/pets_channel.db` и, если нужно,
`PETS_STATE_REPOSITORY=<owner/repository>`. Оставить `PETS_PUBLISH=0`.
Запустить workflow вручную с `controlled_publish=false` и просмотреть artifact.
Cron отсутствует; AGRO и AI Automation не менялись.
