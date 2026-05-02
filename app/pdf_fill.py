import fitz  # PyMuPDF

from app.prompt_parser import parse_label_answer_prompt, get_answer


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

    # BASIC TEMPLATE (expand next)
    template = [
        {
            "page": 0,
            "rect": [100, 100, 300, 120],
            "value": get_answer(answers, "name")
        },
        {
            "page": 0,
            "rect": [100, 140, 300, 160],
            "value": get_answer(answers, "date of birth", "dob")
        },
    ]

    for field in template:
        page = doc[field["page"]]
        rect = fitz.Rect(field["rect"])
        fit_text_to_box(page, field["value"], rect)

    doc.save(output_pdf)
