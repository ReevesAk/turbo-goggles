<!-- ...existing code... -->

# Picadailys — Banking API

## Project overview
Picadailys is a Django-based microservices-style platform powering fintech and value-added services. This repository contains the Banking service — a Django REST Framework (DRF) API that handles wallet management, KYC, transfers, card payments, transactions, FX quotes, and webhooks. The project integrates multiple third-party providers (Cloudinary, Paystack, Twilio, NextBee, VTpass, etc.) and uses Redis for caching and background needs.

## Architecture & components
- Django + Django REST Framework for APIs
- PostgreSQL as primary datastore (DATABASE_URL)
- Redis for caching/job coordination
- Cloudinary for media storage
- drf-spectacular for OpenAPI schema + Swagger/Redoc
- Modular apps: accounts, banking, transfers, fx, gamification, vas, fmcg, partners, roles, support
- Webhooks endpoints for payment provider callbacks
- AES and JWT-based encryption/auth patterns

## Key features
- KYC verification (BVN & NIN)
- Tiered wallet lifecycle (create, upgrade to tier2/tier3)
- Wallet PIN management (set, reset, OTP flows)
- Intra- and inter-bank transfers
- Card funding flows and refunds
- Transaction listing and retrieval
- FX quotation endpoint
- Webhook handlers for inflows and card payments
- Notifications & push integrations (Pusher, Twilio)
- Role-based permissions and granular access control

## Repository layout (important files & folders)
- banking/ — banking app (views, urls, transfers, fx, tx, webhooks)
- accounts/ — user management and authentication
- config/ or project root settings — global Django settings and SPECTACULAR_SETTINGS
- requirements.txt — Python dependencies
- .env — environment variables (sensitive; DO NOT commit)
- README.md — this file

## Environment variables (example)
DO NOT commit real secrets. Add a local `.env` with required variables. Examples (non-exhaustive):
- SECRET_KEY
- DEBUG
- DATABASE_URL
- REDIS_LOCATION
- CLOUDINARY_* (CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)
- PAYSTACK_SECRET_KEY
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
- PUSHER_APP_*  
Refer to `.env.example` (create one) for the full list.

## Requirements & setup (macOS)
1. Create and activate venv:
   - python3 -m venv .venv
   - source .venv/bin/activate
2. Install:
   - pip install -r requirements.txt
3. Create `.env` (copy from `.env.example`) and populate secrets.
4. Migrate and collect static:
   - python manage.py migrate
   - python manage.py collectstatic --noinput
5. Run dev server:
   - python manage.py runserver 0.0.0.0:8000

## Running tests
- python manage.py test
- Use Django test tags and DRF APITestCase for endpoint coverage.
- CI should run tests with a test database and mock external providers.

## API documentation
Use drf-spectacular to publish OpenAPI schema and interactive UIs.

Recommended URLs to add under the banking (or global) urls:
- /api/schema/  (SpectacularAPIView)
- /api/docs/    (SpectacularSwaggerView)
- /api/redoc/   (SpectacularRedocView)

Example SPECTACULAR_SETTINGS (settings.py):
- TITLE, DESCRIPTION, VERSION, TAGS, COMPONENT_SPLIT_REQUEST

Document each view with @extend_schema for clear request/response examples and tags.

## Authentication & security
- JWT (rest_framework_simplejwt) for authenticated endpoints
- Webhook endpoints should be unauthenticated but must validate signatures
- Enforce HTTPS in production; enable HSTS
- Rotate secrets and do not check `.env` into VCS
- Use AES_KEY/AES_IV only in secure contexts; store in secret manager for production

## Error handling & conventions
- Use standardized error codes (e.g., WAL001, TRF001, KYC001)
- Consistent JSON response structure:
  - success: bool
  - data: object | null
  - error: { code: string, message: string } | null
- Return appropriate HTTP status codes for client vs server errors

## Rate limiting & throttling
- Apply DRF throttling classes for endpoint categories:
  - Standard endpoints: e.g., 100/min
  - Webhooks: higher limit (e.g., 1000/min)
- Consider per-user and per-ip limits

## Logging & observability
- Structured JSON logs for critical flows (payments, refunds, transfers)
- Capture correlation IDs for cross-service tracing (X-Request-ID)
- Metrics: request latency, error rate, success/failure rates for provider calls
- Integrate Sentry (or similar) for exceptions

## Deployment notes
- Build image with pinned dependencies
- Use environment variables and secret manager (AWS Secrets Manager, Render secrets)
- Run database migrations as part of deployment pipeline
- Use managed Postgres + Redis for production
- Ensure webhook endpoints are reachable over HTTPS with valid TLS certs

## Development tips
- Mock external provider calls during local development (VCR, responses, or custom mocks)
- Use fixtures and factory_boy for test data
- Add more unit and integration tests around monetary flows and edge cases

## Contribution & support
- Follow repository linting and formatting rules (black, isort, flake8)
- Add tests for every feature or bugfix
- For security incidents, do not disclose secrets — rotate compromised keys immediately

## Contact
For API usage questions or integrations, reach out to the maintainers listed in the project metadata or open an issue/pr in this repository.
