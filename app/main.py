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
          .card { border: 1px solid #ddd; border-radius: 10px; padding: 18px; margin-top: 16px; }
          .step { border: 2px solid #111; border-radius: 12px; padding: 16px; margin-top: 16px; }
          .step h3 { margin-top: 0; }
          textarea { width: 100%; min-height: 220px; }
          input, textarea, button { font: inherit; margin-top: 8px; }
          button { padding: 12px 18px; cursor: pointer; font-weight: bold; }
          label { display: block; margin-top: 14px; font-weight: bold; }
          .hint { color: #555; font-size: 0.95rem; }
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
        <div class=\"card\">
          <h2>Fill a PDF</h2>
          <form action=\"/fill\" method=\"post\" enctype=\"multipart/form-data\">
            <div class=\"step\">
              <h3>1. PDF that needs to be filled</h3>
              <label>Upload form PDF</label>
              <input type=\"file\" name=\"pdf\" accept=\"application/pdf\" required />
              <p class=\"hint\">This is the PDF the app will preserve and type answers onto.</p>
            </div>

            <div class=\"step\">
              <h3>2. Answers / source prompt</h3>
              <label>Upload answers PDF or text file</label>
              <input type=\"file\" name=\"prompt_file\" accept=\"application/pdf,text/plain,.txt\" />

              <label>Or paste answers here</label>
              <textarea name=\"prompt\"></textarea>
            </div>

            <br />
            <button type=\"submit\">Fill PDF</button>
          </form>
        </div>
      </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok"}


def extract_prompt_file_text(prompt_file: UploadFile | None) -> str:
    if prompt_file is None:
        return ""

    raw = prompt_file.file.read()
    filename = (prompt_file.filename or "").lower()

    if filename.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)

    return raw.decode("utf-8", errors="ignore")


@app.post("/fill")
async def fill_pdf(
    pdf: UploadFile = File(...),
    prompt: str = Form(""),
    prompt_file: UploadFile | None = File(None),
):
    prompt_file_text = extract_prompt_file_text(prompt_file)
    combined_prompt = "\n\n".join(part for part in [prompt, prompt_file_text] if part.strip())

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        shutil.copyfileobj(pdf.file, temp_pdf)
        input_path = temp_pdf.name

    output_path = input_path.replace(".pdf", "_filled.pdf")

    fill_pdf_with_template(input_path, output_path, combined_prompt)

    return FileResponse(output_path, filename="filled.pdf")
