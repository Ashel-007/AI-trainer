"""
Модуль для обработки видео:
- скачивание видео
- извлечение аудио
- транскрибация (Whisper)
- аудиоанализ (темп речи, паузы)
"""

import os
import requests
import whisper
import librosa
import numpy as np
import tempfile
import subprocess
import logging

class VideoProcessor:
    def __init__(self):
        """Инициализация процессора видео"""
        print("Загрузка модели Whisper... (только при первом запуске)")
        self.whisper_model = whisper.load_model("base")
        print("Модель Whisper загружена")
    
    def download_video(self, video_url: str) -> str:
        """
        Скачивает видео по ссылке
        Возвращает путь к сохранённому файлу
        """
        logging.info(f"Скачиваю видео: {video_url[:50]}...")
        
        # Создаём временный файл
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_path = temp_file.name
        temp_file.close()
        
        # Скачиваем видео
        response = requests.get(video_url, stream=True)
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logging.info(f"Видео сохранено: {temp_path}")
        return temp_path
    
    def extract_audio(self, video_path: str) -> str:
        """
        Извлекает аудиодорожку из видео
        Возвращает путь к аудиофайлу (wav)
        """
        logging.info("Извлекаю аудио из видео...")
        
        audio_path = video_path.replace('.mp4', '.wav')
        
        # Используем ffmpeg для извлечения аудио
        cmd = [
            'ffmpeg', '-i', video_path,
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            '-y',
            audio_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        logging.info(f"Аудио сохранено: {audio_path}")
        return audio_path
    
    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Транскрибирует аудио в текст с таймкодами
        Возвращает: {
            'text': полный текст,
            'segments': [{'start': 0.0, 'end': 2.5, 'text': '...'}]
        }
        """
        logging.info("Транскрибирую аудио...")
        
        result = self.whisper_model.transcribe(
            audio_path,
            language='ru',
            task='transcribe'
        )
        
        logging.info(f"Транскрибация завершена. Распознано {len(result['segments'])} сегментов")
        return result
    
    def analyze_audio(self, audio_path: str, whisper_segments: list) -> dict:
        """
        Анализирует аудио: темп речи, паузы
        Возвращает:
        {
            'average_speech_rate': 150,
            'speech_rate_segments': [{'start': 0, 'end': 10, 'rate': 140}],
            'pauses': [{'start': 1.2, 'end': 1.8, 'duration': 0.6}],
            'total_pauses': 15
        }
        """
        logging.info("Анализирую аудио...")
        
        # Загружаем аудио для анализа
        y, sr = librosa.load(audio_path, sr=16000)
        
        # 1. Определяем паузы (участки тишины)
        frame_length = int(sr * 0.025)
        hop_length = int(sr * 0.010)
        
        energy = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        threshold = np.mean(energy) * 0.3
        
        pauses = []
        is_pause = False
        pause_start = 0
        
        for i, e in enumerate(energy):
            time_val = i * hop_length / sr
            
            if e < threshold and not is_pause:
                is_pause = True
                pause_start = time_val
            elif e >= threshold and is_pause:
                is_pause = False
                pause_duration = time_val - pause_start
                if pause_duration > 0.3:
                    pauses.append({
                        'start': round(pause_start, 2),
                        'end': round(time_val, 2),
                        'duration': round(pause_duration, 2)
                    })
        
        # 2. Рассчитываем темп речи по сегментам из Whisper
        speech_rate_segments = []
        total_words = 0
        total_duration = 0
        
        for segment in whisper_segments:
            text = segment['text']
            duration = segment['end'] - segment['start']
            
            words = len(text.split())
            if duration > 0:
                rate = (words / duration) * 60
            else:
                rate = 0
            
            speech_rate_segments.append({
                'start': round(segment['start'], 2),
                'end': round(segment['end'], 2),
                'rate': round(rate, 2)
            })
            
            total_words += words
            total_duration += duration
        
        average_rate = (total_words / total_duration) * 60 if total_duration > 0 else 0
        
        logging.info(f"Анализ завершён. Средний темп: {average_rate:.0f} слов/мин, пауз: {len(pauses)}")
        
        return {
            'average_speech_rate': round(average_rate, 2),
            'speech_rate_segments': speech_rate_segments,
            'pauses': pauses,
            'total_pauses': len(pauses)
        }
    
    def process_video(self, video_url: str) -> dict:
        """
        Полный цикл обработки видео
        Возвращает:
        {
            'transcript': 'полный текст',
            'segments': [{'start': 0, 'end': 2.5, 'text': '...', 'rate': 140}],
            'analysis': {
                'average_speech_rate': 150,
                'total_pauses': 15,
                'pauses': [...]
            }
        }
        """
        logging.info("=" * 50)
        logging.info("Начинаю обработку видео")
        logging.info("=" * 50)
        
        # 1. Скачиваем видео
        video_path = self.download_video(video_url)
        
        # 2. Извлекаем аудио
        audio_path = self.extract_audio(video_path)
        
        # 3. Транскрибируем
        transcription = self.transcribe_audio(audio_path)
        
        # 4. Анализируем аудио
        audio_analysis = self.analyze_audio(audio_path, transcription['segments'])
        
        # 5. Объединяем результаты
        for i, segment in enumerate(transcription['segments']):
            if i < len(audio_analysis['speech_rate_segments']):
                segment['rate'] = audio_analysis['speech_rate_segments'][i]['rate']
        
        result = {
            'transcript': transcription['text'],
            'segments': transcription['segments'],
            'analysis': audio_analysis
        }
        
        # 6. Очищаем временные файлы
        try:
            os.remove(video_path)
            os.remove(audio_path)
            logging.info("Временные файлы удалены")
        except:
            pass
        
        logging.info("=" * 50)
        logging.info("Обработка видео завершена")
        logging.info("=" * 50)
        
        return result


# Для тестирования модуля
if __name__ == "__main__":
    processor = VideoProcessor()
    print("Модуль video_processor загружен. Используйте в основном боте.")
