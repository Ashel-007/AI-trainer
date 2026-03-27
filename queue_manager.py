"""
Менеджер очереди задач для асинхронной обработки видео
"""

import threading
from queue import Queue
from video_processor import VideoProcessor
import logging
import traceback

# Очередь задач
task_queue = Queue()

# Глобальный объект для отправки сообщений
vk_instance = None
send_message_func = None

def set_vk_instance(vk, send_func):
    """Устанавливает VK объект для отправки сообщений"""
    global vk_instance, send_message_func
    vk_instance = vk
    send_message_func = send_func

def worker():
    """Воркер, который обрабатывает задачи из очереди"""
    processor = VideoProcessor()
    
    while True:
        user_id, video_url = task_queue.get()
        
        try:
            logging.info(f"Начинаю обработку видео для пользователя {user_id}")
            
            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id, "Начинаю анализ видео... Это может занять 1-2 минуты.")
            
            # Обрабатываем видео
            result = processor.process_video(video_url)
            
            # Формируем отчёт для пользователя
            report = format_video_report(result)
            
            # Отправляем результат
            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id, report)
            
            logging.info(f"Обработка видео для пользователя {user_id} завершена")
            
        except Exception as e:
            logging.error(f"Ошибка при обработке видео: {e}")
            logging.error(traceback.format_exc())
            if send_message_func and vk_instance:
                send_message_func(vk_instance, user_id, f"Ошибка при обработке видео: {str(e)}")
        
        finally:
            task_queue.task_done()

def format_video_report(result: dict) -> str:
    """Форматирует результат анализа видео для отправки пользователю"""
    transcript = result['transcript']
    analysis = result['analysis']
    
    # Ограничиваем текст, если он слишком длинный
    transcript_preview = transcript[:500] + "..." if len(transcript) > 500 else transcript
    
    report = f"""
Анализ вашего выступления:

Транскрибация (первые 500 символов):
{transcript_preview}

Статистика выступления:
- Средний темп речи: {analysis['average_speech_rate']:.0f} слов в минуту
- Количество пауз: {analysis['total_pauses']}
- Длительность выступления: {result['segments'][-1]['end']:.0f} секунд

Рекомендации:
"""
    
    # Добавляем рекомендации на основе анализа
    if analysis['average_speech_rate'] > 180:
        report += "- Ваш темп речи слишком быстрый. Постарайтесь говорить медленнее и делайте паузы между мыслями.\n"
    elif analysis['average_speech_rate'] < 100:
        report += "- Ваш темп речи слишком медленный. Попробуйте говорить чуть быстрее, чтобы удерживать внимание аудитории.\n"
    else:
        report += "- Темп речи в норме (120-180 слов в минуту). Отлично!\n"
    
    if analysis['total_pauses'] < 5 and result['segments'][-1]['end'] > 60:
        report += "- Вы делаете мало пауз. Помните, что паузы помогают аудитории осмыслить информацию.\n"
    elif analysis['total_pauses'] > 20:
        report += "- Вы делаете много пауз. Попробуйте сократить их количество для более плавной речи.\n"
    
    report += """
Для детального анализа текста пришлите мне текст выступления, и я дам разбор по структуре и словам-паразитам.

AI-тренер публичных выступлений
"""
    
    return report

def enqueue_video(user_id: int, video_url: str):
    """Добавляет видео в очередь на обработку"""
    task_queue.put((user_id, video_url))
    logging.info(f"Видео для пользователя {user_id} добавлено в очередь")

# Запускаем воркер в фоновом потоке
worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()
print("Менеджер очереди запущен")
