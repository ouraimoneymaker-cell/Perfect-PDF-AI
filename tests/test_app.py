import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TEST_DB = Path("/tmp/perfect_pdf_ai_test.sqlite3")
TEST_DB.unlink(missing_ok=True)

os.environ["ENVIRONMENT"] = "test"
os.environ["COOKIE_SECURE"] = "false"
os.environ["APP_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-tests-123456789"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["STRIPE_REQUIRE_PAYMENT"] = "false"
os.environ["STRIPE_PAYMENT_LINK"] = "https://buy.stripe.com/test_perfect_pdf_ai"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_perfect_pdf_ai_test"
os.environ["FREE_COMPLETIONS"] = "1"
os.environ["PAYMENT_CREDITS"] = "1"

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app as app_module
from app import (
    AuthSession,
    Base,
    PAYMENT_CREDITS,
    SESSION_COOKIE,
    User,
    app,
    csrf_for_token,
    db_session,
    engine,
    map_answers,
)


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(app_module, "STRIPE_REQUIRE_PAYMENT", False)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str = "user@example.com", password: str = "password123"):
    response = client.post(
        "/register",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.cookies.get(SESSION_COOKIE)
    return response


def csrf(client: TestClient) -> str:
    token = client.cookies.get(SESSION_COOKIE)
    assert token
    return csrf_for_token(token)


def sample_pdf(label: str = "Full Name:") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 88), "Application Form", fontsize=16)
    page.insert_text((72, 130), f"{label} __________________________", fontsize=11)
    page.insert_text((72, 165), "Email: ______________________________", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def upload_pdf(client: TestClient, filename: str = "application.pdf", label: str = "Full Name:") -> str:
    response = client.post(
        "/upload",
        data={"csrf": csrf(client)},
        files={"file": (filename, sample_pdf(label), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/documents/")
    return location.rsplit("/", 1)[-1]


def detected_labels(document_id: str, user_id: int) -> list[str]:
    record = app_module.get_document_for_user(document_id, user_id)
    analysis = app_module.decrypt_json(record.analysis_blob)
    return [field["label"] for field in analysis["fields"]]


def test_health_and_config(client):
    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["ok"] is True
    assert payload["service"] == "perfect-pdf-ai"
    assert payload["version"] == "2.0.0"

    config = client.get("/config")
    assert config.status_code == 200
    assert ".pdf" in config.json()["allowed_extensions"]


def test_registration_login_and_secure_session_hash(client):
    register(client)
    raw_cookie = client.cookies.get(SESSION_COOKIE)
    assert raw_cookie

    with db_session() as session:
        stored = session.scalars(select(AuthSession)).one()
        assert stored.token_hash != raw_cookie
        assert stored.token_hash == hashlib.sha256(raw_cookie.encode()).hexdigest()

    logout = client.post("/logout", data={"csrf": csrf(client)}, follow_redirects=False)
    assert logout.status_code == 303

    login = client.post(
        "/login",
        data={"email": "user@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_smart_mapping_matches_semantic_labels():
    fields = [
        {"id": "f1", "label": "Applicant Full Name"},
        {"id": "f2", "label": "Mailing Address"},
        {"id": "f3", "label": "Telephone Number"},
    ]
    answers = {
        "full_name": "Jane Smith",
        "address": "123 Main Street",
        "phone": "617-555-0100",
    }
    mapped = map_answers(fields, answers)
    assert mapped["f1"]["value"] == "Jane Smith"
    assert mapped["f2"]["value"] == "123 Main Street"
    assert mapped["f3"]["value"] == "617-555-0100"


def test_pdf_upload_detects_fields_and_generates_completed_pdf(client):
    register(client)
    document_id = upload_pdf(client)

    detail = client.get(f"/documents/{document_id}")
    assert detail.status_code == 200
    assert "Full Name" in detail.text
    assert "Email" in detail.text

    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        assert user is not None
        labels = detected_labels(document_id, user.id)

    full_name_label = next(label for label in labels if "Full Name" in label)
    email_label = next(label for label in labels if "Email" in label)

    completed = client.post(
        f"/documents/{document_id}/complete",
        data={
            "csrf": csrf(client),
            "field_0_label": full_name_label,
            "field_0_answer": "Jane Smith",
            "field_1_label": email_label,
            "field_1_answer": "jane@example.com",
            "answers_text": "",
        },
        follow_redirects=False,
    )
    assert completed.status_code == 303

    download = client.get(f"/documents/{document_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")

    doc = fitz.open(stream=download.content, filetype="pdf")
    extracted = "\n".join(page.get_text("text") for page in doc)
    doc.close()
    assert "Jane Smith" in extracted
    assert "jane@example.com" in extracted

    home = client.get("/")
    assert "application.pdf" in home.text
    assert "Completed" in home.text


def test_saved_answers_reuse_on_new_form(client):
    register(client)
    first_id = upload_pdf(client, filename="first.pdf", label="Full Name:")

    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        labels = detected_labels(first_id, user.id)
    name_label = next(label for label in labels if "Full Name" in label)

    response = client.post(
        f"/documents/{first_id}/complete",
        data={
            "csrf": csrf(client),
            "field_0_label": name_label,
            "field_0_answer": "Jane Smith",
            "answers_text": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    second_id = upload_pdf(client, filename="second.pdf", label="Applicant Name:")
    detail = client.get(f"/documents/{second_id}")
    assert detail.status_code == 200
    assert 'value="Jane Smith"' in detail.text


def test_document_access_is_owner_scoped(client):
    register(client, "owner@example.com")
    document_id = upload_pdf(client)

    other = TestClient(app)
    register(other, "other@example.com")
    forbidden = other.get(f"/documents/{document_id}")
    assert forbidden.status_code == 404
    other.close()


def test_rejects_fake_pdf_and_unsupported_extension(client):
    register(client)
    fake = client.post(
        "/upload",
        data={"csrf": csrf(client)},
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert fake.status_code == 415

    bad = client.post(
        "/upload",
        data={"csrf": csrf(client)},
        files={"file": ("bad.exe", b"MZ", "application/octet-stream")},
    )
    assert bad.status_code == 415


def test_answer_import_updates_reusable_profile(client):
    register(client)
    response = client.post(
        "/submit-answers",
        data={"csrf": csrf(client)},
        files={
            "file": (
                "answers.txt",
                b"Full Name: Jane Smith\nPhone: 617-555-0100\n",
                "text/plain",
            )
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        assert user is not None
        user_id = user.id
    profile = app_module.get_profile(user_id)
    assert profile["full_name"] == "Jane Smith"
    assert profile["phone"] == "617-555-0100"


def test_payment_gate_consumes_credit_then_blocks_next_completion(client, monkeypatch):
    monkeypatch.setattr(app_module, "STRIPE_REQUIRE_PAYMENT", True)
    register(client)
    first_id = upload_pdf(client, filename="paid-one.pdf")

    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        labels = detected_labels(first_id, user.id)
    name_label = next(label for label in labels if "Full Name" in label)

    first = client.post(
        f"/documents/{first_id}/complete",
        data={
            "csrf": csrf(client),
            "field_0_label": name_label,
            "field_0_answer": "Jane Smith",
            "answers_text": "",
        },
        follow_redirects=False,
    )
    assert first.status_code == 303

    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        assert user.credits == 0

    second_id = upload_pdf(client, filename="paid-two.pdf")
    second = client.post(
        f"/documents/{second_id}/complete",
        data={
            "csrf": csrf(client),
            "field_0_label": "Full Name",
            "field_0_answer": "Jane Smith",
            "answers_text": "",
        },
        follow_redirects=False,
    )
    assert second.status_code == 402
    assert "completion credit" in second.text.lower()


def test_checkout_carries_user_reference(client):
    register(client)
    response = client.get("/checkout", follow_redirects=False)
    assert response.status_code == 303
    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert query["client_reference_id"][0].isdigit()
    assert query["prefilled_email"][0] == "user@example.com"


def test_stripe_webhook_grants_credit_idempotently(client):
    register(client)
    with db_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))
        user_id = user.id
        starting_credits = user.credits

    event = {
        "id": "evt_test_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_perfect_pdf_ai_1",
                "object": "checkout.session",
                "client_reference_id": str(user_id),
                "amount_total": 999,
                "currency": "usd",
            }
        },
    }
    payload = json.dumps(event, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signed = f"{timestamp}.".encode() + payload
    signature = hmac.new(
        os.environ["STRIPE_WEBHOOK_SECRET"].encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()
    header = f"t={timestamp},v1={signature}"

    first = client.post(
        "/stripe/webhook",
        content=payload,
        headers={"stripe-signature": header, "content-type": "application/json"},
    )
    assert first.status_code == 200

    second = client.post(
        "/stripe/webhook",
        content=payload,
        headers={"stripe-signature": header, "content-type": "application/json"},
    )
    assert second.status_code == 200

    with db_session() as session:
        user = session.get(User, user_id)
        assert user.credits == starting_credits + PAYMENT_CREDITS


def test_api_requires_login_and_returns_analysis(client):
    unauth = client.post(
        "/api/upload",
        files={"file": ("test.pdf", sample_pdf(), "application/pdf")},
    )
    assert unauth.status_code == 401

    register(client)
    auth = client.post(
        "/api/upload",
        files={"file": ("test.pdf", sample_pdf(), "application/pdf")},
    )
    assert auth.status_code == 200
    payload = auth.json()
    assert payload["ok"] is True
    assert payload["field_count"] >= 2
    assert payload["document_id"]
