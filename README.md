# Perfect PDF AI

Perfect PDF AI is a FastAPI web app that turns uploaded forms into completed PDFs while keeping each user's reusable answers and document history private to their account.

## Product flow

1. A user creates an account and uploads a PDF, DOCX, TXT, MD, or CSV form.
2. The local document-intelligence engine detects fillable PDF widgets and printed field/question labels.
3. Saved answers are semantically matched to the new form so the user does not have to retype the same information.
4. The user confirms or corrects the proposed answers.
5. Perfect PDF AI fills true PDF form fields where possible, overlays answers beside printed labels, and appends a completion summary.
6. The completed PDF is encrypted before database storage and remains available in the user's history.
7. Optional Stripe Payment Link + webhook integration grants completion credits after verified checkout completion events.

The core form-mapping engine runs locally in the application and does not require a paid AI API.

## Security model

- PBKDF2-SHA256 password hashing with per-password salts.
- Random session tokens; only SHA-256 session-token hashes are stored in the database.
- HttpOnly, SameSite=Strict cookies; Secure cookies are enabled in production.
- CSRF protection on authenticated browser forms.
- Source documents, completed PDFs, answer profiles, and mapping data are encrypted with a key derived from APP_SECRET_KEY.
- Every document query is scoped to its owning user.
- File size, extension, and basic PDF/DOCX signature validation are enforced.
- Security headers are applied to every response.

APP_SECRET_KEY must remain stable. Changing it makes previously encrypted documents unreadable.

## Persistence

The app uses SQLAlchemy.

- If DATABASE_URL is set to PostgreSQL, Postgres is used.
- Without it, local development uses SQLite at data/perfect_pdf_ai.sqlite3.
- Uploaded documents are stored as encrypted database blobs, so production does not depend on Render's ephemeral filesystem.

## Local run

\`\`\`bash
pip install -r requirements.txt
export APP_SECRET_KEY="replace-with-a-long-random-secret"
uvicorn app:app --host 0.0.0.0 --port 8000
\`\`\`

Open http://localhost:8000.

## Tests

\`\`\`bash
pytest -q
\`\`\`

GitHub Actions also compiles app.py before running the suite.

## Render

render.yaml defines a free Python web service plus free Render Postgres:

\`\`\`yaml
startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
\`\`\`

The production service should run with:

\`\`\`text
ENVIRONMENT=production
COOKIE_SECURE=true
APP_SECRET_KEY=<stable secret>
DATABASE_URL=<Render Postgres internal connection string>
\`\`\`

## Stripe monetization

Perfect PDF AI uses completion credits. Upload and analysis can remain available while completion is gated.

Required production variables:

\`\`\`text
STRIPE_REQUIRE_PAYMENT=true
STRIPE_PAYMENT_LINK=https://buy.stripe.com/...
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
event: checkout.session.completed
\`\`\`

Only a webhook event with a valid Stripe signature grants credits. Repeated delivery of the same Stripe Checkout Session is idempotent.

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

The built-in intelligence is a local semantic/fuzzy mapping engine designed for common application labels and PDF fields. It does not call an external LLM and therefore has no per-document AI API cost. Complex handwriting, scanned-image OCR, and forms whose questions are only present as images are outside the current zero-cost processing path.
