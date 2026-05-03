#!/usr/bin/env python3
"""
Perfect PDF AI — deployable PDF/document reader, answer intake, and Stripe-ready app.
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Final

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
STATIC_DIR: Final[Path] = BASE_DIR / "static"
UPLOAD_DIR: Final[Path] = BASE_DIR / "uploads"
DOCUMENT_DIR: Final[Path] = UPLOAD_DIR / "documents"
ANSWER_DIR: Final[Path] = UPLOAD_DIR / "answers"
MAX_UPLOAD_BYTES: Final[int] = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_EXTENSIONS: Final[set[str]] = {".pdf", ".txt", ".md", ".csv", ".docx"}

APP_NAME: Final[str] = os.getenv("APP_NAME", "Perfect PDF AI")
STRIPE_PAYMENT_LINK: Final[str] = os.getenv("STRIPE_PAYMENT_LINK", "").strip()
STRIPE_REQUIRE_PAYMENT: Final[bool] = os.getenv("STRIPE_REQUIRE_PAYMENT", "false").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title=APP_NAME, version="1.3.0")


def ensure_dirs() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def safe_filename(original: str) -> str:
    name = Path(original or "upload.bin").name.strip() or "upload.bin"
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name).strip("._-")
    return cleaned or "upload.bin"


def validate_extension(filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {allowed}")


def save_upload(upload: UploadFile, destination_dir: Path, *, validate_type: bool = True) -> Path:
    ensure_dirs()
    filename = safe_filename(upload.filename or "upload.bin")
    if validate_type:
        validate_extension(filename)

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
                raise HTTPException(status_code=413, detail=f"File is too large. Max size is {MAX_UPLOAD_BYTES} bytes.")
            out.write(chunk)

    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file was empty.")

    return destination


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz

        pieces: list[str] = []
        with fitz.open(path) as doc:
            if doc.page_count == 0:
                return "PDF uploaded successfully, but it had no pages."
            for page_number, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                pieces.append(f"\n--- Page {page_number} ---\n{text}")
        result = "\n".join(pieces).strip()
        if result:
            return result
    except Exception as exc:
        fallback_note = f"PyMuPDF extraction failed: {type(exc).__name__}."
    else:
        fallback_note = "No readable PDF text was found by PyMuPDF."

    if shutil.which("pdftotext"):
        completed = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()

    return f"PDF uploaded successfully, but readable text was not found. {fallback_note} Try a clearer source PDF."


def extract_docx_text(path: Path) -> str:
    if shutil.which("docx2txt"):
        completed = subprocess.run(
            ["docx2txt", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
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


def payment_required_response() -> HTMLResponse:
    checkout_html = ""
    if STRIPE_PAYMENT_LINK:
        checkout_html = '<a class="button" href="/checkout">Continue to Secure Checkout</a>'
    else:
        checkout_html = '<p class="muted">Stripe is not configured yet.</p>'

    body = f"""
    <section class="card">
      <h1>Unlock Uploads</h1>
      <p>Payment is required before uploading documents.</p>
      {checkout_html}
    </section>
    """
    return HTMLResponse(page_shell("Payment Required", body), status_code=402)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "perfect-pdf-ai", "version": "1.3.0"})


@app.get("/config")
def config() -> JSONResponse:
    return JSONResponse({
        "app_name": APP_NAME,
        "stripe_enabled": bool(STRIPE_PAYMENT_LINK),
        "payment_required": STRIPE_REQUIRE_PAYMENT,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    })


@app.get("/checkout")
def checkout() -> RedirectResponse:
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=503, detail="Stripe payment link is not configured.")
    return RedirectResponse(url=STRIPE_PAYMENT_LINK)


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    checkout_button = '<a class="button secondary" href="/checkout">Unlock with Stripe</a>' if STRIPE_PAYMENT_LINK else ""
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
    path = save_upload(file, ANSWER_DIR, validate_type=False)
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
    path = save_upload(file, ANSWER_DIR, validate_type=False)
    return JSONResponse({"ok": True, "file_name": path.name.split("_", 1)[-1], "stored_name": path.name})


@app.get("/submit_answers")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url="/")
