# main.py (бот-сообщество)

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
from config import VK_TOKEN, GROUP_ID          # ! добавьте GROUP_ID в config.py
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
    """
    Извлекает ссылку на видео/аудио/голосовое из вложений.
    attachments – список из event.obj['attachments'].
    """
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


# ========== ОСНОВНАЯ ЛОГИКА ==========
def process_event(event, vk):
    global user_texts, user_last_analysis

    # В bot_longpoll данные лежат в event.obj
    msg = event.obj['message']
    user_id = msg['from_id']
    original_text = msg.get('text', '').strip()
    text = original_text.lower()
    attachments = msg.get('attachments', [])

    # 1. Проверка вложений (видео/аудио/голосовое)
    media_url = extract_video_from_attachments(vk, attachments)
    if media_url:
        logging.info(f"Обнаружено медиа от пользователя {user_id}")
        send_message(vk, user_id,
                     "🎬 Файл получен! Добавляю в очередь...")
        queue_manager.enqueue_video(user_id, media_url)
        return

    # 2. Команды
    if text in ['/help', 'help', 'помощь', 'справка', 'начать', '❓ ценность и помощь']:
        help_msg = """💎 ЦЕННОСТЬ НАШЕГО ПРОЕКТА «AI-ТРЕНЕР»:
1. Экономия времени и денег на личных тренерах.
2. Объективный аудит темпа речи, пауз.
3. Комплексный анализ и советы.

📋 ИНСТРУКЦИЯ:
1. Отправьте текст, видео, аудио или голосовое сообщение.
2. Бот автоматически распознает речь и выдаст анализ.
3. Используйте кнопки для навигации."""
        send_message(vk, user_id, help_msg, keyboard=get_main_keyboard())
        return

    if text in ['/export', 'экспорт', 'export', '📄 экспорт в pdf']:
        if user_id not in user_last_analysis:
            send_message(vk, user_id, "❌ Сначала выполните анализ.")
            return
        send_message(vk, user_id, "📄 Создаю PDF...")
        try:
            data = user_last_analysis[user_id]
            msg_text, pdf_path = generate_export_message(user_id, data['text'], data['analysis_str'], "text")
            # ... отправка pdf (функция send_pdf_to_user) ...
            send_message(vk, user_id, "PDF готов (заглушка)")
        except Exception as e:
            send_message(vk, user_id, f"❌ Ошибка PDF: {e}")
        return

    if text in ['анализ', '/analyze', '🔍 анализ']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст.")
            return
        send_message(vk, user_id, "🔍 Анализирую...")
        try:
            analysis = analyze_speech(user_texts[user_id])
            report = format_analysis_report(analysis)
            send_message(vk, user_id, report, keyboard=get_main_keyboard())
            user_last_analysis[user_id] = {
                'text': user_texts[user_id],
                'analysis_str': report
            }
        except Exception as e:
            logging.error(traceback.format_exc())
            send_message(vk, user_id, f"❌ Ошибка анализа: {e}")
        return

    if text in ['улучши', '/improve', '✨ улучшить текст']:
        if user_id not in user_texts:
            send_message(vk, user_id, "❌ Сначала пришлите текст.")
            return
        send_message(vk, user_id, "✨ Улучшаю...")
        try:
            improved = command_1(user_texts[user_id])
            send_message(vk, user_id, f"🎤 Улучшенный текст:\n\n{improved}", keyboard=get_main_keyboard())
        except Exception as e:
            send_message(vk, user_id, f"❌ Ошибка улучшения: {e}")
        return

    # 3. Сохранение текста
    if original_text:
        user_texts[user_id] = original_text
        send_message(vk, user_id,
                     f"✅ Текст сохранён ({len(original_text)} символов).\nВыберите действие:",
                     keyboard=get_main_keyboard())


# ========== ЗАПУСК ==========
def run_bot():
    if not VK_TOKEN:
        print("❌ Нет VK_TOKEN")
        return
    if not GROUP_ID:
        print("❌ Нет GROUP_ID в config.py")
        return

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    queue_manager.start_worker_thread(vk, send_message, user_texts, user_last_analysis)

    longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)

    print("=" * 55)
    print("          Бот-тренер публичных выступлений ЗАПУЩЕН (сообщество)")
    print("=" * 55)

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            try:
                process_event(event, vk)
            except Exception as e:
                logging.error(f"Ошибка обработки: {e}")
                logging.error(traceback.format_exc())


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")