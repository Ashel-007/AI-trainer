# main.py

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import random
import time
import logging
import sys
import traceback
import os
import requests

from gigachat_client import analyze_speech, command_1, format_analysis_report
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

# ========== КЛАВИАТУРА ИНТЕРФЕЙСА (UI) ==========
def get_main_keyboard():
    """Создает кнопочный интерфейс для взаимодействия с ботом"""
    keyboard = VkKeyboard(one_time=False)

    keyboard.add_button('🔍 Анализ', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('✨ Улучшить текст', color=VkKeyboardColor.POSITIVE)

    keyboard.add_line()

    keyboard.add_button('📄 Экспорт в PDF', color=VkKeyboardColor.SECONDARY)
    keyboard.add_button('❓ Ценность и Помощь', color=VkKeyboardColor.SECONDARY)

    return keyboard.get_keyboard()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def send_message(vk, user_id: int, message: str, keyboard=None):
    """Отправляет текстовое сообщение пользователю с опциональной клавиатурой"""
    try:
        payload = {
            'user_id': user_id,
            'message': message,
            'random_id': random.randint(1, 1000000)
        }
        if keyboard:
            payload['keyboard'] = keyboard

        vk.messages.send(**payload)
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")

def send_pdf_to_user(vk, user_id: int, pdf_path: str) -> bool:
    """Отправляет PDF файл пользователю в диалог ВК"""
    try:
        upload_server = vk.docs.getMessagesUploadServer(type='doc', peer_id=user_id)

        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(upload_server['upload_url'], files=files)
            file_data = response.json()

        saved_doc = vk.docs.save(file=file_data['file'], title='Анализ_выступления.pdf')

        doc = saved_doc['doc']
        doc_id = doc['id']
        owner_id = doc['owner_id']

        vk.messages.send(
            user_id=user_id,
            attachment=f'doc{owner_id}_{doc_id}',
            random_id=random.randint(1, 1000000),
            message="📄 Ваш сформированный отчёт в формате PDF:"
        )
        return True
    except Exception as e:
        logging.error(f"Ошибка отправки PDF: {e}")
        return False

def get_video_url(vk, owner_id: int, video_id: int) -> str:
    """Получает прямую ссылку на видео через VK API"""
    try:
        video_info = vk.video.get(videos=f"{owner_id}_{video_id}", extended=0)
        if video_info and 'items' in video_info and len(video_info['items']) > 0:
            files = video_info['items'][0].get('files', {})
            url = files.get('mp4_1080') or files.get('mp4_720') or files.get('mp4_480') or files.get('mp4_360')
            return url
        return None
    except Exception as e:
        logging.error(f"Ошибка получения видео: {e}")
        return None

def get_document_url(vk, owner_id: int, doc_id: int) -> str:
    """Получает ссылку на документ (аудио/видео) через VK API"""
    try:
        doc_info = vk.docs.getById(docs=f"{owner_id}_{doc_id}")
        if doc_info and len(doc_info) > 0:
            doc = doc_info[0]
            ext = doc.get('ext', '')
            url = doc.get('url', '')
            if ext in ['mp4', 'avi', 'mov', 'mkv', 'mpg', 'webm', 'mp3', 'wav', 'ogg', 'm4a']:
                return url
        return None
    except Exception as e:
        logging.error(f"Ошибка получения документа: {e}")
        return None

def extract_video_from_attachments(vk, attachments):
    """
    Извлекает медиафайл (видео, аудио, голосовое) из вложений любых типов.
    Поддерживает видео, документы и голосовые сообщения (войсы).
    """
    # --- Старый формат (словарь) ---
    if isinstance(attachments, dict):
        for key, value in attachments.items():
            if key.startswith('attach') and not key.endswith('_type'):
                attach_id = value
                type_key = key + '_type'
                attach_type = attachments.get(type_key)

                if attach_type == 'video' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        return get_video_url(vk, int(parts[0]), int(parts[1]))
                elif attach_type == 'doc' and attach_id:
                    parts = attach_id.split('_')
                    if len(parts) == 2:
                        return get_document_url(vk, int(parts[0]), int(parts[1]))
                elif attach_type == 'audio_message' and attach_id:
                    # Пропускаем, т.к. голосовые обычно приходят в новом формате
                    pass

    # --- Современный формат (список) ---
    if isinstance(attachments, list):
        for item in attachments:
            if isinstance(item, dict):
                if item.get('type') == 'video':
                    video = item.get('video', {})
                    return get_video_url(vk, video.get('owner_id'), video.get('id'))
                elif item.get('type') == 'doc':
                    doc = item.get('doc', {})
                    return doc.get('url')
                elif item.get('type') == 'audio_message':
                    audio_msg = item.get('audio_message', {})
                    return audio_msg.get('link_mp3') or audio_msg.get('link_ogg')
    return None

# ========== ОСНОВНАЯ ЛОГИКА БОТА ==========
def process_event(event, vk):
    """Обрабатывает входящее событие от пользователя VK"""
    global user_texts, user_last_analysis

    user_id = event.user_id
    original_text = event.text.strip() if event.text else ""
    text = original_text.lower()

    # ===== 1. ПРОВЕРКА ВЛОЖЕНИЙ (ВИДЕО/АУДИОРЕЧЬ) =====
    video_url = None
    if hasattr(event, 'attachments') and event.attachments:
        video_url = extract_video_from_attachments(vk, event.attachments)

    if video_url:
        logging.info(f"Обнаружено медиа для пользователя {user_id}")
        send_message(vk, user_id,
                     "🎬 Файл получен! Добавляю в очередь на извлечение звука и распознавание текста (STT)...")
        queue_manager.enqueue_video(user_id, video_url)
        return

    # ===== 2. ОБРАБОТКА КОМАНД С КЛАВИАТУРЫ И ТЕКСТА =====

    if text in ['/help', 'help', 'помощь', 'справка', 'начать', '❓ ценность и помощь']:
        help_msg = """💎 ЦЕННОСТЬ НАШЕГО ПРОЕКТА «AI-ТРЕНЕР»:
1. Экономия времени и денег на личных тренерах ораторского искусства.
2. Объективный аудит: Связка Whisper STT и Librosa выявляет точный темп речи и задержки.
3. Комплексный подход: Проверка структуры, опечаток, очистка от слов-паразитов и генерация индивидуальных советов по подаче!

📋 ИНСТРУКЦИЯ К БОТУ:
1. Просто отправьте боту текст вашего выступления или пришлите видео/аудиофайл.
2. При отправке медиа бот выполнит автоматический перевод речи в текст и сразу же проведет полный ораторский анализ!
3. Используйте кнопки управления интерфейса для быстрой навигации."""
        send_message(vk, user_id, help_msg, keyboard=get_main_keyboard())
        return

    if text in ['/export', 'экспорт', 'export', '📄 экспорт в pdf']:
        if user_id not in user_last_analysis:
            send_message(vk, user_id,
                         "❌ Нет сохранённого анализа. Сначала отправьте текст и выполните команду 'Анализ' (или отправьте видеофайл).")
            return

        send_message(vk, user_id, "📄 Создаю PDF отчёт... Подождите.")
        try:
            analysis_data = user_last_analysis[user_id]
            msg, pdf_path = generate_export_message(
                user_id,
                analysis_data['text'],
                analysis_data['analysis_str'],
                "text"
            )

            success = send_pdf_to_user(vk, user_id, pdf_path)
            if not success:
                send_message(vk, user_id, f"✅ PDF отчёт создан локально на сервере. Файл: {pdf_path}")
        except Exception as e:
            logging.error(traceback.format_exc())
            send_message(vk, user_id, f"❌ Ошибка создания PDF: {str(e)[:200]}")
        return

    if text in ['анализ', '/analyze', '🔍 анализ']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст вашего выступления!")
            return

        send_message(vk, user_id, "🔍 Анализирую выступление...")
        try:
            analysis_result = analyze_speech(user_texts[user_id])
            logging.debug(f"Результат анализа: {analysis_result}")

            report = format_analysis_report(analysis_result)
            logging.debug(f"Отчёт сформирован, длина: {len(report)}")

            send_message(vk, user_id, report, keyboard=get_main_keyboard())

            user_last_analysis[user_id] = {
                'text': user_texts[user_id],
                'analysis_str': report
            }
        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(f"Ошибка при анализе: {e}\n{error_details}")
            send_message(vk, user_id, f"❌ Ошибка анализа: {str(e)[:200]}\n\nПодробности в логах бота.")
        return

    if text in ['улучши', '/improve', '✨ улучшить текст']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст вашего выступления!")
            return

        send_message(vk, user_id, "✨ Улучшаю текст...")
        try:
            improved = command_1(user_texts[user_id])
            send_message(vk, user_id, f"🎤 УЛУЧШЕННОЕ ВЫСТУПЛЕНИЕ:\n\n{improved}", keyboard=get_main_keyboard())
        except Exception as e:
            logging.error(traceback.format_exc())
            send_message(vk, user_id, f"❌ Ошибка улучшения: {str(e)[:200]}")
        return

    # ===== 3. СОХРАНЕНИЕ ТЕКСТА ПОЛЬЗОВАТЕЛЯ ДЛЯ ДАЛЬНЕЙШЕГО АНАЛИЗА =====
    if original_text:
        user_texts[user_id] = original_text
        send_message(vk, user_id,
                     f"✅ Текст выступления успешно сохранён ({len(original_text)} символов).\n\n"
                     f"📌 Выберите нужное действие на панели кнопок ниже 👇",
                     keyboard=get_main_keyboard())

# ========== ЗАПУСК БОТА ==========
def run_bot():
    if not VK_TOKEN:
        print("❌ ОШИБКА: VK_TOKEN не найден в config.py")
        return

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    queue_manager.start_worker_thread(vk, send_message, user_texts, user_last_analysis)

    if not os.path.exists("reports"):
        os.makedirs("reports")

    print("=" * 55)
    print("          Бот-тренер публичных выступлений ЗАПУЩЕН")
    print("=" * 55)

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
            logging.error(f"Ошибка подключения к LongPoll: {e}")
            time.sleep(5)
            continue

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n👋 Бот успешно остановлен вручную.")