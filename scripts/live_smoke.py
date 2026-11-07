import os
import re
import secrets
import sys
import time

import fitz
import httpx


BASE_URL = os.environ["SMOKE_BASE_URL"].rstrip("/")
RUN_ID = os.environ.get("GITHUB_RUN_ID", str(int(time.time())))
EMAIL = f"smoke+{RUN_ID}-{secrets.token_hex(4)}@example.com"
PASSWORD = f"Smoke-{secrets.token_urlsafe(24)}!A9"


def expect(response: httpx.Response, status: int, label: str) -> None:
    if response.status_code != status:
        raise AssertionError(
            f"{label}: expected HTTP {status}, got {response.status_code}: "
            f"{response.text[:500]}"
        )


def extract_csrf(html_text: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html_text)
    if not match:
        raise AssertionError("CSRF token was not present in authenticated page.")
    return match.group(1)


def make_scanned_pdf() -> bytes:
    source = fitz.open()
    source_page = source.new_page(width=612, height=792)
    source_page.insert_text((72, 90), "Perfect PDF AI Live Smoke Application", fontsize=16)
    source_page.insert_text((72, 145), "Full Name: __________________________", fontsize=14)
    source_page.insert_text((72, 195), "Email: ______________________________", fontsize=14)
    pix = source_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    source.close()

    scanned = fitz.open()
    page = scanned.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    data = scanned.tobytes()
    scanned.close()
    return data


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=120.0, follow_redirects=False) as client:
        health = client.get("/health")
        expect(health, 200, "health")
        health_data = health.json()
        assert health_data["ok"] is True
        assert health_data["version"] == "2.1.0"
        assert health_data["ocr_enabled"] is True
        assert health_data["ocr_engine"] == "tesseract"
        assert health_data["ocr_available"] is True

        root = client.get("/")
        expect(root, 200, "root")
        assert "Perfect PDF AI" in root.text

        expect(client.get("/privacy"), 200, "privacy")
        expect(client.get("/terms"), 200, "terms")

        registered = False
        try:
            register = client.post(
                "/register",
                data={"email": EMAIL, "password": PASSWORD},
            )
            expect(register, 303, "register")
            registered = True

            home = client.get("/")
            expect(home, 200, "authenticated home")
            csrf = extract_csrf(home.text)

            upload = client.post(
                "/upload",
                data={"csrf": csrf},
                files={
                    "file": (
                        "live-scanned-application.pdf",
                        make_scanned_pdf(),
                        "application/pdf",
                    )
                },
            )
            expect(upload, 303, "scanned PDF upload")
            location = upload.headers.get("location", "")
            assert location.startswith("/documents/"), location

            detail = client.get(location)
            expect(detail, 200, "document detail")
            assert "OCR used on" in detail.text
            assert "Full Name" in detail.text
            assert "Email" in detail.text
            csrf = extract_csrf(detail.text)

            complete = client.post(
                f"{location}/complete",
                data={
                    "csrf": csrf,
                    "answers_text": (
                        "Full Name: Perfect PDF Smoke User\n"
                        f"Email: {EMAIL}\n"
                    ),
                },
            )
            expect(complete, 303, "completed PDF generation")

            download = client.get(f"{location}/download")
            expect(download, 200, "completed PDF download")
            assert download.headers["content-type"].startswith("application/pdf")

            completed = fitz.open(stream=download.content, filetype="pdf")
            completed_text = "\n".join(page.get_text("text") for page in completed)
            completed.close()
            assert "Perfect PDF Smoke User" in completed_text
            assert EMAIL in completed_text

            account = client.get("/account")
            expect(account, 200, "account page")
            csrf = extract_csrf(account.text)
            deleted = client.post(
                "/account/delete",
                data={"csrf": csrf, "password": PASSWORD},
            )
            expect(deleted, 303, "account deletion")
            registered = False

            expect(client.get("/account"), 401, "deleted account session")
        finally:
            if registered:
                account = client.get("/account")
                if account.status_code == 200:
                    csrf = extract_csrf(account.text)
                    client.post(
                        "/account/delete",
                        data={"csrf": csrf, "password": PASSWORD},
                    )

    print("LIVE_SMOKE_OK", BASE_URL)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"LIVE_SMOKE_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
