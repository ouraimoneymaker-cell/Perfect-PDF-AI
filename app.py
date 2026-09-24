#!/usr/bin/env python3
"""
Perfect PDF AI — secure document intake, smart field mapping, reusable answers,
completed-PDF generation, account history, and Stripe-ready monetization.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Final, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import fitz
import stripe
from cryptography.fernet import Fernet, InvalidToken
from docx import Document as DocxDocument
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


BASE_DIR: Final[Path] = Path(__file__).resolve().parent
STATIC_DIR: Final[Path] = BASE_DIR / "static"
DATA_DIR: Final[Path] = BASE_DIR / "data"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME: Final[str] = os.getenv("APP_NAME", "Perfect PDF AI").strip() or "Perfect PDF AI"
ENVIRONMENT: Final[str] = os.getenv("ENVIRONMENT", "development").strip().lower()
MAX_UPLOAD_BYTES: Final[int] = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
SESSION_COOKIE: Final[str] = "perfect_pdf_session"
SESSION_DAYS: Final[int] = int(os.getenv("SESSION_DAYS", "30"))
COOKIE_SECURE: Final[bool] = os.getenv(
    "COOKIE_SECURE", "true" if ENVIRONMENT == "production" else "false"
).strip().lower() in {"1", "true", "yes", "on"}

APP_SECRET_KEY: Final[str] = os.getenv("APP_SECRET_KEY", "").strip()
EFFECTIVE_APP_SECRET: Final[str] = APP_SECRET_KEY or "perfect-pdf-ai-development-only-secret"
SECURE_CONFIGURATION: Final[bool] = bool(APP_SECRET_KEY) and len(APP_SECRET_KEY) >= 32

STRIPE_PAYMENT_LINK: Final[str] = os.getenv("STRIPE_PAYMENT_LINK", "").strip()
STRIPE_WEBHOOK_SECRET: Final[str] = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_REQUIRE_PAYMENT: bool = os.getenv("STRIPE_REQUIRE_PAYMENT", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PAYMENT_CREDITS: Final[int] = max(1, int(os.getenv("PAYMENT_CREDITS", "1")))
FREE_COMPLETIONS: Final[int] = max(0, int(os.getenv("FREE_COMPLETIONS", "1")))

ALLOWED_EXTENSIONS: Final[set[str]] = {".pdf", ".txt", ".md", ".csv", ".docx"}
ANSWER_EXTENSIONS: Final[set[str]] = {".txt", ".md", ".csv", ".json"}

_raw_db_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_db_url:
    DATABASE_URL = f"sqlite:///{(DATA_DIR / 'perfect_pdf_ai.sqlite3').as_posix()}"
elif _raw_db_url.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + _raw_db_url[len("postgres://") :]
elif _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + _raw_db_url[len("postgresql://") :]
else:
    DATABASE_URL = _raw_db_url

_engine_kwargs: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite:"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "ppa_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=FREE_COMPLETIONS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthSession(Base):
    __tablename__ = "ppa_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("ppa_users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnswerProfile(Base):
    __tablename__ = "ppa_answer_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("ppa_users.id", ondelete="CASCADE"), primary_key=True)
    encrypted_answers: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentRecord(Base):
    __tablename__ = "ppa_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("ppa_users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    analysis_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    completed_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    answer_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="analyzed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PaymentRecord(Base):
    __tablename__ = "ppa_payments"

    stripe_session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("ppa_users.id", ondelete="CASCADE"), index=True)
    amount_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


Base.metadata.create_all(engine)

_secret_digest = hashlib.sha256(EFFECTIVE_APP_SECRET.encode("utf-8")).digest()
fernet = Fernet(base64.urlsafe_b64encode(_secret_digest))


@contextmanager
def db_session() -> Iterable[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def encrypt_bytes(data: bytes) -> bytes:
    return fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    try:
        return fernet.decrypt(data)
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored document encryption key mismatch.") from exc


def encrypt_json(value: object) -> bytes:
    return encrypt_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def decrypt_json(data: bytes) -> object:
    return json.loads(decrypt_bytes(data).decode("utf-8"))


def hash_password(password: str) -> str:
    iterations = 390_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return "pbkdf2_sha256$" + str(iterations) + "$" + salt + "$" + digest


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations_text, salt, expected = stored.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return hmac.compare_digest(digest, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db_session() as session:
        session.add(
            AuthSession(
                token_hash=token_hash(token),
                user_id=user_id,
                expires_at=utcnow() + timedelta(days=SESSION_DAYS),
            )
        )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def current_user(request: Request) -> Optional[User]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    with db_session() as session:
        auth = session.get(AuthSession, token_hash(raw))
        if auth is None:
            return None
        expires = auth.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= utcnow():
            session.delete(auth)
            return None
        user = session.get(User, auth.user_id)
        if user is None:
            session.delete(auth)
            return None
        session.expunge(user)
        return user


def require_user(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


def csrf_for_token(raw_session_token: str) -> str:
    return hmac.new(
        EFFECTIVE_APP_SECRET.encode("utf-8"),
        raw_session_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def csrf_for_request(request: Request) -> str:
    raw = request.cookies.get(SESSION_COOKIE, "")
    return csrf_for_token(raw) if raw else ""


def validate_csrf(request: Request, submitted: str) -> None:
    expected = csrf_for_request(request)
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="Invalid form token. Refresh the page and try again.")


def safe_filename(original: str) -> str:
    name = Path(original or "upload.bin").name.strip() or "upload.bin"
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip(" ._-")
    return (cleaned or "upload.bin")[:255]


def validate_extension(filename: str, allowed: set[str] = ALLOWED_EXTENSIONS) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}",
        )
    return suffix


def read_upload_bytes(upload: UploadFile, allowed: set[str] = ALLOWED_EXTENSIONS) -> tuple[str, str, bytes]:
    filename = safe_filename(upload.filename or "upload.bin")
    suffix = validate_extension(filename, allowed)
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large. Max size is {MAX_UPLOAD_BYTES} bytes.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file was empty.")

    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded .pdf is not a valid PDF file.")
    if suffix == ".docx" and not data.startswith(b"PK"):
        raise HTTPException(status_code=415, detail="The uploaded .docx is not a valid DOCX file.")
    if suffix in {".txt", ".md", ".csv"}:
        data.decode("utf-8", errors="strict")

    return filename, suffix, data


CANONICAL_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "full_name": (
        "full name",
        "applicant name",
        "name of applicant",
        "your name",
        "legal name",
        "name",
    ),
    "first_name": ("first name", "given name", "forename"),
    "middle_name": ("middle name", "middle initial"),
    "last_name": ("last name", "surname", "family name"),
    "address": ("street address", "home address", "mailing address", "address"),
    "address_2": ("address line 2", "apartment", "apt", "unit", "suite"),
    "city": ("city", "town"),
    "state": ("state", "province"),
    "zip": ("zip code", "zipcode", "postal code", "zip"),
    "email": ("email address", "e-mail address", "email", "e-mail"),
    "phone": ("phone number", "telephone number", "mobile number", "cell phone", "phone"),
    "date_of_birth": ("date of birth", "birth date", "dob"),
    "employer": ("employer name", "current employer", "employer"),
    "occupation": ("job title", "occupation", "position"),
    "company": ("company name", "business name", "company"),
    "date": ("today's date", "current date", "date"),
    "signature": ("applicant signature", "your signature", "signature"),
}

STOPWORDS: Final[set[str]] = {
    "the",
    "a",
    "an",
    "of",
    "your",
    "you",
    "please",
    "enter",
    "provide",
    "applicant",
    "applicable",
    "if",
    "what",
    "is",
    "are",
    "for",
    "to",
    "and",
}


def normalize_label(value: str) -> str:
    value = value.lower().replace("_", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def canonical_key(label: str) -> str:
    normalized = normalize_label(label)
    for key, phrases in CANONICAL_GROUPS.items():
        for phrase in phrases:
            p = normalize_label(phrase)
            if normalized == p or (len(p) >= 4 and p in normalized):
                return key
    return normalized


def label_tokens(label: str) -> set[str]:
    return {t for t in normalize_label(label).split() if t not in STOPWORDS and len(t) > 1}


def semantic_score(field_label: str, answer_label: str) -> float:
    f_norm = normalize_label(field_label)
    a_norm = normalize_label(answer_label)
    if not f_norm or not a_norm:
        return 0.0
    if f_norm == a_norm:
        return 1.0

    f_key = canonical_key(field_label)
    a_key = canonical_key(answer_label)
    if f_key == a_key and f_key in CANONICAL_GROUPS:
        return 0.99

    f_tokens = label_tokens(field_label)
    a_tokens = label_tokens(answer_label)
    union = f_tokens | a_tokens
    jaccard = len(f_tokens & a_tokens) / len(union) if union else 0.0
    ratio = SequenceMatcher(None, f_norm, a_norm).ratio()
    substring = 0.85 if (f_norm in a_norm or a_norm in f_norm) and min(len(f_norm), len(a_norm)) >= 4 else 0.0
    return max(ratio * 0.72 + jaccard * 0.28, substring)


def map_answers(fields: list[dict], answers: dict[str, str], threshold: float = 0.42) -> dict[str, dict]:
    mapped: dict[str, dict] = {}
    cleaned_answers = {str(k): str(v).strip() for k, v in answers.items() if str(v).strip()}
    for field in fields:
        label = str(field.get("label", "")).strip()
        if not label:
            continue
        best_label = ""
        best_value = ""
        best_score = 0.0
        for answer_label, value in cleaned_answers.items():
            score = semantic_score(label, answer_label)
            if score > best_score:
                best_label, best_value, best_score = answer_label, value, score
        if best_value and best_score >= threshold:
            mapped[str(field["id"])] = {
                "field_label": label,
                "answer_label": best_label,
                "value": best_value,
                "score": round(best_score, 4),
            }
    return mapped


def parse_answer_text(text: str) -> dict[str, str]:
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return {str(k).strip(): str(v).strip() for k, v in payload.items() if str(v).strip()}

    answers: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line:
            continue
        separator = ":" if ":" in line else "=" if "=" in line else None
        if not separator:
            continue
        key, value = line.split(separator, 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            answers[key] = value
    return answers


def merge_profile(existing: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    merged = dict(existing)
    for key, value in updates.items():
        value = str(value).strip()
        if not value:
            continue
        merged[str(key).strip()] = value
        canon = canonical_key(str(key))
        if canon in CANONICAL_GROUPS:
            merged[canon] = value
    return merged


def is_question_candidate(text: str) -> bool:
    stripped = " ".join(text.split()).strip()
    if len(stripped) < 2 or len(stripped) > 140:
        return False
    normalized = normalize_label(stripped)
    if not normalized:
        return False
    if stripped.endswith("?") or stripped.endswith(":") or re.search(r"_{3,}", stripped):
        return True
    for phrases in CANONICAL_GROUPS.values():
        if any(normalize_label(p) in normalized for p in phrases if len(p) >= 3):
            return True
    return False


def extract_pdf_analysis(data: bytes) -> dict:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The PDF could not be opened.") from exc

    fields: list[dict] = []
    full_text_parts: list[str] = []
    seen: set[tuple[int, str, str]] = set()

    for page_index, page in enumerate(doc):
        page_text = page.get_text("text") or ""
        full_text_parts.append(f"--- Page {page_index + 1} ---\n{page_text}".strip())

        widgets = list(page.widgets() or [])
        for widget in widgets:
            label = (widget.field_label or widget.field_name or "").strip()
            if not label:
                continue
            key = (page_index, normalize_label(label), "widget")
            if key in seen:
                continue
            seen.add(key)
            rect = widget.rect
            fields.append(
                {
                    "id": f"f{len(fields)+1}",
                    "label": label,
                    "kind": "widget",
                    "page": page_index,
                    "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "widget_name": widget.field_name or label,
                }
            )

        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(str(span.get("text", "")) for span in spans).strip()
                if not text or not is_question_candidate(text):
                    continue
                bbox = line.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                normalized = normalize_label(text)
                if any(
                    normalize_label(existing["label"]) == normalized
                    and existing["page"] == page_index
                    for existing in fields
                ):
                    continue
                key = (page_index, normalized, "text")
                if key in seen:
                    continue
                seen.add(key)
                fields.append(
                    {
                        "id": f"f{len(fields)+1}",
                        "label": text,
                        "kind": "text",
                        "page": page_index,
                        "rect": [float(v) for v in bbox],
                    }
                )

    page_count = doc.page_count
    doc.close()
    return {
        "type": "pdf",
        "page_count": page_count,
        "fields": fields,
        "text": "\n\n".join(full_text_parts).strip(),
    }


def extract_docx_text(data: bytes) -> str:
    try:
        document = DocxDocument(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The DOCX could not be opened.") from exc
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def analyze_document(filename: str, suffix: str, data: bytes) -> dict:
    if suffix == ".pdf":
        return extract_pdf_analysis(data)
    if suffix == ".docx":
        text = extract_docx_text(data)
    else:
        text = data.decode("utf-8", errors="replace")

    fields: list[dict] = []
    for line in text.splitlines():
        if is_question_candidate(line):
            fields.append(
                {
                    "id": f"f{len(fields)+1}",
                    "label": line.strip(),
                    "kind": "text_only",
                    "page": 0,
                    "rect": None,
                }
            )
    return {"type": suffix.lstrip("."), "page_count": 1, "fields": fields, "text": text}


def _safe_pdf_text(value: str) -> str:
    return value.replace("\x00", "").strip()


def generate_completed_pdf(
    source_bytes: bytes,
    filename: str,
    analysis: dict,
    mapped: dict[str, dict],
    all_answers: dict[str, str],
) -> bytes:
    if Path(filename).suffix.lower() != ".pdf":
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((54, 54), APP_NAME, fontsize=18)
        page.insert_text((54, 82), f"Completed answers for {filename}", fontsize=11)
        y = 116
        for key, value in all_answers.items():
            if y > 740:
                page = doc.new_page(width=612, height=792)
                y = 54
            text = _safe_pdf_text(f"{key}: {value}")
            page.insert_textbox(fitz.Rect(54, y, 558, y + 36), text, fontsize=10)
            y += 32
        result = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return result

    try:
        doc = fitz.open(stream=source_bytes, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The original PDF could not be reopened.") from exc

    fields_by_id = {str(field["id"]): field for field in analysis.get("fields", [])}

    mapped_by_widget_name: dict[str, str] = {}
    for field_id, match in mapped.items():
        field = fields_by_id.get(field_id, {})
        if field.get("kind") == "widget":
            mapped_by_widget_name[str(field.get("widget_name", ""))] = str(match["value"])

    for page in doc:
        for widget in list(page.widgets() or []):
            name = widget.field_name or ""
            if name not in mapped_by_widget_name:
                continue
            try:
                widget.field_value = mapped_by_widget_name[name]
                widget.update()
            except Exception:
                pass

    for field_id, match in mapped.items():
        field = fields_by_id.get(field_id)
        if not field or field.get("kind") == "widget":
            continue
        rect_data = field.get("rect")
        page_index = int(field.get("page", 0))
        if not rect_data or page_index < 0 or page_index >= doc.page_count:
            continue
        page = doc[page_index]
        label_rect = fitz.Rect(*rect_data)
        value = _safe_pdf_text(str(match.get("value", "")))
        if not value:
            continue

        right_space = page.rect.width - label_rect.x1
        if right_space >= 130:
            target = fitz.Rect(
                label_rect.x1 + 6,
                max(12, label_rect.y0 - 2),
                page.rect.width - 36,
                min(page.rect.height - 24, label_rect.y1 + 18),
            )
        else:
            target = fitz.Rect(
                max(36, label_rect.x0),
                min(page.rect.height - 44, label_rect.y1 + 2),
                page.rect.width - 36,
                min(page.rect.height - 18, label_rect.y1 + 26),
            )

        if target.width < 60 or target.height < 10:
            continue
        page.draw_rect(target, color=(0.78, 0.84, 0.92), fill=(1, 1, 1), width=0.5, overlay=True)
        page.insert_textbox(
            target + (3, 2, -3, -2),
            value,
            fontsize=9.5,
            color=(0.05, 0.20, 0.48),
            fontname="helv",
            overlay=True,
        )

    summary = doc.new_page(width=612, height=792)
    summary.insert_text((54, 54), f"{APP_NAME} — Completed Answers", fontsize=17)
    summary.insert_text((54, 78), f"Source: {safe_filename(filename)}", fontsize=10)
    y = 112
    ordered = []
    used_keys: set[str] = set()
    for match in mapped.values():
        key = str(match.get("field_label", "")).strip()
        value = str(match.get("value", "")).strip()
        if key and value and key not in used_keys:
            used_keys.add(key)
            ordered.append((key, value))
    if not ordered:
        ordered = list(all_answers.items())

    for key, value in ordered:
        if y > 735:
            summary = doc.new_page(width=612, height=792)
            y = 54
        line = _safe_pdf_text(f"{key}: {value}")
        used = summary.insert_textbox(fitz.Rect(54, y, 558, y + 42), line, fontsize=10.5)
        y += 34 if used >= 0 else 46

    result = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return result


def get_profile(user_id: int) -> dict[str, str]:
    with db_session() as session:
        record = session.get(AnswerProfile, user_id)
        if record is None:
            return {}
        payload = decrypt_json(record.encrypted_answers)
        return payload if isinstance(payload, dict) else {}


def save_profile(user_id: int, answers: dict[str, str]) -> None:
    with db_session() as session:
        existing = session.get(AnswerProfile, user_id)
        encrypted = encrypt_json(answers)
        if existing is None:
            session.add(AnswerProfile(user_id=user_id, encrypted_answers=encrypted, updated_at=utcnow()))
        else:
            existing.encrypted_answers = encrypted
            existing.updated_at = utcnow()


def get_document_for_user(document_id: str, user_id: int) -> DocumentRecord:
    with db_session() as session:
        record = session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.user_id == user_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        session.expunge(record)
        return record


def payment_configured() -> bool:
    return bool(STRIPE_PAYMENT_LINK and STRIPE_WEBHOOK_SECRET)


def checkout_url_for_user(user: User) -> str:
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=503, detail="Stripe checkout is not configured.")
    parts = urlsplit(STRIPE_PAYMENT_LINK)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["client_reference_id"] = str(user.id)
    query["prefilled_email"] = user.email
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def has_completion_credit(user_id: int) -> bool:
    if not STRIPE_REQUIRE_PAYMENT:
        return True
    with db_session() as session:
        user = session.get(User, user_id)
        return bool(user and user.credits > 0)


def consume_credit_if_required(user_id: int) -> None:
    if not STRIPE_REQUIRE_PAYMENT:
        return
    with db_session() as session:
        user = session.get(User, user_id)
        if user is None or user.credits <= 0:
            raise HTTPException(status_code=402, detail="A completion credit is required.")
        user.credits -= 1


def fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def page_shell(title: str, body: str, request: Optional[Request] = None) -> str:
    user = current_user(request) if request else None
    nav = ""
    if user:
        csrf = html.escape(csrf_for_request(request))
        nav = f"""
        <div class="topbar">
          <a class="brand" href="/">{html.escape(APP_NAME)}</a>
          <div class="topbar-right">
            <span class="muted">{html.escape(user.email)}</span>
            <form method="post" action="/logout" class="inline-form">
              <input type="hidden" name="csrf" value="{csrf}">
              <button class="link-button" type="submit">Logout</button>
            </form>
          </div>
        </div>
        """
    else:
        nav = f"""
        <div class="topbar">
          <a class="brand" href="/">{html.escape(APP_NAME)}</a>
          <div class="topbar-right"><a href="/login">Login</a><a href="/register">Create account</a></div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="Upload a form, reuse your answers, and generate a completed PDF.">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="wrap">
    {nav}
    {body}
  </main>
  <script src="/static/app.js"></script>
</body>
</html>"""


def login_required_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card narrow">
      <p class="eyebrow">Account required</p>
      <h1>Sign in to continue</h1>
      <p>Your documents and saved answers are tied to your account.</p>
      <div class="actions">
        <a class="button" href="/login">Login</a>
        <a class="button secondary" href="/register">Create account</a>
      </div>
    </section>
    """
    return HTMLResponse(page_shell("Login Required", body, request), status_code=401)


def payment_required_page(request: Request, user: User) -> HTMLResponse:
    if STRIPE_PAYMENT_LINK:
        action = '<a class="button" href="/checkout">Buy a completion credit</a>'
    else:
        action = '<p class="warning">Payments are not configured yet. The owner must connect Stripe before paid completions can be sold.</p>'
    body = f"""
    <section class="card narrow">
      <p class="eyebrow">Completion credit required</p>
      <h1>Your PDF is ready to finish</h1>
      <p>Upload and analysis are complete. A completion credit is required to generate and save the finished PDF.</p>
      {action}
      <p class="muted">Current credits: {user.credits}</p>
    </section>
    """
    return HTMLResponse(page_shell("Payment Required", body, request), status_code=402)


app = FastAPI(title=APP_NAME, version="2.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
def health() -> JSONResponse:
    try:
        with db_session() as session:
            session.execute(select(User.id).limit(1))
        database_ok = True
    except Exception:
        database_ok = False
    status = 200 if database_ok else 503
    return JSONResponse(
        {
            "ok": database_ok,
            "service": "perfect-pdf-ai",
            "version": "2.0.0",
            "database": database_ok,
            "secure_configuration": SECURE_CONFIGURATION if ENVIRONMENT == "production" else True,
            "payments_configured": payment_configured(),
        },
        status_code=status,
    )


@app.get("/config")
def config() -> JSONResponse:
    return JSONResponse(
        {
            "app_name": APP_NAME,
            "environment": ENVIRONMENT,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            "payment_required": STRIPE_REQUIRE_PAYMENT,
            "payment_configured": payment_configured(),
            "payment_credits": PAYMENT_CREDITS,
            "free_completions": FREE_COMPLETIONS,
        }
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    user = current_user(request)
    if user is None:
        body = f"""
        <section class="hero card">
          <p class="eyebrow">Upload → understand → answer once → complete</p>
          <h1>{html.escape(APP_NAME)}</h1>
          <p class="lead">Turn messy applications and forms into completed PDFs. The app detects fields and questions, reuses answers you have already supplied, maps them to new forms, and creates a finished PDF you can download.</p>
          <div class="actions">
            <a class="button" href="/register">Try it</a>
            <a class="button secondary" href="/login">Login</a>
          </div>
        </section>
        <section class="feature-grid">
          <article class="card"><h2>1. Upload</h2><p>PDF, DOCX, TXT, MD, or CSV up to {MAX_UPLOAD_BYTES // (1024*1024)} MB.</p></article>
          <article class="card"><h2>2. Smart map</h2><p>Detects form fields and printed questions, then matches them to your reusable answer profile.</p></article>
          <article class="card"><h2>3. Download</h2><p>Generates a completed PDF and keeps an encrypted account history.</p></article>
        </section>
        """
        return HTMLResponse(page_shell(APP_NAME, body, request))

    csrf = html.escape(csrf_for_request(request))
    with db_session() as session:
        db_user = session.get(User, user.id)
        credits = db_user.credits if db_user else 0
        documents = session.scalars(
            select(DocumentRecord)
            .where(DocumentRecord.user_id == user.id)
            .order_by(DocumentRecord.created_at.desc())
            .limit(30)
        ).all()

    payment_html = ""
    if STRIPE_REQUIRE_PAYMENT:
        payment_html = f'<span class="pill">{credits} completion credit{"s" if credits != 1 else ""}</span>'
        if credits <= 0 and STRIPE_PAYMENT_LINK:
            payment_html += ' <a class="button small" href="/checkout">Buy credit</a>'

    history_cards = []
    for record in documents:
        download = (
            f'<a class="button small" href="/documents/{record.id}/download">Download completed PDF</a>'
            if record.completed_blob
            else ""
        )
        history_cards.append(
            f"""
            <article class="document-card">
              <div>
                <strong>{html.escape(record.filename)}</strong>
                <p class="muted">{html.escape(record.status.title())} · {fmt_time(record.created_at)}</p>
              </div>
              <div class="actions compact">
                <a class="button secondary small" href="/documents/{record.id}">Open</a>
                {download}
              </div>
            </article>
            """
        )
    history_html = "".join(history_cards) or '<p class="muted">No documents yet. Upload your first form above.</p>'

    body = f"""
    <section class="card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Your workspace</p>
          <h1>Complete a form</h1>
        </div>
        <div>{payment_html}</div>
      </div>
      <p>Upload a document. Perfect PDF AI will detect fillable fields and printed questions before you enter anything.</p>
      <form method="post" action="/upload" enctype="multipart/form-data" class="upload-form">
        <input type="hidden" name="csrf" value="{csrf}">
        <input type="file" name="file" accept=".pdf,.txt,.md,.csv,.docx" required>
        <button type="submit">Upload and analyze</button>
        <p class="form-status muted" aria-live="polite"></p>
      </form>
      <p class="muted">Your stored files and saved answers are encrypted before being written to the database.</p>
    </section>

    <section class="card">
      <h2>Import reusable answers</h2>
      <p>Optional: upload a TXT, MD, CSV, or JSON file containing entries such as <code>Full Name: Jane Smith</code>. These answers will be reused on future forms.</p>
      <form method="post" action="/submit-answers" enctype="multipart/form-data" class="upload-form">
        <input type="hidden" name="csrf" value="{csrf}">
        <input type="file" name="file" accept=".txt,.md,.csv,.json" required>
        <button type="submit">Import answers</button>
      </form>
    </section>

    <section class="card">
      <h2>Your document history</h2>
      <div class="document-list">{history_html}</div>
    </section>
    """
    return HTMLResponse(page_shell(APP_NAME, body, request))


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card narrow">
      <p class="eyebrow">Create your workspace</p>
      <h1>Create account</h1>
      <form method="post" action="/register" class="upload-form">
        <label>Email<input name="email" type="email" autocomplete="email" required></label>
        <label>Password<input name="password" type="password" autocomplete="new-password" minlength="8" required></label>
        <button type="submit">Create account</button>
      </form>
      <p class="muted">Already registered? <a href="/login">Login</a>.</p>
    </section>
    """
    return HTMLResponse(page_shell("Create Account", body, request))


@app.post("/register")
def register(email: str = Form(...), password: str = Form(...)) -> Response:
    email_clean = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_clean):
        return HTMLResponse(
            page_shell(
                "Create Account",
                '<section class="card narrow"><h1>Enter a valid email</h1><a class="button" href="/register">Try again</a></section>',
            ),
            status_code=400,
        )
    if len(password) < 8:
        return HTMLResponse(
            page_shell(
                "Create Account",
                '<section class="card narrow"><h1>Password too short</h1><p>Use at least 8 characters.</p><a class="button" href="/register">Try again</a></section>',
            ),
            status_code=400,
        )
    with db_session() as session:
        if session.scalar(select(User).where(User.email == email_clean)):
            return HTMLResponse(
                page_shell(
                    "Create Account",
                    '<section class="card narrow"><h1>Account exists</h1><p>That email is already registered.</p><a class="button" href="/login">Login</a></section>',
                ),
                status_code=409,
            )
        user = User(email=email_clean, password_hash=hash_password(password), credits=FREE_COMPLETIONS)
        session.add(user)
        session.flush()
        user_id = user.id

    token = create_session(user_id)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, token)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    body = """
    <section class="card narrow">
      <p class="eyebrow">Welcome back</p>
      <h1>Login</h1>
      <form method="post" action="/login" class="upload-form">
        <label>Email<input name="email" type="email" autocomplete="email" required></label>
        <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
        <button type="submit">Login</button>
      </form>
      <p class="muted">Need an account? <a href="/register">Create one</a>.</p>
    </section>
    """
    return HTMLResponse(page_shell("Login", body, request))


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)) -> Response:
    email_clean = email.strip().lower()
    with db_session() as session:
        user = session.scalar(select(User).where(User.email == email_clean))
        valid = bool(user and verify_password(password, user.password_hash))
        user_id = user.id if valid and user else None
    if not valid or user_id is None:
        return HTMLResponse(
            page_shell(
                "Login",
                '<section class="card narrow"><h1>Login failed</h1><p>Email or password was incorrect.</p><a class="button" href="/login">Try again</a></section>',
            ),
            status_code=401,
        )
    token = create_session(user_id)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, token)
    return response


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)) -> RedirectResponse:
    validate_csrf(request, csrf)
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        with db_session() as session:
            auth = session.get(AuthSession, token_hash(raw))
            if auth:
                session.delete(auth)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.post("/upload")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    csrf: str = Form(...),
) -> Response:
    user = current_user(request)
    if user is None:
        return login_required_page(request)
    validate_csrf(request, csrf)
    filename, suffix, data = read_upload_bytes(file)
    analysis = analyze_document(filename, suffix, data)
    document_id = uuid.uuid4().hex

    with db_session() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                user_id=user.id,
                filename=filename,
                media_type=file.content_type or "application/octet-stream",
                source_sha256=hashlib.sha256(data).hexdigest(),
                source_blob=encrypt_bytes(data),
                analysis_blob=encrypt_json(analysis),
                status="analyzed",
                updated_at=utcnow(),
            )
        )
    return RedirectResponse(url=f"/documents/{document_id}", status_code=303)


@app.get("/documents/{document_id}", response_class=HTMLResponse)
def document_detail(request: Request, document_id: str) -> HTMLResponse:
    user = current_user(request)
    if user is None:
        return login_required_page(request)
    record = get_document_for_user(document_id, user.id)
    analysis = decrypt_json(record.analysis_blob)
    if not isinstance(analysis, dict):
        raise HTTPException(status_code=500, detail="Document analysis is invalid.")
    fields = analysis.get("fields", [])
    profile = get_profile(user.id)
    prefilled = map_answers(fields, profile, threshold=0.40)
    csrf = html.escape(csrf_for_request(request))

    field_rows = []
    for index, field in enumerate(fields[:100]):
        field_id = str(field.get("id", ""))
        label = str(field.get("label", "")).strip()
        match = prefilled.get(field_id, {})
        value = str(match.get("value", ""))
        confidence = match.get("score")
        confidence_html = (
            f'<span class="confidence">saved answer match {int(float(confidence) * 100)}%</span>'
            if confidence is not None and value
            else ""
        )
        field_rows.append(
            f"""
            <div class="field-row">
              <label for="answer_{index}">{html.escape(label)} {confidence_html}</label>
              <input type="hidden" name="field_{index}_label" value="{html.escape(label, quote=True)}">
              <input id="answer_{index}" name="field_{index}_answer" value="{html.escape(value, quote=True)}" autocomplete="off">
            </div>
            """
        )
    if not field_rows:
        field_rows.append(
            '<p class="muted">No obvious printed field labels were detected. Paste labeled answers below; they will still be added to the completed PDF summary.</p>'
        )

    with db_session() as session:
        fresh_user = session.get(User, user.id)
        credits = fresh_user.credits if fresh_user else 0

    pay_notice = ""
    if STRIPE_REQUIRE_PAYMENT and credits <= 0:
        if STRIPE_PAYMENT_LINK:
            pay_notice = '<div class="notice"><strong>Payment required to generate.</strong> <a href="/checkout">Buy a completion credit</a>. You can still review the detected fields first.</div>'
        else:
            pay_notice = '<div class="notice warning"><strong>Paid mode is enabled but Stripe is not configured.</strong></div>'

    complete_actions = ""
    if record.completed_blob:
        complete_actions = f"""
        <div class="actions">
          <a class="button" href="/documents/{record.id}/download">Download completed PDF</a>
          <a class="button secondary" href="/documents/{record.id}/source">Download original</a>
        </div>
        """
    else:
        complete_actions = f'<a class="button secondary" href="/documents/{record.id}/source">Download original</a>'

    body = f"""
    <section class="card">
      <p class="eyebrow">Analyzed document</p>
      <div class="section-heading">
        <div><h1>{html.escape(record.filename)}</h1><p>{len(fields)} detected field/question{"s" if len(fields) != 1 else ""} · {int(analysis.get("page_count", 1))} page{"s" if int(analysis.get("page_count", 1)) != 1 else ""}</p></div>
        <span class="pill">{html.escape(record.status.title())}</span>
      </div>
      {complete_actions}
    </section>

    <section class="card">
      <h2>Confirm the answers</h2>
      <p>Saved answers are filled automatically when the labels match. Correct anything that needs changing; the updated values are saved for your next form.</p>
      {pay_notice}
      <form method="post" action="/documents/{record.id}/complete" class="upload-form">
        <input type="hidden" name="csrf" value="{csrf}">
        <div class="field-grid">{"".join(field_rows)}</div>
        <label>Paste additional labeled answers
          <textarea name="answers_text" rows="7" placeholder="Full Name: Jane Smith&#10;Address: 123 Main Street&#10;Phone: 555-555-5555"></textarea>
        </label>
        <button type="submit">Generate completed PDF</button>
      </form>
    </section>
    """
    return HTMLResponse(page_shell(record.filename, body, request))


@app.post("/documents/{document_id}/complete")
async def complete_document(request: Request, document_id: str) -> Response:
    user = current_user(request)
    if user is None:
        return login_required_page(request)

    form = await request.form()
    validate_csrf(request, str(form.get("csrf", "")))

    with db_session() as session:
        fresh_user = session.get(User, user.id)
        if fresh_user is None:
            raise HTTPException(status_code=401, detail="Login required.")
        session.expunge(fresh_user)

    if STRIPE_REQUIRE_PAYMENT and not has_completion_credit(user.id):
        return payment_required_page(request, fresh_user)

    record = get_document_for_user(document_id, user.id)
    analysis = decrypt_json(record.analysis_blob)
    if not isinstance(analysis, dict):
        raise HTTPException(status_code=500, detail="Document analysis is invalid.")
    fields = analysis.get("fields", [])

    submitted: dict[str, str] = {}
    index = 0
    while True:
        label_key = f"field_{index}_label"
        answer_key = f"field_{index}_answer"
        if label_key not in form and answer_key not in form:
            break
        label = str(form.get(label_key, "")).strip()
        value = str(form.get(answer_key, "")).strip()
        if label and value:
            submitted[label] = value
        index += 1
        if index > 200:
            break

    submitted.update(parse_answer_text(str(form.get("answers_text", ""))))
    if not submitted:
        return HTMLResponse(
            page_shell(
                "Answers Required",
                f'<section class="card narrow"><h1>Add at least one answer</h1><p>No answer values were submitted.</p><a class="button" href="/documents/{record.id}">Back to document</a></section>',
                request,
            ),
            status_code=400,
        )

    profile = get_profile(user.id)
    combined = merge_profile(profile, submitted)
    mapped = map_answers(fields, combined, threshold=0.40)
    source_bytes = decrypt_bytes(record.source_blob)
    completed = generate_completed_pdf(source_bytes, record.filename, analysis, mapped, submitted)

    with db_session() as session:
        db_record = session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == record.id,
                DocumentRecord.user_id == user.id,
            )
        )
        if db_record is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        db_record.completed_blob = encrypt_bytes(completed)
        db_record.answer_blob = encrypt_json(mapped)
        db_record.status = "completed"
        db_record.updated_at = utcnow()

        if STRIPE_REQUIRE_PAYMENT:
            db_user = session.get(User, user.id)
            if db_user is None or db_user.credits <= 0:
                raise HTTPException(status_code=402, detail="A completion credit is required.")
            db_user.credits -= 1

    save_profile(user.id, combined)
    return RedirectResponse(url=f"/documents/{record.id}", status_code=303)


@app.get("/documents/{document_id}/download")
def download_completed(request: Request, document_id: str) -> Response:
    user = require_user(request)
    record = get_document_for_user(document_id, user.id)
    if not record.completed_blob:
        raise HTTPException(status_code=404, detail="This document has not been completed yet.")
    data = decrypt_bytes(record.completed_blob)
    stem = Path(record.filename).stem or "completed"
    filename = safe_filename(f"{stem}_completed.pdf")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/documents/{document_id}/source")
def download_source(request: Request, document_id: str) -> Response:
    user = require_user(request)
    record = get_document_for_user(document_id, user.id)
    data = decrypt_bytes(record.source_blob)
    return Response(
        content=data,
        media_type=record.media_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(record.filename)}"'},
    )


@app.post("/submit-answers")
def submit_answers(
    request: Request,
    file: UploadFile = File(...),
    csrf: str = Form(...),
) -> Response:
    user = current_user(request)
    if user is None:
        return login_required_page(request)
    validate_csrf(request, csrf)
    _, suffix, data = read_upload_bytes(file, ANSWER_EXTENSIONS)
    text = data.decode("utf-8", errors="replace")
    answers = parse_answer_text(text)
    if not answers:
        return HTMLResponse(
            page_shell(
                "No Answers Found",
                '<section class="card narrow"><h1>No labeled answers found</h1><p>Use lines like <code>Full Name: Jane Smith</code> or a JSON object.</p><a class="button" href="/">Back</a></section>',
                request,
            ),
            status_code=400,
        )
    merged = merge_profile(get_profile(user.id), answers)
    save_profile(user.id, merged)
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/upload")
def api_upload_document(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    user = current_user(request)
    if user is None:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    filename, suffix, data = read_upload_bytes(file)
    analysis = analyze_document(filename, suffix, data)
    document_id = uuid.uuid4().hex
    with db_session() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                user_id=user.id,
                filename=filename,
                media_type=file.content_type or "application/octet-stream",
                source_sha256=hashlib.sha256(data).hexdigest(),
                source_blob=encrypt_bytes(data),
                analysis_blob=encrypt_json(analysis),
                status="analyzed",
                updated_at=utcnow(),
            )
        )
    return JSONResponse(
        {
            "ok": True,
            "document_id": document_id,
            "file_name": filename,
            "field_count": len(analysis.get("fields", [])),
            "fields": analysis.get("fields", []),
            "text_preview": str(analysis.get("text", ""))[:4000],
        }
    )


@app.post("/api/submit-answers")
def api_submit_answers(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    user = current_user(request)
    if user is None:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    _, _, data = read_upload_bytes(file, ANSWER_EXTENSIONS)
    answers = parse_answer_text(data.decode("utf-8", errors="replace"))
    if not answers:
        return JSONResponse({"ok": False, "error": "no_labeled_answers"}, status_code=400)
    merged = merge_profile(get_profile(user.id), answers)
    save_profile(user.id, merged)
    return JSONResponse({"ok": True, "saved_keys": sorted(answers.keys())})


@app.get("/checkout")
def checkout(request: Request) -> RedirectResponse:
    user = require_user(request)
    return RedirectResponse(url=checkout_url_for_user(user), status_code=303)


@app.get("/payment/success", response_class=HTMLResponse)
def payment_success(request: Request) -> HTMLResponse:
    user = current_user(request)
    body = """
    <section class="card narrow">
      <p class="eyebrow">Payment received</p>
      <h1>Thank you</h1>
      <p>Stripe will confirm the payment to Perfect PDF AI. Your completion credit appears automatically after the webhook is received.</p>
      <a class="button" href="/">Return to your workspace</a>
    </section>
    """
    return HTMLResponse(page_shell("Payment Received", body, request if user else None))


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    if not STRIPE_WEBHOOK_SECRET:
        return JSONResponse({"ok": False, "error": "webhook_not_configured"}, status_code=503)
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=400)

    if event.get("type") == "checkout.session.completed":
        session_object = event.get("data", {}).get("object", {})
        stripe_session_id = str(session_object.get("id", "")).strip()
        reference = str(session_object.get("client_reference_id", "")).strip()
        if stripe_session_id and reference.isdigit():
            user_id = int(reference)
            with db_session() as dbs:
                existing = dbs.get(PaymentRecord, stripe_session_id)
                user = dbs.get(User, user_id)
                if existing is None and user is not None:
                    credits = PAYMENT_CREDITS
                    user.credits += credits
                    dbs.add(
                        PaymentRecord(
                            stripe_session_id=stripe_session_id,
                            user_id=user_id,
                            amount_total=int(session_object.get("amount_total") or 0),
                            currency=str(session_object.get("currency") or ""),
                            credits_granted=credits,
                        )
                    )
    return JSONResponse({"ok": True})


@app.get("/submit_answers")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=303)
