from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
import tempfile
import shutil

from app.pdf_fill import fill_pdf_with_template

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html>
      <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Perfect PDF AI</title>
        <style>
          body { font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 18px; line-height: 1.5; }
          code { background: #f3f3f3; padding: 2px 6px; border-radius: 4px; }
          .card { border: 1px solid #ddd; border-radius: 10px; padding: 18px; }
        </style>
      </head>
      <body>
        <h1>Perfect PDF AI</h1>
        <div class=\"card\">
          <p>Status: <strong>running</strong></p>
          <p>Health check: <a href=\"/health\">/health</a></p>
          <p>API docs: <a href=\"/docs\">/docs</a></p>
          <p>Current endpoint: <code>POST /fill</code></p>
        </div>
      </body>
    </html>
    """


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
