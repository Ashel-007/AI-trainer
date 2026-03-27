import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from gigachat_client import analyze_speech
from config import VK_TOKEN
import queue_manager
import time
import logging
import sys
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def send_message(vk, user_id: int, message: str):
    """Отправляет сообщение пользователю"""
    try:
        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=0
        )
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")

def get_video_url(vk, owner_id: int, video_id: int) -> str:
    """Получает прямую ссылку на видео через VK API"""
    try:
        video_info = vk.video.get(
            videos=f"{owner_id}_{video_id}",
            extended=0
        )
        
        if video_info and 'items' in video_info and len(video_info['items']) > 0:
            files = video_info['items'][0].get('files', {})
            url = files.get('mp4_1080') or files.get('mp4_720') or files.get('mp4_480') or files.get('mp4_360')
            if url:
                logging.info(f"Ссылка на видео получена")
            return url
        return None
    except Exception as e:
        logging.error(f"Ошибка получения видео: {e}")
        return None

def get_document_url(vk, owner_id: int, doc_id: int) -> str:
    """Получает ссылку на документ через VK API"""
    try:
        logging.info(f"Запрашиваю документ: {owner_id}_{doc_id}")
        
        # docs.getById ожидает строку вида "owner_id_doc_id"
        doc_info = vk.docs.getById(docs=f"{owner_id}_{doc_id}")
        
        logging.info(f"Ответ от docs.getById: {doc_info}")
        
        if doc_info and len(doc_info) > 0:
            doc = doc_info[0]
            ext = doc.get('ext', '')
            title = doc.get('title', '')
            url = doc.get('url', '')
            
            logging.info(f"Документ: title={title}, ext={ext}, url={url[:100] if url else 'None'}")
            
            # Проверяем, что это видеофайл
            if ext in ['mp4', 'avi', 'mov', 'mkv', 'mpg', 'webm']:
                logging.info(f"Найден видео-документ: {ext}")
                return url
            else:
                logging.info(f"Документ не является видео (расширение: {ext})")
                return None
        
        logging.warning("Документ не найден")
        return None
    except Exception as e:
        logging.error(f"Ошибка получения документа: {e}")
        logging.error(traceback.format_exc())
        return None

def extract_video_from_attachments(vk, attachments):
    """Извлекает видео из вложений"""
    
    # Случай 1: attachments в виде словаря
    if isinstance(attachments, dict):
        logging.info(f"Обрабатываем словарь attachments")
        
        # Ищем все возможные вложения (attach1, attach2 и т.д.)
        for key, value in attachments.items():
            if key.startswith('attach') and not key.endswith('_type'):
                # Это ID вложения
                attach_id = value
                # Ищем соответствующий тип
                type_key = key + '_type'
                attach_type = attachments.get(type_key)
                
                if attach_type == 'video' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        owner_id, video_id = parts
                        logging.info(f"Видео вложение найдено: {owner_id}_{video_id}")
                        return get_video_url(vk, int(owner_id), int(video_id))
                
                elif attach_type == 'doc' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        owner_id, doc_id = parts
                        logging.info(f"Документ вложение найдено: {owner_id}_{doc_id}")
                        url = get_document_url(vk, int(owner_id), int(doc_id))
                        if url:
                            return url
    
    # Случай 2: attachments в виде списка
    if isinstance(attachments, list):
        for item in attachments:
            if isinstance(item, dict):
                if item.get('type') == 'video':
                    video = item.get('video', {})
                    return get_video_url(vk, video.get('owner_id'), video.get('id'))
                elif item.get('type') == 'doc':
                    doc = item.get('doc', {})
                    ext = doc.get('ext', '')
                    if ext in ['mp4', 'avi', 'mov', 'mkv']:
                        return doc.get('url')
    
    return None

def process_event(event, vk):
    """Обрабатывает одно событие от VK"""
    user_id = event.user_id
    text = event.text.strip() if event.text else ""
    
    logging.info(f"Сообщение от пользователя {user_id}")
    
    # Получаем вложения
    attachments = None
    if hasattr(event, 'attachments'):
        attachments = event.attachments
        logging.info(f"Тип attachments: {type(attachments)}")
    
    # Пытаемся извлечь видео из вложений
    video_url = None
    if attachments:
        video_url = extract_video_from_attachments(vk, attachments)
    
    # Если есть видео — обрабатываем видео
    if video_url:
        logging.info(f"Обнаружено видео для пользователя {user_id}, URL: {video_url[:80]}...")
        send_message(vk, user_id, "Видео получено. Добавляю в очередь обработки...")
        send_message(vk, user_id, "Обработка займёт 1-2 минуты. Я пришлю результат сюда.")
        queue_manager.enqueue_video(user_id, video_url)
        return
    
    # Если нет видео, но есть текст — анализируем текст
    if text:
        if text == "/help":
            send_message(vk, user_id, "Доступные команды:\n/help - справка")
            return
        
        logging.info(f"Анализирую текст: {text[:50]}...")
        send_message(vk, user_id, "Анализирую выступление...")
        
        try:
            feedback = analyze_speech(text)
            send_message(vk, user_id, f"Анализ выступления:\n\n{feedback}")
            logging.info(f"Анализ отправлен пользователю {user_id}")
        except Exception as e:
            send_message(vk, user_id, "Ошибка при анализе. Попробуйте позже.")
            logging.error(f"Ошибка анализа: {e}")
        return
    
    # Если ничего нет
    send_message(vk, user_id, "Пришли текст выступления или загрузи видео с речью!")

def run_bot():
    """Запускает бота"""
    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    
    queue_manager.set_vk_instance(vk, send_message)
    
    print("=" * 50)
    print("Бот-тренер публичных выступлений ЗАПУЩЕН")
    print("=" * 50)
    print("Бот слушает сообщения и видео...")
    print("Для остановки нажмите Ctrl+C")
    print("=" * 50)
    
    while True:
        try:
            longpoll = VkLongPoll(vk_session)
            
            for event in longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    try:
                        process_event(event, vk)
                    except Exception as e:
                        logging.error(f"Ошибка обработки события: {e}")
                        logging.error(traceback.format_exc())
                        
        except Exception as e:
            logging.error(f"Ошибка подключения: {e}")
            logging.info("Переподключение через 5 секунд...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    run_bot()
