import fitz  # PyMuPDF

from app.prompt_parser import normalize_key, parse_label_answer_prompt
from app.templates import build_dr_dan_template


def fit_text_to_box(page, text, rect):
    text = str(text or "").strip()
    if not text:
        return

    fontsize = 10

    while fontsize > 5:
        length = fitz.get_text_length(text, fontsize=fontsize)
        if length < rect.width:
            break
        fontsize -= 0.5

    page.insert_textbox(
        rect,
        text,
        fontsize=fontsize,
        fontname="helv",
        align=0,
    )


def _answer_for_field(answers, field_name):
    direct_key = normalize_key(field_name)
    if direct_key in answers and answers[direct_key]:
        return answers[direct_key]

    for key, value in answers.items():
        if key and value and (key in direct_key or direct_key in key):
            return value

    return ""


def fill_form_fields(doc, answers):
    filled = False

    for page in doc:
        widgets = page.widgets() or []
        for widget in widgets:
            field_name = widget.field_name or ""
            value = _answer_for_field(answers, field_name)
            if not value:
                continue

            widget.field_value = value
            widget.update()
            filled = True

    return filled


def fill_template_fields(doc, answers):
    filled = False
    template = build_dr_dan_template(answers)

    for field in template:
        page_index = field["page"]
        if page_index < 0 or page_index >= len(doc):
            continue

        value = str(field.get("value", "")).strip()
        if not value:
            continue

        page = doc[page_index]
        rect = fitz.Rect(field["rect"])
        fit_text_to_box(page, value, rect)
        filled = True

    return filled


def fill_fallback_text(doc, answers):
    if not answers or len(doc) == 0:
        return False

    page = doc[0]
    y = 50
    filled = False

    for key, value in answers.items():
        value = str(value or "").strip()
        if not value:
            continue

        label = key.replace("_", " ").title()
        rect = fitz.Rect(50, y, 550, y + 28)
        fit_text_to_box(page, f"{label}: {value}", rect)
        y += 32
        filled = True

        if y > 760:
            break

    return filled


def fill_pdf_with_template(input_pdf, output_pdf, prompt_text):
    doc = fitz.open(input_pdf)
    answers = parse_label_answer_prompt(prompt_text)

    form_filled = fill_form_fields(doc, answers)
    if not form_filled:
        template_filled = fill_template_fields(doc, answers)
        if not template_filled:
            fill_fallback_text(doc, answers)

    doc.save(output_pdf, garbage=4, deflate=True)
