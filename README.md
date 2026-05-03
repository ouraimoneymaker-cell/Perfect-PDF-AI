# Perfect PDF AI

Perfect PDF AI is a deployable web app for uploading documents, reading extracted text, and submitting a separate answers file.

## What it does

- Upload PDF, TXT, MD, CSV, or DOCX files.
- Extract readable PDF text with PyMuPDF.
- Display document text in a clean browser reader.
- Upload a separate answers file after reading.
- Provide API endpoints for upload and answer intake.
- Include optional Stripe payment-link gating through environment variables.
- Deploy cleanly on Render.
- Run automated smoke tests with GitHub Actions.

## Main files

```text
app.py
static/styles.css
static/app.js
tests/test_app.py
requirements.txt
render.yaml
.github/workflows/tests.yml
uploads/.gitkeep
uploads/answers/.gitkeep
```

## Local run

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## Test

```bash
pytest -q
```

## Render deployment

Render uses `render.yaml`:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
```

## Optional Stripe monetization

Set these environment variables in Render:

```text
STRIPE_PAYMENT_LINK=https://buy.stripe.com/your-payment-link
STRIPE_REQUIRE_PAYMENT=true
```

When `STRIPE_REQUIRE_PAYMENT=true`, uploads are blocked until the user follows the configured Stripe payment link. Set it to `false` while testing free uploads.

## Environment variables

```text
APP_NAME=Perfect PDF AI
MAX_UPLOAD_BYTES=26214400
STRIPE_PAYMENT_LINK=
STRIPE_REQUIRE_PAYMENT=false
```

## API endpoints

```text
GET  /health
GET  /config
GET  /
GET  /checkout
POST /upload
POST /api/upload
POST /submit-answers
POST /api/submit-answers
```
