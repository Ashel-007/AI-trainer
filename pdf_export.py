"""
Модуль для экспорта анализа выступления в PDF
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os

# Создаём папку для отчётов
REPORTS_DIR = "reports"
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)
    print(f"✅ Создана папка для отчётов: {REPORTS_DIR}")

# Пытаемся найти доступный шрифт с поддержкой кириллицы
FONT_NAME = None

# Список возможных шрифтов (в порядке приоритета)
possible_fonts = [
    ('Arial', 'arial.ttf'),
    ('LiberationSans', 'LiberationSans-Regular.ttf'),
    ('DejaVuSans', 'DejaVuSans.ttf'),
]

# Проверяем текущую папку проекта
for font_name, font_file in possible_fonts:
    if os.path.exists(font_file):
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_file))
            FONT_NAME = font_name
            print(f"✅ Используется шрифт: {font_name} (из папки проекта)")
            break
        except:
            pass

# Если не нашли в папке проекта, пробуем системный путь Windows
if FONT_NAME is None and os.path.exists("C:/Windows/Fonts/arial.ttf"):
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
        FONT_NAME = 'Arial'
        print("✅ Используется системный шрифт: Arial (Windows)")
    except:
        pass

# Если ничего не подошло, используем стандартный шрифт (кириллица не будет работать)
if FONT_NAME is None:
    print("⚠️ Шрифт для кириллицы не найден! Русские буквы могут не отображаться.")
    FONT_NAME = 'Helvetica'


def create_pdf_analysis(user_id: int, original_text: str, analysis: str, speech_type: str = "text") -> str:
    """Создаёт PDF файл с анализом выступления"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{REPORTS_DIR}/user_{user_id}_{timestamp}.pdf"
    
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        topMargin=20*mm,
        bottomMargin=20*mm,
        leftMargin=20*mm,
        rightMargin=20*mm,
        title="Speech Analysis"
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=18,
        textColor=colors.HexColor('#1a5276'),
        spaceAfter=20,
        alignment=1,
        encoding='utf-8'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=14,
        textColor=colors.HexColor('#2980b9'),
        spaceAfter=10,
        spaceBefore=10,
        bold=1,
        encoding='utf-8'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=10,
        leading=14,
        spaceAfter=6,
        encoding='utf-8'
    )
    
    speech_style = ParagraphStyle(
        'SpeechStyle',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=10,
        leading=14,
        backColor=colors.HexColor('#f0f3f5'),
        leftIndent=10,
        rightIndent=10,
        spaceAfter=10,
        borderPadding=5,
        encoding='utf-8'
    )
    
    content = []
    
    # 1. Заголовок
    content.append(Paragraph("Анализ выступления", title_style))
    content.append(Spacer(1, 5))
    
    # 2. Информация
    info_text = f"""
    <b>Тип:</b> {speech_type.upper()}<br/>
    <b>Дата:</b> {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}<br/>
    <b>Пользователь:</b> {user_id}<br/>
    <b>Длина текста:</b> {len(original_text)} символов
    """
    content.append(Paragraph(info_text, normal_style))
    content.append(Spacer(1, 10))
    
    # 3. Исходный текст
    content.append(Paragraph("Исходный текст:", heading_style))
    content.append(Spacer(1, 3))
    safe_text = original_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    content.append(Paragraph(safe_text.replace('\n', '<br/>'), speech_style))
    content.append(Spacer(1, 10))
    
    # 4. Анализ
    content.append(Paragraph("Анализ и рекомендации:", heading_style))
    content.append(Spacer(1, 3))
    
    safe_analysis = analysis.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    lines = safe_analysis.split('\n')
    for line in lines:
        if line.strip():
            if line.startswith(('1.', '2.', '3.', '4.', 'Структура', 'Слова-паразиты', 'Сильные стороны', 'Советы')):
                content.append(Paragraph(f"<b>{line}</b>", normal_style))
            else:
                content.append(Paragraph(line, normal_style))
            content.append(Spacer(1, 2))
    
    content.append(Spacer(1, 15))
    
    # 5. Подвал
    footer_text = """
    <i>Отчёт создан автоматически с помощью AI-тренера публичных выступлений.</i>
    """
    content.append(Paragraph(footer_text, normal_style))
    
    doc.build(content)
    
    return filename


def generate_export_message(user_id: int, original_text: str, analysis: str, speech_type: str = "text") -> tuple:
    """Генерирует PDF и возвращает сообщение и путь к файлу"""
    try:
        pdf_path = create_pdf_analysis(user_id, original_text, analysis, speech_type)
        message = f"✅ PDF отчёт успешно создан!"
        return message, pdf_path
    except Exception as e:
        error_msg = f"❌ Ошибка при создании PDF: {str(e)}"
        print(error_msg)
        return error_msg, None
