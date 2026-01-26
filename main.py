import asyncio
import logging
from datetime import datetime
from config import POSTER_BOT_TOKEN, CHANNELS_CONFIG_FILE, PUBLISH_INTERVAL_HOURS
from telegram_bot import TelegramBot
from parser import ArticleParser
from processor import ContentProcessor
from database import DatabaseManager
from optimization import PerformanceMonitor, Optimizer, CacheManager, optimize_article_processing, optimize_channel_processing

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class ChannelManager:
    """
    Класс для управления чат-каналами
    """
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.channels = {}
        self.performance_monitor = PerformanceMonitor(db_manager)
        self.optimizer = Optimizer(self.performance_monitor)
        self.cache_manager = CacheManager(max_size=1000)
        self.load_channels_config()
    
    def load_channels_config(self):
        """
        Загрузка конфигурации каналов из файла
        """
        import json
        try:
            with open(CHANNELS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.channels = config.get('channels', {})
            logger.info(f"Загружено {len(self.channels)} каналов из конфигурации")
        except FileNotFoundError:
            logger.warning(f"Файл конфигурации {CHANNELS_CONFIG_FILE} не найден")
            self.channels = {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации каналов: {e}")
            self.channels = {}
    
    def add_channel(self, channel_id, sources, keywords, style, hashtags=None):
        """
        Добавление нового канала
        """
        self.channels[channel_id] = {
            'sources': sources,
            'keywords': keywords,
            'style': style,
            'hashtags': hashtags or []
        }
        
        # Сохраняем обновленную конфигурацию
        self.save_channels_config()
    
    def remove_channel(self, channel_id):
        """
        Удаление канала
        """
        if channel_id in self.channels:
            del self.channels[channel_id]
            self.save_channels_config()
    
    def save_channels_config(self):
        """
        Сохранение конфигурации каналов в файл
        """
        import json
        try:
            with open(CHANNELS_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'channels': self.channels}, f, ensure_ascii=False, indent=2)
            logger.info("Конфигурация каналов сохранена")
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации каналов: {e}")
    
    def get_all_channels(self):
        """
        Получение всех каналов
        """
        return self.channels

async def publish_articles(bot, parser, processor, channel_manager, db_manager):
    """
    Публикация статей в каналы
    """
    logger.info("Начало публикации статей...")
    
    # Применяем оптимизацию к каналам
    channels = await optimize_channel_processing(channel_manager.get_all_channels(), channel_manager.performance_monitor)
    
    for channel_id, settings in channels.items():
        logger.info(f"Обработка канала {channel_id}")
        
        # Начинаем замер времени для обработки канала
        channel_manager.performance_monitor.start_timer(f'process_channel_{channel_id}')
        
        sources = settings.get('sources', [])
        keywords = settings.get('keywords', [])
        style = settings.get('style', 'neutral')
        hashtags = settings.get('hashtags', [])
        
        for source in sources:
            try:
                logger.info(f"Получение статей из {source}")
                
                # Начинаем замер времени для парсинга из источника
                channel_manager.performance_monitor.start_timer(f'parse_from_{source}')
                
                articles = await parser.get_articles_from_source(source, keywords)
                
                # Завершаем замер времени для парсинга
                channel_manager.performance_monitor.stop_timer(f'parse_from_{source}')
                
                # Оптимизированная обработка статей с учетом хэштегов
                processed_articles = await optimize_article_processing(articles, processor, channel_manager.cache_manager, style=style, keywords=keywords, hashtags=hashtags)
                
                for i, processed_article in enumerate(processed_articles):
                    article = articles[i]
                    # Проверяем, не публиковалась ли уже эта статья в этом канале
                    if not db_manager.is_article_published(article['id'], channel_id):
                        # Начинаем замер времени для отправки статьи
                        channel_manager.performance_monitor.start_timer(f'send_article_to_{channel_id}')
                        
                        if processed_article:
                            # Отправляем статью в канал
                            await bot.send_article(channel_id, processed_article)
                            
                            # Завершаем замер времени для отправки статьи
                            channel_manager.performance_monitor.stop_timer(f'send_article_to_{channel_id}')
                            
                            # Сохраняем информацию о публикации
                            db_manager.save_published_article(
                                article['id'],
                                channel_id,
                                article['title']
                            )
                        else:
                            logger.warning(f"Не удалось обработать статью {article['id']} для канала {channel_id}")
                    else:
                        logger.info(f"Статья {article['id']} уже была опубликована в канале {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка при обработке источника {source} для канала {channel_id}: {e}")
                # Записываем ошибку в базу данных
                db_manager.log_error('ERROR', f"Ошибка при обработке источника {source} для канала {channel_id}", str(e))
        
        # Завершаем замер времени для обработки канала
        channel_manager.performance_monitor.stop_timer(f'process_channel_{channel_id}')

async def schedule_publications(bot, parser, processor, channel_manager, db_manager):
    """
    Планировщик публикаций
    """
    while True:
        try:
            await publish_articles(bot, parser, processor, channel_manager, db_manager)
            
            # Выводим статистику производительности
            stats = channel_manager.performance_monitor.get_stats()
            if stats:
                logger.info("Статистика производительности:")
                for operation, data in stats.items():
                    logger.info(f"  {operation}: {data['count']} выполнений, "
                              f"среднее время {data['average_time']:.2f}s")
            
            # Получаем рекомендации по оптимизации
            recommendations = channel_manager.optimizer.get_optimization_recommendations()
            if recommendations:
                logger.info("Рекомендации по оптимизации:")
                for rec in recommendations:
                    logger.info(f"  - {rec}")
            
            logger.info(f"Ожидание {PUBLISH_INTERVAL_HOURS} часов до следующей публикации...")
            await asyncio.sleep(PUBLISH_INTERVAL_HOURS * 3600)  # Переводим часы в секунды
        except Exception as e:
            logger.error(f"Ошибка в планировщике публикаций: {e}")

async def main():
    """
    Основная функция запуска бота
    """
    logger.info("Запуск бота...")
    
    # Инициализация базы данных
    db_manager = DatabaseManager()
    
    # Инициализация менеджера каналов
    channel_manager = ChannelManager(db_manager)
    
    # Инициализация телеграм-бота
    bot = TelegramBot(BOT_TOKEN, channel_manager)
    
    # Инициализация парсера статей
    parser = ArticleParser()
    
    # Инициализация процессора контента
    processor = ContentProcessor()
    
    # Запуск планировщика публикаций как фоновая задача
    scheduler_task = asyncio.create_task(
        schedule_publications(bot, parser, processor, channel_manager, db_manager)
    )
    
    # Запуск бота
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
    finally:
        # Отменяем задачу планировщика при завершении
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("Планировщик публикаций остановлен")

if __name__ == '__main__':

    asyncio.run(main())
