#!/usr/bin/env python3
"""
Perfect PDF AI — deployable PDF/document reader, answer intake, login, and Stripe-ready app.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Final, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
STATIC_DIR: Final[Path] = BASE_DIR / "static"
UPLOAD_DIR: Final[Path] = BASE_DIR / "uploads"
DOCUMENT_DIR: Final[Path] = UPLOAD_DIR / "documents"
ANSWER_DIR: Final[Path] = UPLOAD_DIR / "answers"
DATA_DIR: Final[Path] = BASE_DIR / "data"
DB_PATH: Final[Path] = DATA_DIR / "app.sqlite3"
MAX_UPLOAD_BYTES: Final[int] = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_EXTENSIONS: Final[set[str]] = {".pdf", ".txt", ".md", ".csv", ".docx"}
SESSION_COOKIE: Final[str] = "perfect_pdf_session"

APP_NAME: Final[str] = os.getenv("APP_NAME", "Perfect PDF AI")
STRIPE_PAYMENT_LINK: Final[str] = os.getenv("STRIPE_PAYMENT_LINK", "").strip()
STRIPE_REQUIRE_PAYMENT: Final[bool] = os.getenv("STRIPE_REQUIRE_PAYMENT", "false").strip().lower() in {"1", "true", "yes", "on"}
REQUIRE_LOGIN: Final[bool] = os.getenv("REQUIRE_LOGIN", "true").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title=APP_NAME, version="1.4.0")


def ensure_dirs() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()


ensure_dirs()
init_db()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(digest, expected)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
        conn.commit()
    return token


def current_user(request: Request) -> Optional[sqlite3.Row]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with db() as conn:
        return conn.execute(
            """
            SELECT users.id, users.email
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()


def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


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


def page_shell(title: str, body: str, request: Optional[Request] = None) -> str:
    user = current_user(request) if request else None
    auth_html = ""
    if user:
        auth_html = f'<div class="topbar"><span>Signed in as {html.escape(user["email"])}</span><a href="/logout">Logout</a></div>'
    else:
        auth_html = '<div class="topbar"><a href="/login">Login</a><a href="/register">Create account</a></div>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="wrap">
    {auth_html}
    {body}
  </main>
  <script src="/static/app.js"></script>
</body>
</html>"""


def payment_required_response(request: Request) -> HTMLResponse:
    checkout_html = '<a class="button" href="/checkout">Continue to Secure Checkout</a>' if STRIPE_PAYMENT_LINK else '<p class="muted">Stripe is not configured yet.</p>'
    body = f"""
    <section class="card">
      <h1>Unlock Uploads</h1>
      <p>Payment is required before uploading documents.</p>
      {checkout_html}
    </section>
    """
    return HTMLResponse(page_shell("Payment Required", body, request), status_code=402)


def login_required_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card">
      <h1>Login Required</h1>
      <p>Create an account or log in before uploading files.</p>
      <div class="actions">
        <a class="button" href="/login">Login</a>
        <a class="button secondary" href="/register">Create Account</a>
      </div>
    </section>
    """
    return HTMLResponse(page_shell("Login Required", body, request), status_code=401)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "perfect-pdf-ai", "version": "1.4.0"})


@app.get("/config")
def config() -> JSONResponse:
    return JSONResponse({
        "app_name": APP_NAME,
        "stripe_enabled": bool(STRIPE_PAYMENT_LINK),
        "payment_required": STRIPE_REQUIRE_PAYMENT,
        "require_login": REQUIRE_LOGIN,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    })


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card">
      <h1>Create Account</h1>
      <p>Create a login to upload documents and answers.</p>
      <form method="post" action="/register" class="upload-form">
        <input name="email" type="email" placeholder="Email" autocomplete="email" required>
        <input name="password" type="password" placeholder="Password" autocomplete="new-password" minlength="8" required>
        <button type="submit">Create Account</button>
      </form>
      <p class="muted">Already have an account? <a href="/login">Login</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Create Account", body, request))


@app.post("/register")
def register(email: str = Form(...), password: str = Form(...)) -> RedirectResponse | HTMLResponse:
    email_clean = email.strip().lower()
    if len(password) < 8:
        return HTMLResponse(page_shell("Create Account", '<section class="card"><h1>Password too short</h1><p>Password must be at least 8 characters.</p><a class="button" href="/register">Try Again</a></section>'), status_code=400)
    try:
        with db() as conn:
            cursor = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email_clean, hash_password(password)))
            conn.commit()
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return HTMLResponse(page_shell("Create Account", '<section class="card"><h1>Account Exists</h1><p>That email is already registered.</p><a class="button" href="/login">Login</a></section>'), status_code=409)

    token = create_session(user_id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=False, samesite="lax", max_age=60 * 60 * 24 * 30)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card">
      <h1>Login</h1>
      <p>Log in to upload documents and answers.</p>
      <form method="post" action="/login" class="upload-form">
        <input name="email" type="email" placeholder="Email" autocomplete="email" required>
        <input name="password" type="password" placeholder="Password" autocomplete="current-password" required>
        <button type="submit">Login</button>
      </form>
      <p class="muted">Need an account? <a href="/register">Create one</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Login", body, request))


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)) -> RedirectResponse | HTMLResponse:
    email_clean = email.strip().lower()
    with db() as conn:
        user = conn.execute("SELECT id, password_hash FROM users WHERE email = ?", (email_clean,)).fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        return HTMLResponse(page_shell("Login", '<section class="card"><h1>Login Failed</h1><p>Email or password was incorrect.</p><a class="button" href="/login">Try Again</a></section>'), status_code=401)

    token = create_session(int(user["id"]))
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=False, samesite="lax", max_age=60 * 60 * 24 * 30)
    return response


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/checkout")
def checkout() -> RedirectResponse:
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=503, detail="Stripe payment link is not configured.")
    return RedirectResponse(url=STRIPE_PAYMENT_LINK)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
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
    return HTMLResponse(page_shell(APP_NAME, body, request))


@app.post("/upload", response_class=HTMLResponse)
def upload_document(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    if REQUIRE_LOGIN and current_user(request) is None:
        return login_required_page(request)
    if STRIPE_REQUIRE_PAYMENT:
        return payment_required_response(request)

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
    return HTMLResponse(page_shell("Document Uploaded", body, request))


@app.post("/api/upload")
def api_upload_document(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    if REQUIRE_LOGIN and current_user(request) is None:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    if STRIPE_REQUIRE_PAYMENT:
        return JSONResponse({"ok": False, "error": "payment_required", "payment_link": STRIPE_PAYMENT_LINK}, status_code=402)
    path = save_upload(file, DOCUMENT_DIR)
    text = extract_text(path)
    return JSONResponse({"ok": True, "file_name": path.name.split("_", 1)[-1], "stored_name": path.name, "text": text})


@app.post("/submit-answers", response_class=HTMLResponse)
def submit_answers(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    if REQUIRE_LOGIN and current_user(request) is None:
        return login_required_page(request)
    path = save_upload(file, ANSWER_DIR, validate_type=False)
    escaped_name = html.escape(path.name.split("_", 1)[-1])
    body = f"""
    <section class="card success">
      <h1>Answers Uploaded</h1>
      <p>Your answers file <strong>{escaped_name}</strong> was uploaded successfully.</p>
      <p><a class="button" href="/">Upload Another Document</a></p>
    </section>
    """
    return HTMLResponse(page_shell("Answers Uploaded", body, request))


@app.post("/api/submit-answers")
def api_submit_answers(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    if REQUIRE_LOGIN and current_user(request) is None:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    path = save_upload(file, ANSWER_DIR, validate_type=False)
    return JSONResponse({"ok": True, "file_name": path.name.split("_", 1)[-1], "stored_name": path.name})


@app.get("/submit_answers")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url="/")
