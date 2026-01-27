import asyncio
import time
import logging
from collections import defaultdict
from database import DatabaseManager

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Класс для мониторинга производительности системы
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.metrics = defaultdict(list)
        self.start_times = {}
    
    def start_timer(self, operation_name: str):
        """
        Начать отсчет времени для операции
        """
        self.start_times[operation_name] = time.time()
    
    def stop_timer(self, operation_name: str):
        """
        Остановить отсчет времени для операции и сохранить метрику
        """
        if operation_name in self.start_times:
            elapsed_time = time.time() - self.start_times[operation_name]
            self.metrics[operation_name].append(elapsed_time)
            del self.start_times[operation_name]
            logger.info(f"Операция {operation_name} заняла {elapsed_time:.2f} секунд")
            return elapsed_time
        return None
    
    def get_average_time(self, operation_name: str) -> float:
        """
        Получить среднее время выполнения операции
        """
        if operation_name in self.metrics and self.metrics[operation_name]:
            return sum(self.metrics[operation_name]) / len(self.metrics[operation_name])
        return 0.0
    
    def get_stats(self) -> dict:
        """
        Получить статистику по всем операциям
        """
        stats = {}
        for operation, times in self.metrics.items():
            if times:
                stats[operation] = {
                    'count': len(times),
                    'average_time': sum(times) / len(times),
                    'total_time': sum(times),
                    'min_time': min(times),
                    'max_time': max(times)
                }
        return stats

class Optimizer:
    """
    Класс для оптимизации работы системы
    """
    
    def __init__(self, performance_monitor: PerformanceMonitor):
        self.monitor = performance_monitor
        self.optimization_thresholds = {
            'parse_article': 5.0,  # Если парсинг статьи занимает больше 5 секунд
            'send_article': 2.0,   # Если отправка статьи занимает больше 2 секунд
            'process_article': 1.0 # Если обработка статьи занимает больше 1 секунды
        }
    
    async def optimize_parsing(self, sources: list) -> list:
        """
        Оптимизация процесса парсинга
        """
        optimized_sources = []
        
        for source in sources:
            # Проверяем, не находится ли источник в "черном списке" медленных источников
            avg_parse_time = self.monitor.get_average_time(f'parse_from_{source}')
            
            if avg_parse_time > self.optimization_thresholds['parse_article']:
                logger.warning(f"Источник {source} помечен как медленный (среднее время: {avg_parse_time:.2f}s)")
                # Можно добавить логику исключения или снижения частоты опроса этого источника
                continue
            
            optimized_sources.append(source)
        
        return optimized_sources
    
    async def adaptive_delay(self, operation_name: str, default_delay: float = 1.0) -> float:
        """
        Адаптивная задержка на основе производительности
        """
        avg_time = self.monitor.get_average_time(operation_name)
        
        if avg_time > self.optimization_thresholds.get(operation_name, default_delay * 2):
            # Увеличиваем задержку, если операция работает медленно
            adjusted_delay = default_delay * 1.5
            logger.info(f"Увеличена задержка для {operation_name} до {adjusted_delay}s из-за медленной производительности")
            return adjusted_delay
        else:
            return default_delay
    
    def get_optimization_recommendations(self) -> list:
        """
        Получить рекомендации по оптимизации
        """
        recommendations = []
        stats = self.monitor.get_stats()
        
        for operation, data in stats.items():
            if data['count'] > 5:  # Только если операция выполнялась более 5 раз
                if data['average_time'] > self.optimization_thresholds.get(operation, float('inf')):
                    recommendations.append(
                        f"Операция {operation} требует оптимизации: "
                        f"среднее время {data['average_time']:.2f}s, "
                        f"выполнено {data['count']} раз"
                    )
        
        return recommendations

class CacheManager:
    """
    Класс для управления кэшированием
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = {}
        self.access_order = []  # Для реализации LRU
    
    def get(self, key):
        """
        Получить значение из кэша
        """
        if key in self.cache:
            # Обновляем порядок доступа (LRU)
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def put(self, key, value):
        """
        Добавить значение в кэш
        """
        if key in self.cache:
            # Обновляем существующий ключ
            self.cache[key] = value
            self.access_order.remove(key)
            self.access_order.append(key)
        else:
            # Добавляем новый ключ
            if len(self.cache) >= self.max_size:
                # Удаляем самый старый элемент (LRU)
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]
            
            self.cache[key] = value
            self.access_order.append(key)
    
    def clear(self):
        """
        Очистить кэш
        """
        self.cache.clear()
        self.access_order.clear()

# Функции для интеграции с основной системой
async def optimize_article_processing(articles: list, processor, cache_manager: CacheManager, style: str = 'neutral', keywords: list = None, hashtags: list = None) -> list:
    """
    Оптимизированная обработка статей с использованием кэширования
    """
    processed_articles = []
    
    # Убедимся, что keywords и hashtags не равны None
    if keywords is None:
        keywords = []
    if hashtags is None:
        hashtags = []
    
    for article in articles:
        # Используем ID статьи как ключ для кэширования
        cache_key = f"processed_{article['id']}"
        cached_result = cache_manager.get(cache_key)
        
        if cached_result:
            # Используем кэшированный результат
            processed_articles.append(cached_result)
        else:
            # Обрабатываем статью и кэшируем результат
            processed_article = processor.process_article(article, style, keywords, hashtags)
            cache_manager.put(cache_key, processed_article)
            processed_articles.append(processed_article)
    
    return processed_articles

async def optimize_channel_processing(channels: dict, performance_monitor: PerformanceMonitor) -> dict:
    """
    Оптимизированная обработка каналов с учетом производительности
    """
    optimizer = Optimizer(performance_monitor)
    
    # Получаем оптимизированный список каналов
    optimized_channels = {}
    for channel_id, settings in channels.items():
        # Проверяем, не помечен ли канал как медленный
        avg_process_time = performance_monitor.get_average_time(f'process_channel_{channel_id}')
        
        if avg_process_time < 30.0:  # Если обработка канала занимает меньше 30 секунд
            optimized_channels[channel_id] = settings
        else:
            logger.warning(f"Канал {channel_id} помечен как медленный, пропускаем в этой итерации")
    
    return optimized_channels