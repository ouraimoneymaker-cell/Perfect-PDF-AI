from pathlib import Path

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Perfect PDF AI" in response.text
    assert "Upload and Read" in response.text


def test_text_upload_api_returns_extracted_text(tmp_path):
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


def test_answer_upload_api_saves_file():
    response = client.post(
        "/api/submit-answers",
        files={"file": ("answers.txt", b"Answer 1: Derek", "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["file_name"] == "answers.txt"
