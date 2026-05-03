from fastapi.testclient import TestClient

from app import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "perfect-pdf-ai"


def test_config_endpoint():
    response = client.get("/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["max_upload_bytes"] == MAX_UPLOAD_BYTES
    assert payload["allowed_extensions"] == sorted(ALLOWED_EXTENSIONS)


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Perfect PDF AI" in response.text
    assert "Upload and Read" in response.text


def test_text_upload_api_returns_extracted_text():
    content = b"Question 1: What is your name?"
    response = client.post(
        "/api/upload",
        files={"file": ("test.txt", content, "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["file_name"] == "test.txt"
    assert "Question 1" in payload["text"]


def test_markdown_upload_api_returns_extracted_text():
    response = client.post(
        "/api/upload",
        files={"file": ("questions.md", b"# Questions", "text/markdown")},
    )
    assert response.status_code == 200
    assert "Questions" in response.json()["text"]


def test_rejects_unsupported_document_type():
    response = client.post(
        "/api/upload",
        files={"file": ("bad.exe", b"not allowed", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_rejects_empty_upload():
    response = client.post(
        "/api/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file was empty."


def test_answer_upload_api_saves_any_file_type():
    response = client.post(
        "/api/submit-answers",
        files={"file": ("answers.any", b"Answer 1: Derek", "application/octet-stream")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["file_name"] == "answers.any"
