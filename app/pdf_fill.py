import fitz  # PyMuPDF

from app.prompt_parser import parse_label_answer_prompt
from app.templates import build_dr_dan_template


def fit_text_to_box(page, text, rect):
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
        align=0
    )


def fill_pdf_with_template(input_pdf, output_pdf, prompt_text):
    doc = fitz.open(input_pdf)

    answers = parse_label_answer_prompt(prompt_text)
    template = build_dr_dan_template(answers)

    for field in template:
        page_index = field["page"]
        if page_index < 0 or page_index >= len(doc):
            continue

        page = doc[page_index]
        rect = fitz.Rect(field["rect"])
        value = field.get("value", "")
        fit_text_to_box(page, value, rect)

    doc.save(output_pdf, garbage=4, deflate=True)
