import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

class TelegramBot:
    """
    Класс для работы с Telegram-ботом
    """
    def __init__(self, token, channel_manager):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.channel_manager = channel_manager
        
        # Регистрация обработчиков команд
        self.register_handlers()
    
    def register_handlers(self):
        """
        Регистрация обработчиков команд
        """
        self.dp.message(Command('start'))(self.handle_start)
        self.dp.message(Command('add_channel'))(self.handle_add_channel)
        self.dp.message(Command('remove_channel'))(self.handle_remove_channel)
        self.dp.message(Command('list_channels'))(self.handle_list_channels)
    
    async def handle_start(self, message: types.Message):
        """
        Обработка команды /start
        """
        await message.answer('Привет! Я бот для публикации статей в чат-каналы.')
    
    async def handle_add_channel(self, message: types.Message):
        """
        Обработка команды /add_channel
        """
        # Логика добавления канала
        await message.answer('Команда добавления канала')
    
    async def handle_remove_channel(self, message: types.Message):
        """
        Обработка команды /remove_channel
        """
        # Логика удаления канала
        await message.answer('Команда удаления канала')
    
    async def handle_list_channels(self, message: types.Message):
        """
        Обработка команды /list_channels
        """
        # Логика вывода списка каналов
        channels = self.channel_manager.get_all_channels()
        if channels:
            response = "Список активных каналов:\n"
            for channel_id, settings in channels.items():
                response += f"- {channel_id}: {settings['sources']}\n"
        else:
            response = "Нет активных каналов"
        
        await message.answer(response)
    
    async def start(self):
        """
        Запуск бота
        """
        logger.info("Telegram-бот запущен")
        await self.dp.start_polling(self.bot)
    
    async def send_article(self, channel_id, article_text):
        """
        Отправка статьи в указанный канал
        """
        try:
            await self.bot.send_message(chat_id=channel_id, text=article_text)
            logger.info(f"Статья отправлена в канал {channel_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи в канал {channel_id}: {e}")
            # В случае ошибки пробуем повторить отправку
            await self.retry_send_article(channel_id, article_text)
    
    async def retry_send_article(self, channel_id, article_text):
        """
        Повторная попытка отправки статьи в случае ошибки
        """
        from config import MAX_RETRIES, RETRY_DELAY
        
        for attempt in range(MAX_RETRIES):
            try:
                await asyncio.sleep(RETRY_DELAY)
                await self.bot.send_message(chat_id=channel_id, text=article_text)
                logger.info(f"Статья успешно отправлена в канал {channel_id} после {attempt + 1} попыток")
                return
            except Exception as e:
                logger.error(f"Попытка {attempt + 1} не удалась: {e}")
        

        logger.error(f"Не удалось отправить статью в канал {channel_id} после {MAX_RETRIES} попыток")

