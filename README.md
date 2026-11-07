# Perfect PDF AI

Perfect PDF AI is a FastAPI web app that turns uploaded forms into completed PDFs while keeping each user's reusable answers and document history private to their account.

## Product flow

1. A user creates an account and uploads a PDF, DOCX, TXT, MD, or CSV form.
2. The local document-intelligence engine detects fillable PDF widgets, printed field/question labels, and image-only scanned pages through local OCR.
3. Saved answers are semantically matched to the new form so the user does not have to retype the same information.
4. The user confirms or corrects the proposed answers.
5. Perfect PDF AI fills true PDF form fields where possible, overlays answers beside printed labels, and appends a completion summary.
6. The completed PDF is encrypted before database storage and remains available in the user's history.
7. Optional Stripe Payment Link + webhook integration grants completion credits after verified checkout completion events.

The core form-mapping engine runs locally in the application and does not require a paid AI API. Image-only scans are OCR'd with the open-source Tesseract engine bundled in the production Docker image.

## Security model

- PBKDF2-SHA256 password hashing with per-password salts.
- Random session tokens; only SHA-256 session-token hashes are stored in the database.
- HttpOnly, SameSite=Strict cookies; Secure cookies are enabled in production.
- CSRF protection on authenticated browser forms.
- Source documents, completed PDFs, answer profiles, and mapping data are encrypted with a key derived from APP_SECRET_KEY.
- Every document query is scoped to its owning user.
- File size, extension, and basic PDF/DOCX signature validation are enforced.
- Security headers are applied to every response.
- Failed logins are throttled by account identifier and document-analysis requests are throttled per authenticated user.
- Production fails closed: customer routes return HTTP 503 until secure encryption configuration, durable PostgreSQL, OCR runtime, and any required payment configuration are ready.

APP_SECRET_KEY must remain stable. Changing it makes previously encrypted documents unreadable.

## Persistence

The app uses SQLAlchemy.

- If DATABASE_URL is set to PostgreSQL, Postgres is used.
- Without it, local development uses SQLite at data/perfect_pdf_ai.sqlite3.
- Uploaded documents are stored as encrypted database blobs, so production does not depend on Render's ephemeral filesystem.
- Production history is only durable when `DATABASE_URL` points to durable PostgreSQL. Render Free Postgres expires after 30 days, so it is not treated as permanent production storage.

## Local run

The production-equivalent path is Docker because OCR requires the Tesseract system package:

\`\`\`bash
docker build -t perfect-pdf-ai .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e APP_SECRET_KEY="replace-with-a-long-random-secret" \
  perfect-pdf-ai
\`\`\`

Open http://localhost:8000.

For a non-Docker developer environment, install Tesseract plus the Python requirements before starting Uvicorn.

## Tests

\`\`\`bash
pytest -q
\`\`\`

GitHub Actions installs Tesseract, compiles app.py, runs the full suite including a real image-only OCR test, audits Python dependencies, builds the production Docker image, and reruns the tests inside that image.

## Render

render.yaml defines a free Docker web service. The image installs Tesseract explicitly, making the OCR runtime reproducible. `DATABASE_URL` must still be supplied from a durable PostgreSQL provider:

\`\`\`yaml
runtime: docker
dockerfilePath: ./Dockerfile
healthCheckPath: /health
\`\`\`

The production service should run with:

\`\`\`text
ENVIRONMENT=production
COOKIE_SECURE=true
APP_SECRET_KEY=<stable secret>
DATABASE_URL=<durable PostgreSQL connection string>
OCR_ENABLED=true
OCR_LANGUAGE=eng
OCR_PSM=11
OCR_TIMEOUT_SECONDS=20
OCR_TOTAL_TIMEOUT_SECONDS=90
\`\`\`

## Stripe monetization

Perfect PDF AI uses completion credits. Upload and analysis can remain available while completion is gated.

Required production variables:

\`\`\`text
STRIPE_REQUIRE_PAYMENT=true
STRIPE_PAYMENT_LINK=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_ID=plink_...
STRIPE_WEBHOOK_SECRET=whsec_...
PAYMENT_CREDITS=1
FREE_COMPLETIONS=1
\`\`\`

/checkout adds the logged-in user ID as Stripe's client_reference_id. Configure the Stripe Payment Link to return customers to:

\`\`\`text
https://YOUR-DOMAIN/payment/success
\`\`\`

Configure a Stripe webhook for:

\`\`\`text
POST https://YOUR-DOMAIN/stripe/webhook
events: checkout.session.completed, checkout.session.async_payment_succeeded
\`\`\`

Only a webhook event with a valid Stripe signature, the configured Payment Link ID, and `payment_status=paid` grants credits. Repeated delivery of the same Stripe Checkout Session is idempotent.

Keep STRIPE_REQUIRE_PAYMENT=false until the Payment Link and webhook secret are configured.

## Main routes

\`\`\`text
GET  /health
GET  /config
GET  /
GET  /register
POST /register
GET  /login
POST /login
POST /logout
POST /upload
GET  /documents/{id}
POST /documents/{id}/complete
GET  /documents/{id}/source
GET  /documents/{id}/download
POST /submit-answers
POST /api/upload
POST /api/submit-answers
GET  /checkout
GET  /payment/success
POST /stripe/webhook
\`\`\`

## Current implementation boundary

The built-in intelligence is a local semantic/fuzzy mapping engine plus Tesseract OCR for image-only scanned pages. It does not call an external LLM and therefore has no per-document AI API cost. Handwriting and unusually complex layouts can still require manual correction, which is why detected answers are always presented for confirmation before generation. OCR work is bounded by per-page and per-document time budgets so a pathological scan cannot monopolize the web worker.
