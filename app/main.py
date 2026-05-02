from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import tempfile
import shutil

from app.pdf_fill import fill_pdf_with_template

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/fill")
async def fill_pdf(
    pdf: UploadFile = File(...),
    prompt: str = Form(...)
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        shutil.copyfileobj(pdf.file, temp_pdf)
        input_path = temp_pdf.name

    output_path = input_path.replace(".pdf", "_filled.pdf")

    fill_pdf_with_template(input_path, output_path, prompt)

    return FileResponse(output_path, filename="filled.pdf")
