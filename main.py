# main.py (бот-сообщество, полная версия)

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import random
import time
import logging
import sys
import traceback
import os
import requests

from gigachat_client import analyze_speech, command_1, format_analysis_report
from config import VK_TOKEN, GROUP_ID          # GROUP_ID должен быть в config.py
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

# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('🔍 Анализ', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('✨ Улучшить текст', color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button('📄 Экспорт в PDF', color=VkKeyboardColor.SECONDARY)
    keyboard.add_button('❓ Ценность и Помощь', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

# ========== ОТПРАВКА СООБЩЕНИЙ ==========
def send_message(vk, user_id: int, message: str, keyboard=None):
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

# ========== ОТПРАВКА PDF ==========
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

# ========== ИЗВЛЕЧЕНИЕ МЕДИА ==========
def get_video_url(vk, owner_id: int, video_id: int) -> str:
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

def extract_video_from_attachments(vk, attachments: list) -> str | None:
    """Извлекает ссылку на медиа из вложений. Поддерживает video, doc, audio_message."""
    if not attachments:
        return None
    for item in attachments:
        if not isinstance(item, dict):
            continue
        att_type = item.get('type')
        if att_type == 'video':
            video = item.get('video', {})
            owner_id = video.get('owner_id')
            video_id = video.get('id')
            if owner_id and video_id:
                return get_video_url(vk, owner_id, video_id)
        elif att_type == 'doc':
            doc = item.get('doc', {})
            url = doc.get('url')
            ext = doc.get('ext', '')
            if url and ext in ['mp4', 'avi', 'mov', 'mkv', 'mpg', 'webm', 'mp3', 'wav', 'ogg', 'm4a']:
                return url
        elif att_type == 'audio_message':
            audio = item.get('audio_message', {})
            return audio.get('link_mp3') or audio.get('link_ogg')
    return None

# ========== ОБРАБОТКА КОМАНД ==========
def process_event(event, vk):
    global user_texts, user_last_analysis

    msg = event.obj['message']
    user_id = msg['from_id']
    original_text = msg.get('text', '').strip()
    text = original_text.lower()
    attachments = msg.get('attachments', [])

    # 1. Вложения
    media_url = extract_video_from_attachments(vk, attachments)
    if media_url:
        logging.info(f"Обнаружено медиа от пользователя {user_id}")
        send_message(vk, user_id, "🎬 Файл получен! Добавляю в очередь на извлечение звука и распознавание текста (STT)...")
        queue_manager.enqueue_video(user_id, media_url)
        return

    # 2. Команды
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
            send_message(vk, user_id, "❌ Нет сохранённого анализа. Сначала отправьте текст и выполните команду 'Анализ' (или отправьте видеофайл).")
            return
        send_message(vk, user_id, "📄 Создаю PDF отчёт... Подождите.")
        try:
            data = user_last_analysis[user_id]
            msg, pdf_path = generate_export_message(
                user_id,
                data['text'],
                data['analysis_str'],
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
            report = format_analysis_report(analysis_result)
            send_message(vk, user_id, report, keyboard=get_main_keyboard())
            user_last_analysis[user_id] = {
                'text': user_texts[user_id],
                'analysis_str': report
            }
        except Exception as e:
            logging.error(traceback.format_exc())
            send_message(vk, user_id, f"❌ Ошибка анализа: {str(e)[:200]}")
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

    # 3. Сохранение текста
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
    if not GROUP_ID:
        print("❌ ОШИБКА: GROUP_ID не найден в config.py")
        return

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    queue_manager.start_worker_thread(vk, send_message, user_texts, user_last_analysis)

    if not os.path.exists("reports"):
        os.makedirs("reports")

    print("=" * 55)
    print("          Бот-тренер публичных выступлений ЗАПУЩЕН")
    print("=" * 55)

    longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            try:
                process_event(event, vk)
            except Exception as e:
                logging.error(f"Ошибка обработки события: {e}")
                logging.error(traceback.format_exc())

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n👋 Бот успешно остановлен вручную.")