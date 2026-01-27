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
        clean_content = re.sub(r'\s+', ' ', content.strip())
        summary = f"*{title}*\n\n{clean_content}"
        return summary
    
    def _informal_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Неформальный стиль подачи материала
        """
        clean_content = re.sub(r'\s+', ' ', content.strip())
        summary = f"🚀 *{title}*\n\n{clean_content}\n\n#Интересно #Новости"
        return summary
    
    def _formal_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Формальный стиль подачи материала
        """
        clean_content = re.sub(r'\s+', ' ', content.strip())
        summary = f"*{title}*\n\n{clean_content}\n\nИсточник: {keywords[0] if keywords else 'Неизвестный'}"
        return summary
    
    def _promotional_style(self, title: str, content: str, keywords: List[str]) -> str:
        """
        Продвигающий стиль подачи материала
        """
        clean_content = re.sub(r'\s+', ' ', content.strip())
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
        
        if keywords is None:
            keywords = []
        if hashtags is None:
            hashtags = []
        
        if style in self.styles:
            processed_content = self.styles[style](title, content, keywords)
        else:
            logger.warning(f"Неизвестный стиль '{style}', используется нейтральный стиль по умолчанию")
            processed_content = self.styles['neutral'](title, content, keywords)
        
        # Добавляем хэштеги к обработанному контенту
        if hashtags:
            hashtag_str = ' '.join(hashtags)
            combined_content = f"{processed_content}\n\n{hashtag_str}"
            max_length = 4000
            
            if len(combined_content) > max_length:
                # Если добавление хэштегов превышает лимит, обрезаем основной контент
                # ИСПРАВЛЕНИЕ: Вычитаем 3 символа для "..."
                available_length = max_length - len(hashtag_str) - 2 - 3
                processed_content = processed_content[:available_length] + "..."
                combined_content = f"{processed_content}\n\n{hashtag_str}"
            processed_content = combined_content
        
        # Ограничиваем длину поста по требованиям Telegram
        max_length = 4000
        if len(processed_content) > max_length:
            # ИСПРАВЛЕНИЕ: Вычитаем 3 символа для "..."
            processed_content = processed_content[:max_length - 3] + "..."
        
        return processed_content
    
    def remove_water(self, text: str) -> str:
        """
        Удаление "воды" из текста (лишних слов и фраз)
        """
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
        
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text
