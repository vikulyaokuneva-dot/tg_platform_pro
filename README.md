# TG Platform — Production Architecture

## Концепция
1 BOT TOKEN → N Telegram Channels  
Jobs = data, not code

## Запуск
export POSTER_BOT_TOKEN=...
python -m app

## Добавить новый канал
1. Добавить CHAT_ID в env
2. Добавить job в app/jobs/registry.py
