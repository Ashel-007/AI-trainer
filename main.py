# main.py - полностью исправленная версия с отправкой PDF в чат
# Поддерживает: текст, видео, анализ, улучшение, PDF экспорт

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import random
import time
import logging
import sys
import traceback
import os
import requests

from gigachat_client import analyze_speech, command_1
from config import VK_TOKEN
import queue_manager
from pdf_export import generate_export_message

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ========== ХРАНИЛИЩА ДАННЫХ ==========
user_texts = {}
user_last_analysis = {}


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def send_message(vk, user_id: int, message: str):
    """Отправляет текстовое сообщение пользователю"""
    try:
        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=random.randint(1, 1000000)
        )
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")


def send_pdf_to_user(vk, user_id: int, pdf_path: str) -> bool:
    """Отправляет PDF файл пользователю в диалог ВК"""
    try:
        # 1. Получаем сервер для загрузки документа
        upload_server = vk.docs.getMessagesUploadServer(type='doc', peer_id=user_id)
        
        # 2. Загружаем PDF файл
        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(upload_server['upload_url'], files=files)
            file_data = response.json()
        
        # 3. Сохраняем документ в VK
        saved_doc = vk.docs.save(file=file_data['file'], title='Анализ_выступления.pdf')
        
        # 4. Отправляем документ пользователю
        doc = saved_doc['doc']
        doc_id = doc['id']
        owner_id = doc['owner_id']
        
        vk.messages.send(
            user_id=user_id,
            attachment=f'doc{owner_id}_{doc_id}',
            random_id=random.randint(1, 1000000),
            message="📄 Ваш отчёт в формате PDF:"
        )
        
        logging.info(f"PDF отправлен пользователю {user_id}")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка отправки PDF: {e}")
        return False


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
        
        doc_info = vk.docs.getById(docs=f"{owner_id}_{doc_id}")
        logging.info(f"Ответ от docs.getById: {doc_info}")
        
        if doc_info and len(doc_info) > 0:
            doc = doc_info[0]
            ext = doc.get('ext', '')
            url = doc.get('url', '')
            
            if ext in ['mp4', 'avi', 'mov', 'mkv', 'mpg', 'webm']:
                logging.info(f"Найден видео-документ: {ext}")
                return url
        return None
    except Exception as e:
        logging.error(f"Ошибка получения документа: {e}")
        return None


def extract_video_from_attachments(vk, attachments):
    """Извлекает видео из вложений"""
    
    if isinstance(attachments, dict):
        logging.info(f"Обрабатываем словарь attachments")
        
        for key, value in attachments.items():
            if key.startswith('attach') and not key.endswith('_type'):
                attach_id = value
                type_key = key + '_type'
                attach_type = attachments.get(type_key)
                
                if attach_type == 'video' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        owner_id, video_id = parts
                        return get_video_url(vk, int(owner_id), int(video_id))
                
                elif attach_type == 'doc' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        owner_id, doc_id = parts
                        return get_document_url(vk, int(owner_id), int(doc_id))
    
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


# ========== ОСНОВНАЯ ЛОГИКА БОТА ==========
def process_event(event, vk):
    """Обрабатывает одно событие от VK"""
    global user_texts, user_last_analysis
    
    user_id = event.user_id
    text = event.text.strip().lower() if event.text else ""
    
    logging.info(f"Сообщение от пользователя {user_id}")
    
    # ===== 1. ПРОВЕРКА ВЛОЖЕНИЙ (ВИДЕО) =====
    video_url = None
    if hasattr(event, 'attachments') and event.attachments:
        attachments = event.attachments
        video_url = extract_video_from_attachments(vk, attachments)
    
    # Если есть видео — обрабатываем видео
    if video_url:
        logging.info(f"Обнаружено видео для пользователя {user_id}")
        send_message(vk, user_id, "🎬 Видео получено. Добавляю в очередь обработки...")
        send_message(vk, user_id, "⏳ Обработка займёт 1-2 минуты. Я пришлю результат сюда.")
        queue_manager.enqueue_video(user_id, video_url)
        return
    
    # ===== 2. КОМАНДЫ =====
    
    # Команда HELP
    if text in ['/help', 'help', 'помощь', 'справка', 'начать']:
        help_msg = """📋 ДОСТУПНЫЕ КОМАНДЫ

📝 /analyze или анализ
   → Анализ вашего выступления (структура, слова-паразиты, советы)

✨ /improve или улучши
   → Улучшение текста выступления

📄 /export или экспорт
   → Сохранить последний анализ в PDF

❓ /help или справка
   → Показать эту справку

ИНСТРУКЦИЯ:
1. Пришлите текст вашего выступления
2. Используйте /analyze для анализа
3. Используйте /improve для улучшения
4. Используйте /export для сохранения отчёта в PDF

🎥 Также можно отправить видео с речью — я проанализирую темп и паузы!"""
        send_message(vk, user_id, help_msg)
        return
    
    # Команда EXPORT (PDF)
    if text in ['/export', 'экспорт', 'export']:
        if user_id not in user_last_analysis:
            send_message(vk, user_id, "❌ Нет сохранённого анализа. Сначала выполните команду 'анализ'.")
            return
        
        send_message(vk, user_id, "📄 Создаю PDF отчёт... Подождите.")
        
        try:
            analysis_data = user_last_analysis[user_id]
            msg, pdf_path = generate_export_message(
                user_id,
                analysis_data['text'],
                analysis_data['analysis'],
                "text"
            )
            
            # Отправляем PDF в чат
            success = send_pdf_to_user(vk, user_id, pdf_path)
            
            if success:
                send_message(vk, user_id, "✅ PDF отчёт отправлен во вложении!")
            else:
                send_message(vk, user_id, f"✅ PDF отчёт создан, но не отправлен. Файл: {pdf_path}")
            
            logging.info(f"PDF создан для пользователя {user_id}: {pdf_path}")
            
        except Exception as e:
            error_msg = f"❌ Ошибка создания PDF: {str(e)}"
            send_message(vk, user_id, error_msg)
            logging.error(f"PDF ошибка: {e}")
        return
    
    # Команда ANALYZE (анализ текста)
    if text in ['анализ', '/analyze']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст вашего выступления!")
            return
        
        send_message(vk, user_id, "🔍 Анализирую выступление...")
        try:
            feedback = analyze_speech(user_texts[user_id])
            send_message(vk, user_id, f"📊 АНАЛИЗ ВЫСТУПЛЕНИЯ:\n\n{feedback}")
            
            user_last_analysis[user_id] = {
                'text': user_texts[user_id],
                'analysis': feedback
            }
            logging.info(f"Анализ выполнен для пользователя {user_id}")
        except Exception as e:
            send_message(vk, user_id, "❌ Ошибка анализа. Попробуйте позже.")
            logging.error(f"Ошибка analyze: {e}")
        return
    
    # Команда IMPROVE (улучшение текста)
    if text in ['улучши', '/improve']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст вашего выступления!")
            return
        
        send_message(vk, user_id, "✨ Улучшаю текст...")
        try:
            improved = command_1(user_texts[user_id])
            send_message(vk, user_id, f"🎤 УЛУЧШЕННОЕ ВЫСТУПЛЕНИЕ:\n\n{improved}")
            logging.info(f"Улучшение выполнено для пользователя {user_id}")
        except Exception as e:
            send_message(vk, user_id, "❌ Ошибка улучшения. Попробуйте позже.")
            logging.error(f"Ошибка command_1: {e}")
        return
    
    # ===== 3. СОХРАНЕНИЕ ТЕКСТА =====
    if text:
        user_texts[user_id] = text
        send_message(vk, user_id,
            f"✅ Текст сохранён ({len(text)} символов).\n\n"
            f"📌 ДОСТУПНЫЕ КОМАНДЫ:\n"
            f"  анализ    — получить анализ выступления\n"
            f"  улучши    — получить улучшенную версию\n"
            f"  экспорт   — сохранить анализ в PDF\n"
            f"  help      — полная справка")
        logging.info(f"Сохранён текст от пользователя {user_id} ({len(text)} символов)")
    else:
        send_message(vk, user_id, 
            "📝 Пришлите текст вашего выступления, и я помогу его проанализировать и улучшить!\n\n"
            "Доступные команды: анализ, улучши, экспорт, help")


# ========== ЗАПУСК БОТА ==========
def run_bot():
    """Запускает бота с автоматическим переподключением"""
    
    if not VK_TOKEN:
        print("❌ ОШИБКА: VK_TOKEN не найден в config.py")
        return
    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    
    queue_manager.set_vk_instance(vk, send_message)
    
    if not os.path.exists("reports"):
        os.makedirs("reports")
        print("📁 Создана папка для PDF отчётов: reports/")
    
    print("=" * 55)
    print("          Бот-тренер публичных выступлений ЗАПУЩЕН")
    print("=" * 55)
    print("\nДоступные команды:")
    print("  анализ /analyze    — анализ текста выступления")
    print("  улучши /improve    — улучшение текста выступления")
    print("  экспорт /export    — сохранить анализ в PDF")
    print("  help /справка      — показать справку")
    print("\n🎥 Также можно отправить видео с речью")
    print("=" * 55 + "\n")
    
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
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n\n👋 Бот остановлен. До свидания!")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
