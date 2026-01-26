import asyncio
import logging
import os
import sys

# Импортируем компоненты из твоих файлов
from config import POSTER_BOT_TOKEN, CHANNELS_CONFIG_FILE
from telegram_bot import TelegramBot
from parser import ArticleParser
from processor import ContentProcessor
from database import DatabaseManager
from main import ChannelManager, publish_articles

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_one_cycle():
    """
    Запуск одного цикла публикации и выход
    """
    logger.info("Запуск одиночного цикла обновления...")
    
    # 1. Инициализация БД
    db_manager = DatabaseManager()
    
    # 2. Менеджер каналов
    channel_manager = ChannelManager(db_manager)
    
    # 3. Бот
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден!")
        sys.exit(1)
        
    bot = TelegramBot(BOT_TOKEN, channel_manager)
    
    # 4. Процессор контента
    processor = ContentProcessor()
    
    # 5. Парсер и запуск (используем контекстный менеджер для корректного закрытия сессий)
    async with ArticleParser() as parser:
        try:
            # Запускаем логику публикации из main.py
            await publish_articles(bot, parser, processor, channel_manager, db_manager)
            logger.info("Цикл публикации завершен успешно.")
        except Exception as e:
            logger.error(f"Ошибка в процессе публикации: {e}")
            raise e
        finally:
            # Закрываем сессию бота
            await bot.bot.session.close()

if __name__ == '__main__':
    asyncio.run(run_one_cycle())
