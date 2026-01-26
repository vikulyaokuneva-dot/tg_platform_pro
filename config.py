import os

# Токен телеграм-бота (получается от @BotFather)
BOT_TOKEN = os.getenv('POSTER_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

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
