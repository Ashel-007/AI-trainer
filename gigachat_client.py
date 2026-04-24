from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from prompts import SYSTEM_PROMPT
from prompt_for_command1 import prompt_com_1
from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE

def analyze_speech(speech_text: str) -> str:
    """Анализ выступления"""
    try:
        with GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            scope=GIGACHAT_SCOPE,
            verify_ssl_certs=False
        ) as giga:
            messages = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                    Messages(role=MessagesRole.USER, content=f"Вот моё выступление:\n\n{speech_text}")
                ]
            )
            response = giga.chat(messages)
            return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка GigaChat (анализ): {e}")
        return "Извините, произошла ошибка при анализе. Попробуйте позже."


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
        print(f"Ошибка GigaChat (улучшение): {e}")
        return "Извините, произошла ошибка при улучшении. Попробуйте позже."
