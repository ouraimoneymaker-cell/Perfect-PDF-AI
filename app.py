#!/usr/bin/env python3
"""
Perfect PDF AI — deployable PDF/document reader, answer intake, and Stripe-ready app.

Features:
- Front end served by FastAPI
- Static CSS and JS support when present
- Upload PDF/TXT/MD/CSV/DOCX documents
- Extract readable text from PDFs with PyMuPDF
- Upload separate answer files
- JSON API endpoints for integrations
- Optional Stripe payment link / checkout redirect by environment variables
- Health endpoint for Render
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
DOCUMENT_DIR = UPLOAD_DIR / "documents"
ANSWER_DIR = UPLOAD_DIR / "answers"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

APP_NAME = os.getenv("APP_NAME", "Perfect PDF AI")
STRIPE_PAYMENT_LINK = os.getenv("STRIPE_PAYMENT_LINK", "").strip()
STRIPE_REQUIRE_PAYMENT = os.getenv("STRIPE_REQUIRE_PAYMENT", "false").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title=APP_NAME, version="1.1.0")


def ensure_dirs() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def safe_filename(original: str) -> str:
    name = Path(original or "upload.bin").name.strip() or "upload.bin"
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name).strip("._-")
    return cleaned or "upload.bin"


def payment_required_response() -> HTMLResponse:
    if STRIPE_PAYMENT_LINK:
        body = f"""
        <section class="card">
          <h1>Unlock Uploads</h1>
          <p>Payment is required before uploading documents.</p>
          <a class="button" href="{html.escape(STRIPE_PAYMENT_LINK)}">Continue to Secure Checkout</a>
          <p class="muted">Set STRIPE_REQUIRE_PAYMENT=false to disable this gate.</p>
        </section>
        """
    else:
        body = """
        <section class="card">
          <h1>Payment Setup Needed</h1>
          <p>Payment is currently required, but no STRIPE_PAYMENT_LINK is configured.</p>
        </section>
        """
    return HTMLResponse(page_shell("Payment Required", body), status_code=402)


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
                raise HTTPException(status_code=413, detail="File is too large.")
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

    return "PDF uploaded successfully, but readable text was not found. Try a clearer source PDF."


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
    return "DOCX uploaded successfully, but DOCX preview is not available on this server."


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    return f"Unsupported preview type: {suffix or 'unknown'}. The file was uploaded."


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="wrap">{body}</main>
  <script src="/static/app.js"></script>
</body>
</html>"""


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "perfect-pdf-ai", "version": "1.1.0"})


@app.get("/config")
def config() -> JSONResponse:
    return JSONResponse({
        "app_name": APP_NAME,
        "stripe_enabled": bool(STRIPE_PAYMENT_LINK),
        "payment_required": STRIPE_REQUIRE_PAYMENT,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    })


@app.get("/checkout")
def checkout() -> RedirectResponse:
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=503, detail="Stripe payment link is not configured.")
    return RedirectResponse(url=STRIPE_PAYMENT_LINK)


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    checkout_button = ""
    if STRIPE_PAYMENT_LINK:
        checkout_button = '<a class="button secondary" href="/checkout">Unlock with Stripe</a>'
    body = f"""
    <section class="hero card">
      <p class="eyebrow">PDF reader + answer intake</p>
      <h1>{html.escape(APP_NAME)}</h1>
      <p>Upload a document, read the extracted text, then upload the user answers in the next box.</p>
      <form method="post" action="/upload" enctype="multipart/form-data" class="upload-form">
        <input type="file" name="file" accept=".pdf,.txt,.md,.csv,.docx" required>
        <div class="actions">
          <button type="submit">Upload and Read</button>
          {checkout_button}
        </div>
      </form>
      <p class="muted">Supported previews: PDF, TXT, MD, CSV, DOCX. Max file size: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.</p>
    </section>
    """
    return HTMLResponse(page_shell(APP_NAME, body))


@app.post("/upload", response_class=HTMLResponse)
def upload_document(file: UploadFile = File(...)) -> HTMLResponse:
    if STRIPE_REQUIRE_PAYMENT:
        return payment_required_response()

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
      <form method="post" action="/submit-answers" enctype="multipart/form-data" class="upload-form">
        <input type="file" name="file" required>
        <button type="submit">Upload Answers</button>
      </form>
      <p><a class="button secondary" href="/">Start Over</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Document Uploaded", body))


@app.post("/api/upload")
def api_upload_document(file: UploadFile = File(...)) -> JSONResponse:
    if STRIPE_REQUIRE_PAYMENT:
        return JSONResponse({"ok": False, "error": "payment_required", "payment_link": STRIPE_PAYMENT_LINK}, status_code=402)
    path = save_upload(file, DOCUMENT_DIR)
    text = extract_text(path)
    return JSONResponse({"ok": True, "file_name": path.name.split("_", 1)[-1], "stored_name": path.name, "text": text})


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


@app.post("/api/submit-answers")
def api_submit_answers(file: UploadFile = File(...)) -> JSONResponse:
    path = save_upload(file, ANSWER_DIR)
    return JSONResponse({"ok": True, "file_name": path.name.split("_", 1)[-1], "stored_name": path.name})


@app.get("/submit_answers")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url="/")
