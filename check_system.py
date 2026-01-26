#!/usr/bin/env python3
"""
Скрипт для проверки работоспособности системы добавления хэштегов
"""

import json
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from processor import ContentProcessor
from config import CHANNELS_CONFIG_FILE


def check_hashtags_system():
    """
    Проверка системы добавления хэштегов
    """
    print("Проверка системы добавления хэштегов...")
    
    # Загружаем конфигурацию каналов
    try:
        with open(CHANNELS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"+ Конфигурация каналов загружена: {CHANNELS_CONFIG_FILE}")
    except FileNotFoundError:
        print(f"- Файл конфигурации не найден: {CHANNELS_CONFIG_FILE}")
        return False
    except Exception as e:
        print(f"- Ошибка при загрузке конфигурации: {e}")
        return False
    
    # Проверяем наличие хэштегов в конфигурации
    channels_with_hashtags = 0
    total_channels = len(config.get('channels', {}))
    
    for channel_id, settings in config.get('channels', {}).items():
        if 'hashtags' in settings and settings['hashtags']:
            channels_with_hashtags += 1
            print(f"  - Канал {channel_id} имеет {len(settings['hashtags'])} хэштегов")
    
    print(f"+ Из {total_channels} каналов, {channels_with_hashtags} имеют настроенные хэштеги")
    
    # Проверяем работу ContentProcessor
    processor = ContentProcessor()
    
    # Создаем тестовую статью
    test_article = {
        'title': 'Тестовая статья',
        'content': 'Это тестовое содержание статьи для проверки системы хэштегов.',
        'id': 'test_1'
    }
    
    # Тестируем добавление хэштегов
    test_hashtags = ['#тест', '#хэштег', '#статья']
    
    try:
        processed_article = processor.process_article(
            test_article,
            style='neutral',
            keywords=['тест'],
            hashtags=test_hashtags
        )
        
        if all(tag in processed_article for tag in test_hashtags):
            print("+ Система добавления хэштегов работает корректно")
        else:
            print("- Хэштеги не были добавлены к статье")
            return False
            
    except Exception as e:
        print(f"- Ошибка при обработке статьи: {e}")
        return False
    
    # Проверяем ограничение по длине
    long_content = "Это очень длинный текст. " * 1000  # Создаем длинный текст
    
    long_article = {
        'title': 'Длинная статья для тестирования ограничения по длине',
        'content': long_content,
        'id': 'test_2'
    }
    
    try:
        processed_long_article = processor.process_article(
            long_article,
            style='neutral',
            keywords=['длинный'],
            hashtags=test_hashtags
        )
        
        if len(processed_long_article) <= 4000:
            print("+ Ограничение по длине сообщения работает корректно")
        else:
            print("- Сообщение превышает допустимую длину")
            return False
            
        if all(tag in processed_long_article for tag in test_hashtags):
            print("+ Хэштеги сохраняются даже при ограничении по длине")
        else:
            print("- Хэштеги не сохраняются при ограничении по длине")
            return False
            
    except Exception as e:
        print(f"- Ошибка при обработке длинной статьи: {e}")
        return False
    
    print("\n+ Все проверки системы добавления хэштегов пройдены успешно!")
    return True


def main():
    print("=" * 60)
    print("СИСТЕМА ПРОВЕРКИ РАБОТОСПОСОБНОСТИ ХЭШТЕГОВ")
    print("=" * 60)
    
    success = check_hashtags_system()
    
    print("\n" + "=" * 60)
    if success:
        print("РЕЗУЛЬТАТ: + Система добавления хэштегов работает корректно")
    else:
        print("РЕЗУЛЬТАТ: - Обнаружены проблемы в системе хэштегов")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)