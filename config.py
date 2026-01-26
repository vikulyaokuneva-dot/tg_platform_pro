import os

print("--- DEBUG TOKEN START ---")
# Проверяем наличие переменных окружения
print(f"ENV 'POSTER_BOT_TOKEN' exists: {'POSTER_BOT_TOKEN' in os.environ}")
print(f"ENV 'BOT_TOKEN' exists: {'BOT_TOKEN' in os.environ}")

# Читаем токен
token = os.getenv('POSTER_BOT_TOKEN', os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE'))

# Выводим информацию о токене (безопасно)
print(f"Loaded token type: {type(token)}")
print(f"Loaded token length: {len(token)}")
if len(token) > 5:
    print(f"Token starts with: '{token[:3]}...'")
    print(f"Token ends with: '...{token[-3:]}'")
    
    # Проверка на пробелы (частая ошибка)
    if ' ' in token:
        print("!!! WARNING: Token contains spaces! !!!")
    if '\n' in token:
        print("!!! WARNING: Token contains newlines! !!!")
else:
    print("Token is too short or default placeholder used.")

print("--- DEBUG TOKEN END ---")

# Файл конфигурации каналов
CHANNELS_CONFIG_FILE = 'channels_hashtags_config.json'

# Файл базы данных
DATABASE_FILE = 'bot_database.db'

# Периодичность публикаций (в часах)
PUBLISH_INTERVAL_HOURS = 6

# Максимальное количество попыток повторного подключения
MAX_RETRIES = 3

# Таймаут между попытками
RETRY_DELAY = 5

# Путь к файлу логов

LOG_FILE_PATH = 'bot.log'




