#!/usr/bin/env python3
"""
Perfect PDF AI — simple deployable document reader and answer submission app.

Users can:
1. Upload a document.
2. Read extracted text in the browser.
3. Upload a separate answers file.

Supported document text extraction:
- .txt / .md: native text read
- .pdf: PyMuPDF when installed; pdftotext fallback when available
- .docx: docx2txt command fallback when available
"""

from __future__ import annotations

import html
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DOCUMENT_DIR = UPLOAD_DIR / "documents"
ANSWER_DIR = UPLOAD_DIR / "answers"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(title="Perfect PDF AI", version="1.0.0")


def ensure_dirs() -> None:
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def safe_filename(original: str) -> str:
    name = Path(original or "upload.bin").name.strip() or "upload.bin"
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip()
    return cleaned or "upload.bin"


def save_upload(upload: UploadFile, destination_dir: Path) -> Path:
    ensure_dirs()
    filename = safe_filename(upload.filename or "upload.bin")
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    destination = destination_dir / unique_name

    total = 0
    with destination.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File is too large. Maximum upload size is 25 MB.")
            out.write(chunk)

    return destination


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz

        pieces: list[str] = []
        with fitz.open(path) as doc:
            for page_number, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                pieces.append(f"\n--- Page {page_number} ---\n{text}")
        result = "\n".join(pieces).strip()
        if result:
            return result
    except Exception:
        pass

    if shutil.which("pdftotext"):
        completed = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()

    return "PDF uploaded successfully, but text extraction was not available for this file."


def extract_docx_text(path: Path) -> str:
    if shutil.which("docx2txt"):
        completed = subprocess.run(
            ["docx2txt", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    return "DOCX uploaded successfully, but text extraction was not available on this server."


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    return f"Unsupported preview type: {suffix or 'unknown'}. The file was still uploaded."


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #0f172a; color: #e5e7eb; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 56px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 24px; box-shadow: 0 12px 36px rgba(0,0,0,.25); }}
    h1 {{ margin: 0 0 10px; font-size: clamp(30px, 5vw, 54px); letter-spacing: -0.04em; }}
    h2 {{ margin-top: 26px; }}
    p {{ color: #cbd5e1; line-height: 1.55; }}
    form {{ display: grid; gap: 14px; margin-top: 18px; }}
    input[type=file] {{ padding: 18px; border: 1px dashed #64748b; border-radius: 14px; background: #020617; color: #e5e7eb; }}
    button, .button {{ display: inline-block; width: fit-content; border: 0; border-radius: 12px; padding: 13px 18px; font-weight: 700; background: #38bdf8; color: #020617; cursor: pointer; text-decoration: none; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; max-height: 62vh; overflow: auto; background: #020617; border: 1px solid #334155; padding: 18px; border-radius: 14px; line-height: 1.45; }}
    .muted {{ color: #94a3b8; font-size: 14px; }}
    .success {{ border-color: #22c55e; }}
  </style>
</head>
<body>
  <main class="wrap">{body}</main>
</body>
</html>"""


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "perfect-pdf-ai"})


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    body = """
    <section class="card">
      <h1>Perfect PDF AI</h1>
      <p>Upload a document, read the extracted text, then upload the user answers in the next box.</p>
      <form method="post" action="/upload" enctype="multipart/form-data">
        <input type="file" name="file" accept=".pdf,.txt,.md,.csv,.docx" required>
        <button type="submit">Upload and Read</button>
      </form>
      <p class="muted">Supported previews: PDF, TXT, MD, CSV, DOCX. Max file size: 25 MB.</p>
    </section>
    """
    return HTMLResponse(page_shell("Perfect PDF AI", body))


@app.post("/upload", response_class=HTMLResponse)
def upload_document(file: UploadFile = File(...)) -> HTMLResponse:
    path = save_upload(file, DOCUMENT_DIR)
    text = extract_text(path)
    escaped_name = html.escape(path.name.split("_", 1)[-1])
    escaped_text = html.escape(text or "No readable text was found.")

    body = f"""
    <section class="card">
      <h1>Document Uploaded</h1>
      <p><strong>File:</strong> {escaped_name}</p>
      <h2>Readable Text</h2>
      <pre>{escaped_text}</pre>
      <h2>Upload Answers</h2>
      <p>After reading the document, upload the answers file here.</p>
      <form method="post" action="/submit-answers" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <button type="submit">Upload Answers</button>
      </form>
      <p><a class="button" href="/">Start Over</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Document Uploaded", body))


@app.post("/submit-answers", response_class=HTMLResponse)
def submit_answers(file: UploadFile = File(...)) -> HTMLResponse:
    path = save_upload(file, ANSWER_DIR)
    escaped_name = html.escape(path.name.split("_", 1)[-1])
    body = f"""
    <section class="card success">
      <h1>Answers Uploaded</h1>
      <p>Your answers file <strong>{escaped_name}</strong> was uploaded successfully.</p>
      <p><a class="button" href="/">Upload Another Document</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Answers Uploaded", body))


@app.get("/submit_answers")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url="/")
