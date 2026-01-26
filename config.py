import os
import json
import logging

# --- Получение токена (как мы уже настроили) ---
print("--- DEBUG TOKEN START ---")
token = os.getenv('POSTER_BOT_TOKEN', os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE'))
if token and len(token) > 5:
    print(f"Token loaded (len: {len(token)})")
else:
    print("WARNING: Token not found or too short")
print("--- DEBUG TOKEN END ---")

BOT_TOKEN = token
DATABASE_FILE = 'bot_database.db'
PUBLISH_INTERVAL_HOURS = 6
MAX_RETRIES = 3
RETRY_DELAY = 5
LOG_FILE_PATH = 'bot.log'

# --- Генерация конфигурации каналов из переменных окружения ---
def get_channels_config():
    """
    Генерирует конфигурацию каналов на основе переменных окружения.
    Если переменная с ID канала не найдена, канал пропускается.
    """
    base_config = {}
    
    # 1. AI Automation
    chat_id = os.getenv('AI_AUTOMATION_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://techcrunch.com/category/artificial-intelligence/", "https://habr.com/ru/hub/artificial_intelligence/"],
            "keywords": ["AI", "GPT", "neural", "нейросети", "искусственный интеллект"],
            "style": "neutral",
            "hashtags": ["#AI", "#ArtificialIntelligence", "#Нейросети", "#Tech"]
        }

    # 2. Anekdoty (Юмор)
    chat_id = os.getenv('ANEKDOTY_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://www.anekdot.ru/last/good/"], # Нужен специфичный парсер для анекдотов, но пока оставим как пример
            "keywords": [], # Берем всё
            "style": "informal",
            "hashtags": ["#юмор", "#анекдот", "#смешно"]
        }

    # 3. Crypto Airdrops
    chat_id = os.getenv('CRYPTO_AIRDROPS_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://airdropalert.com/new-airdrops", "https://airdrops.io/"],
            "keywords": ["airdrop", "free", "claim", "раздача"],
            "style": "promotional",
            "hashtags": ["#Airdrop", "#Crypto", "#FreeCrypto", "#Халява"]
        }

    # 4. Crypto News
    chat_id = os.getenv('CRYPTO_NEWS_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://cointelegraph.com/", "https://forklog.com/"],
            "keywords": ["bitcoin", "ethereum", "blockchain", "криптовалюта", "биткоин"],
            "style": "neutral",
            "hashtags": ["#Crypto", "#Blockchain", "#Bitcoin", "#News"]
        }

    # 5. IT Humor
    chat_id = os.getenv('IT_HUMOR_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://habr.com/ru/hub/humor/", "https://dev.to/t/humor"],
            "keywords": ["humor", "meme", "юмор"],
            "style": "informal",
            "hashtags": ["#ITyuмор", "#ProgrammingHumor", "#DevLife"]
        }

    # 6. Personal Finance
    chat_id = os.getenv('PERSONAL_FINANCE_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://journal.tinkoff.ru/flows/money/", "https://www.banki.ru/news/"],
            "keywords": ["finance", "money", "budget", "финансы", "бюджет"],
            "style": "formal",
            "hashtags": ["#Финансы", "#Деньги", "#Бюджет", "#ЛичныеФинансы"]
        }

    # 7. Product Growth
    chat_id = os.getenv('PRODUCT_GROWTH_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://vc.ru/marketing", "https://gopractice.ru/"],
            "keywords": ["product", "growth", "marketing", "маркетинг", "продакт"],
            "style": "neutral",
            "hashtags": ["#ProductManagement", "#GrowthHacking", "#Marketing"]
        }

    # 8. Programming Dev
    chat_id = os.getenv('PROGRAMMING_DEV_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://dev.to/", "https://habr.com/ru/hub/programming/"],
            "keywords": ["python", "java", "code", "development", "программирование"],
            "style": "neutral",
            "hashtags": ["#Programming", "#Coding", "#Dev", "#Tutorial"]
        }

    # 9. Startups VC
    chat_id = os.getenv('STARTUPS_VC_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://techcrunch.com/startups/", "https://vc.ru/tribuna"],
            "keywords": ["startup", "venture", "funding", "стартап", "инвестиции"],
            "style": "promotional",
            "hashtags": ["#Startup", "#VC", "#Business", "#Tech"]
        }

    # 10. Stocks Investing
    chat_id = os.getenv('STOCKS_INVESTING_CHAT_ID')
    if chat_id:
        base_config[chat_id] = {
            "sources": ["https://www.investing.com/news/stock-market-news", "https://smart-lab.ru/"],
            "keywords": ["stocks", "market", "trading", "акции", "рынок"],
            "style": "formal",
            "hashtags": ["#Stocks", "#Investing", "#Market", "#Trading"]
        }

    return {"channels": base_config}

# Вместо чтения файла - генерируем словарь
CHANNELS_CONFIG = get_channels_config()

# Чтобы совместимость с остальным кодом осталась,
# нам нужно изменить ChannelManager, чтобы он брал конфиг из переменной,
# а не читал файл. Или мы можем перезаписать файл при запуске.
# Самый простой способ (чтобы не менять main.py) -> перезаписать файл конфига
CHANNELS_CONFIG_FILE = 'channels_hashtags_config.json'

def update_config_file():
    try:
        with open(CHANNELS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(CHANNELS_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"Config file {CHANNELS_CONFIG_FILE} generated successfully with {len(CHANNELS_CONFIG['channels'])} channels.")
    except Exception as e:
        print(f"Error generating config file: {e}")

# Запускаем обновление файла при импорте конфига
update_config_file()
