# queue_manager.py

import threading
from queue import Queue
from video_processor import VideoProcessor
import logging
import traceback
from gigachat_client import analyze_speech, format_analysis_report

# Очередь задач
task_queue = Queue()

# Глобальные объекты
vk_instance = None
send_message_func = None
user_texts_ref = None
user_last_analysis_ref = None

def set_vk_instance(vk, send_func, user_texts_dict=None, user_analysis_dict=None):
    """Устанавливает VK объект и внешние словари для синхронизации сессий"""
    global vk_instance, send_message_func, user_texts_ref, user_last_analysis_ref
    vk_instance = vk
    send_message_func = send_func
    user_texts_ref = user_texts_dict
    user_last_analysis_ref = user_analysis_dict

def format_video_report(result: dict) -> str:
    """Форматирует результат анализа видео для отправки пользователю"""
    analysis = result['analysis']

    report = f"""🎙 Результаты акустического анализа:

Статистика аудиодорожки:
- Средний темп речи: {analysis['average_speech_rate']:.0f} слов в минуту
- Количество пауз/запинок: {analysis['total_pauses']}
- Длительность выступления: {result['segments'][-1]['end']:.0f} секунд

Рекомендации по подаче:
"""

    if analysis['average_speech_rate'] > 180:
        report += "- Ваш темп речи слишком быстрый. Постарайтесь говорить медленнее и делайте паузы между мыслями.\n"
    elif analysis['average_speech_rate'] < 100:
        report += "- Ваш темп речи слишком медленный. Попробуйте говорить чуть быстрее, чтобы удерживать внимание аудитории.\n"
    else:
        report += "- Темп речи в норме (120-180 слов в минуту). Отлично!\n"

    return report

def enqueue_video(user_id: int, video_url: str):
    """Добавляет видео/аудио в очередь на обработку"""
    task_queue.put((user_id, video_url))
    logging.info(f"Медиа для пользователя {user_id} добавлено в очередь")

def start_worker_thread(vk, send_func, user_texts_dict, user_analysis_dict):
    """Инициализирует фоновый поток обработки очереди"""
    set_vk_instance(vk, send_func, user_texts_dict, user_analysis_dict)
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    print("Менеджер очереди успешно запущен")

def worker():
    """Воркер, который обрабатывает задачи из очереди"""
    processor = VideoProcessor()

    while True:
        user_id, video_url = task_queue.get()

        try:
            logging.info(f"Начинаю обработку медиа для пользователя {user_id}")

            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id,
                                  "🎬 Начинаю извлечение звука и Speech-to-Text транскрибацию... Это займет 1-2 минуты.")

            # 1. Извлекаем аудио и делаем STT (Whisper)
            result = processor.process_video(video_url)

            # 2. Получаем отчет по темпу и паузам (Librosa)
            audio_report = format_video_report(result)

            # 3. Полная автоматизация STT -> Передача распознанного текста в LLM
            speech_text = result.get('transcript', '').strip()

            if speech_text:
                if send_message_func and vk_instance:
                    send_message_func(vk_instance, user_id,
                                      "📝 Речь успешно распознана! Передаю текст искусственному интеллекту для анализа структуры и ораторских советов...")

                if user_texts_ref is not None:
                    user_texts_ref[user_id] = speech_text

                # Запускаем анализ текста через GigaChat
                analysis_result = analyze_speech(speech_text)
                text_report = format_analysis_report(analysis_result)

                if user_last_analysis_ref is not None:
                    user_last_analysis_ref[user_id] = {
                        'text': speech_text,
                        'analysis_str': text_report
                    }

                # Формируем объединенный отчет
                final_report = (
                    f"{audio_report}\n"
                    f"_____________________\n\n"
                    f"📖 РАСПОЗНАННЫЙ ТЕКСТ ВЫСТУПЛЕНИЯ:\n«{speech_text}»\n\n"
                    f"{text_report}\n\n"
                    f"📄 Теперь вы можете нажать кнопку «Экспорт в PDF» для сохранения отчёта."
                )
            else:
                final_report = f"{audio_report}\n\n⚠️ Бот не смог распознать устную речь в данном файле для проведения смыслового анализа."

            # Отправляем итоговый отчёт
            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id, final_report)

            logging.info(f"Обработка видео для пользователя {user_id} завершена")

        except Exception as e:
            logging.error(f"Ошибка при обработке медиа: {e}")
            logging.error(traceback.format_exc())
            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id, f"Ошибка при обработке медиафайла: {str(e)}")

        finally:
            task_queue.task_done()