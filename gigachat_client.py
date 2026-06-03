# gigachat_client.py

import json
import logging
import re

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from prompt_for_command_analyze import prompt_for_analyze
from prompt_for_command1 import prompt_com_1
from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _extract_json(text: str) -> str | None:
    """
    Извлекает JSON-объект из ответа модели, убирая markdown-разметку
    и исправляя удвоенные скобки, если модель повторяет шаблон промпта.
    """
    text = re.sub(r'```(?:json)?\s*', '', text, flags=re.IGNORECASE).strip()
    text = text.replace('{{', '{').replace('}}', '}')

    for start_char in ('{', '['):
        idx = text.find(start_char)
        if idx == -1:
            continue
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(text, idx)
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            continue
    return None

def analyze_speech(speech_text: str) -> dict:
    """Анализ выступления — возвращает словарь с результатами"""
    try:
        with GigaChat(
                credentials=GIGACHAT_CREDENTIALS,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
        ) as giga:
            filled_prompt = prompt_for_analyze.replace("{presentation_text}", speech_text)
            messages = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=filled_prompt),
                    Messages(role=MessagesRole.USER, content="Выполни анализ текста согласно инструкции.")
                ]
            )
            response = giga.chat(messages)
            raw_content = response.choices[0].message.content

            logging.info(f"Полный ответ GigaChat: {raw_content}")
            print(f"\n=== ПОЛНЫЙ ОТВЕТ МОДЕЛИ ===\n{raw_content}\n=== КОНЕЦ ===\n")

            json_str = _extract_json(raw_content)
            if json_str is None:
                logging.error("JSON не найден в ответе модели")
                return {"error": "В ответе нет JSON"}

            result = json.loads(json_str)

            if isinstance(result, list):
                if len(result) == 1 and isinstance(result[0], dict):
                    result = result[0]
                else:
                    logging.error(f"Модель вернула список из {len(result)} элементов, ожидался объект")
                    return {"error": "Модель вернула список вместо объекта"}

            logging.info("JSON успешно распарсен")
            return result

    except json.JSONDecodeError as e:
        logging.error(f"Ошибка парсинга JSON: {e}")
        return {"error": "Не удалось распарсить ответ модели"}
    except Exception as e:
        logging.error(f"Ошибка GigaChat (анализ): {e}")
        return {"error": "Произошла ошибка при анализе"}

def format_analysis_report(analysis: dict) -> str:
    """Форматирует словарь анализа в читаемый отчёт"""
    if isinstance(analysis, list):
        if len(analysis) == 1 and isinstance(analysis[0], dict):
            analysis = analysis[0]
        else:
            return "❌ Ошибка: некорректный формат ответа от модели"

    if not isinstance(analysis, dict) or "error" in analysis:
        return f"❌ Ошибка: {analysis.get('error', 'неизвестная ошибка')}"

    report = "📊 АНАЛИЗ ВЫСТУПЛЕНИЯ\n\n"

    if analysis.get("orthographic_errors"):
        report += "❌ Орфографические ошибки:\n"
        for error in analysis["orthographic_errors"]:
            report += f"   • «{error.get('incorrect')}» → «{error.get('correct')}»\n"
        report += "\n"
    else:
        report += "✅ Орфографических ошибок не обнаружено\n\n"

    if analysis.get("filler_words"):
        report += "🗣 Слова-паразиты:\n"
        for filler in analysis["filler_words"]:
            report += f"   • «{filler.get('word')}» — {filler.get('count')} раз(а)\n"
        report += "\n"
    else:
        report += "✅ Слов-паразитов не обнаружено\n\n"

    if analysis.get("stylistic_issues"):
        report += "✍️ Стилистические проблемы:\n"
        for issue in analysis["stylistic_issues"]:
            report += f"   • {issue.get('type')}: {issue.get('suggestion')}\n"
        report += "\n"
    else:
        report += "✅ Стилистических проблем не обнаружено\n\n"

    if analysis.get("structural_feedback"):
        report += "🏗 Структурные замечания:\n"
        for feedback in analysis["structural_feedback"]:
            report += f"   • {feedback}\n"
        report += "\n"
    else:
        report += "✅ Структура хорошая\n\n"

    if analysis.get("oratory_tips"):
        report += "🎤 Советы по подаче и ораторскому мастерству:\n"
        for tip in analysis["oratory_tips"]:
            report += f"   • {tip}\n"
        report += "\n"

    report += f"📝 Итог: {analysis.get('summary', 'Нет сводки')}"
    return report

def command_1(speech_text: str) -> str:
    """Улучшение текста выступления"""
    try:
        with GigaChat(
                credentials=GIGACHAT_CREDENTIALS,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
        ) as giga:
            messages = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=prompt_com_1),
                    Messages(role=MessagesRole.USER, content=f"Улучши мой текст:\n\n{speech_text}")
                ]
            )
            response = giga.chat(messages)
            return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка GigaChat (улучшение): {e}")
        return "Извините, произошла ошибка при улучшении. Попробуйте позже."