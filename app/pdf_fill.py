import fitz  # PyMuPDF


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

    # TEMP TEMPLATE (we replace this next step)
    template = [
        {
            "page": 0,
            "text": "Laurie A. Milward",
            "rect": [100, 100, 300, 120]
        }
    ]

    for field in template:
        page = doc[field["page"]]
        rect = fitz.Rect(field["rect"])
        fit_text_to_box(page, field["text"], rect)

    doc.save(output_pdf)
