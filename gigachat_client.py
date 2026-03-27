from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from prompts import SYSTEM_PROMPT
from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE

def analyze_speech(speech_text: str) -> str:
    """
    Отправляет текст выступления в GigaChat и возвращает анализ
    """
    # Формируем сообщения для GigaChat
    messages = Chat(
        messages=[
            Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
            Messages(role=MessagesRole.USER, content=f"Вот моё выступление:\n\n{speech_text}")
        ]
    )
    
    # Подключаемся к GigaChat и отправляем запрос
    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False
    ) as giga:
        response = giga.chat(messages)
        return response.choices[0].message.content
