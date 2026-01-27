import sqlite3
import logging
from config import DATABASE_FILE

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Класс для управления базой данных
    """
    
    def __init__(self, db_path=DATABASE_FILE):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """
        Инициализация базы данных
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Создание таблицы для хранения истории публикаций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS published_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT UNIQUE,
                channel_id TEXT,
                publish_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                title TEXT
            )
        ''')
        
        # Создание таблицы для хранения настроек парсинга
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parsing_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE,
                selectors TEXT,
                templates TEXT
            )
        ''')
        
        # Создание таблицы для хранения журнала ошибок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT,
                message TEXT,
                traceback TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"База данных инициализирована: {self.db_path}")
    
    def is_article_published(self, article_id: str, channel_id: str) -> bool:
        """
        Проверка, была ли статья уже опубликована в канале
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM published_articles 
            WHERE article_id = ? AND channel_id = ?
        ''', (article_id, channel_id))
        
        result = cursor.fetchone()[0]
        conn.close()
        
        return result > 0
    
    def save_published_article(self, article_id: str, channel_id: str, title: str):
        """
        Сохранение информации об опубликованной статье
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO published_articles (article_id, channel_id, title)
                VALUES (?, ?, ?)
            ''', (article_id, channel_id, title))
            conn.commit()
            logger.info(f"Статья {article_id} сохранена как опубликованная в канале {channel_id}")
        except sqlite3.IntegrityError:
            logger.warning(f"Статья {article_id} уже существует в канале {channel_id}")
        finally:
            conn.close()
    
    def log_error(self, level: str, message: str, traceback: str = None):
        """
        Запись ошибки в журнал
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO error_log (level, message, traceback)
            VALUES (?, ?, ?)
        ''', (level, message, traceback))
        
        conn.commit()
        conn.close()
    
    def get_parsing_settings(self, domain: str):
        """
        Получение настроек парсинга для домена
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT selectors, templates FROM parsing_settings
            WHERE domain = ?
        ''', (domain,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {'selectors': result[0], 'templates': result[1]}
        return None
    
    def save_parsing_settings(self, domain: str, selectors: str, templates: str):
        """
        Сохранение настроек парсинга для домена
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO parsing_settings (domain, selectors, templates)
            VALUES (?, ?, ?)
        ''', (domain, selectors, templates))
        
        conn.commit()
        conn.close()