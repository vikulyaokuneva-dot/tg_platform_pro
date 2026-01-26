import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

class ContentProcessor:
    """
    Класс для обработки и сокращения контента
    """
    
    def __init__(self):
        # Словарь со стилями подачи материала
        self.styles = {
            'neutral': self._neutral_style,
            'informal': self._informal_style,
            'formal': self._formal_style,
            'promotional': self._promotional_style
        }
    
    def _neutral_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Нейтральный стиль подачи материала
        """
        # Убираем лишние переносы строк и пробелы
        clean_content = re.sub(r'\s+', ' ', content.strip())
        
        # Оставляем только основную информацию
        summary = f"*{title}*\n\n{clean_content}"
        
        return summary
    
    def _informal_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Неформальный стиль подачи материала
        """
        # Убираем лишние переносы строк и пробелы
        clean_content = re.sub(r'\s+', ' ', content.strip())
        
        # Добавляем немного эмоций и неформальности
        summary = f"🚀 *{title}*\n\n{clean_content}\n\n#Интересно #Новости"
        
        return summary
    
    def _formal_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Формальный стиль подачи материала
        """
        # Убираем лишние переносы строк и пробелы
        clean_content = re.sub(r'\s+', ' ', content.strip())
        
        # Формальный стиль с акцентом на достоверность информации
        summary = f"*{title}*\n\n{clean_content}\n\nИсточник: {keywords[0] if keywords else 'Неизвестный'}"
        
        return summary
    
    def _promotional_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Продвигающий стиль подачи материала
        """
        # Убираем лишние переносы строк и пробелы
        clean_content = re.sub(r'\s+', ' ', content.strip())
        
        # Добавляем призыв к действию и продвигающие элементы
        summary = f"🔥 *{title}*\n\n{clean_content}\n\nЧитайте подробнее по ссылке выше! 💬"
        
        return summary
    
    def process_article(self, article: Dict, style: str = 'neutral', keywords: List[str] = None, hashtags: List[str] = None) -> str:
        """
        Обработка статьи в соответствии с заданным стилем и ключевыми словами
        """
        if not article or 'title' not in article or 'content' not in article:
            logger.error("Некорректная статья для обработки")
            return ""
        
        title = article['title']
        content = article['content']
        
        # Если ключевые слова не переданы, используем пустой список
        if keywords is None:
            keywords = []
        
        # Если хэштеги не переданы, используем пустой список
        if hashtags is None:
            hashtags = []
        
        # Применяем соответствующий стиль
        if style in self.styles:
            processed_content = self.styles[style](title, content, keywords)
        else:
            logger.warning(f"Неизвестный стиль '{style}', используется нейтральный стиль по умолчанию")
            processed_content = self.styles['neutral'](title, content, keywords)
        
        # Добавляем хэштеги к обработанному контенту
        if hashtags:
            hashtag_str = ' '.join(hashtags)
            # Проверяем, что добавление хэштегов не превысит максимальную длину
            combined_content = f"{processed_content}\n\n{hashtag_str}"
            max_length = 4000
            if len(combined_content) > max_length:
                # Если добавление хэштегов превышает лимит, обрезаем основной контент
                available_length = max_length - len(hashtag_str) - 2  # 2 символа для \n\n
                processed_content = processed_content[:available_length] + "..."
                combined_content = f"{processed_content}\n\n{hashtag_str}"
            processed_content = combined_content
        
        # Ограничиваем длину поста по требованиям Telegram (4096 символов максимум)
        max_length = 4000
        if len(processed_content) > max_length:
            processed_content = processed_content[:max_length] + "..."
        
        return processed_content
    
    def remove_water(self, text: str) -> str:
        """
        Удаление "воды" из текста (лишних слов и фраз)
        """
        # Список слов и фраз, которые считаются "водой"
        water_phrases = [
            r'\b(?:читайте также|подробнее читайте|больше информации|в заключение|как сообщается)\b',
            r'\b(?:по словам|сообщает|рассказывает|отмечает)\b',
            r'\s+(?:в результате|в связи с этим|в то же время|с другой стороны)\s+',
            r'(?:--|--\s|--\s+|\s--\s+|\s--)',
            r'(?:\.{2,}|…{2,})'
        ]
        
        clean_text = text
        for phrase in water_phrases:
            clean_text = re.sub(phrase, ' ', clean_text, flags=re.IGNORECASE)
        
        # Удаляем лишние пробелы
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text