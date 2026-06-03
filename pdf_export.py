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

REPORTS_DIR = "reports"
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)

# ---------- Поиск подходящего шрифта с кириллицей ----------
FONT_NAME = None

# 1. Проверяем DejaVuSans.ttf в папке проекта (если вы его положили)
dejavu_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
if os.path.exists(dejavu_path):
    pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_path))
    FONT_NAME = 'DejaVuSans'
    print("✅ Используется шрифт DejaVuSans (из папки проекта)")

# 2. Если нет – проверяем системный Arial (Windows)
if FONT_NAME is None:
    arial_path = "C:/Windows/Fonts/arial.ttf"
    if os.path.exists(arial_path):
        pdfmetrics.registerFont(TTFont('Arial', arial_path))
        FONT_NAME = 'Arial'
        print("✅ Используется системный шрифт Arial (Windows)")

# 3. Крайний случай – Courier (не содержит кириллицы, но хоть не упадёт)
if FONT_NAME is None:
    print("⚠️ Шрифт для кириллицы не найден! Русские буквы могут не отображаться.")
    FONT_NAME = 'Courier'


def create_pdf_analysis(user_id: int, original_text: str, analysis: str, speech_type: str = "text") -> str:
    """Создаёт PDF файл с анализом выступления"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(REPORTS_DIR, f"user_{user_id}_{timestamp}.pdf")

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
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
    footer_text = "<i>Отчёт создан автоматически с помощью AI-тренера публичных выступлений.</i>"
    content.append(Paragraph(footer_text, normal_style))

    doc.build(content)
    return filename


def generate_export_message(user_id: int, original_text: str, analysis: str, speech_type: str = "text") -> tuple:
    """Генерирует PDF и возвращает сообщение и путь к файлу"""
    try:
        pdf_path = create_pdf_analysis(user_id, original_text, analysis, speech_type)
        message = "✅ PDF отчёт успешно создан!"
        return message, pdf_path
    except Exception as e:
        error_msg = f"❌ Ошибка при создании PDF: {str(e)}"
        print(error_msg)
        return error_msg, None