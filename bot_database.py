import sqlite3
import logging
from datetime import datetime

class Database:
    def __init__(self, db_file="bot_database.db"):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_table()

    def create_table(self):
        """Создает таблицу, если она не существует"""
        with self.connection:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def url_exists(self, url):
        """Проверяет, была ли ссылка уже опубликована"""
        with self.connection:
            result = self.cursor.execute("SELECT id FROM posted_urls WHERE url = ?", (url,)).fetchone()
            return bool(result)

    def add_url(self, url, category):
        """Добавляет ссылку в базу"""
        try:
            with self.connection:
                self.cursor.execute("INSERT INTO posted_urls (url, category) VALUES (?, ?)", (url, category))
                return True
        except sqlite3.IntegrityError:
            # Ссылка уже есть (дубликат), игнорируем
            return False
        except Exception as e:
            logging.error(f"Database error: {e}")
            return False

    def close(self):
        self.connection.close()
