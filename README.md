# Picadailys — Backend API

[![CI](https://github.com/picadailystechhub/backend/actions/workflows/ci.yml/badge.svg)](https://github.com/picadailystechhub/backend/actions/workflows/ci.yml)

Django REST API powering the Picadailys mobile app (members, partners, advertisers, guests), the admin dashboard, the support dashboard and the marketing website.

## Quick start (Docker)

Requires Docker Desktop. No other setup or provider accounts needed.

```bash
git clone https://github.com/picadailystechhub/backend.git && cd backend
docker compose up --build          # web on http://localhost:8000, plus worker, PostGIS, Redis
```

API docs are then available at http://localhost:8000/v1/docs/ (Scalar), `/v1/swagger/` and `/v1/redoc/`.

Run the test suite:

```bash
make docker-test                   # = docker compose --profile test run --rm test
```

The test container reads only `.env.example` placeholders and an in-memory SpatiaLite database, so it never touches real data or calls live providers. To use real credentials for the dev server, `cp .env.example .env` and fill it in; compose layers `.env` over the placeholders.

## Project overview

| | |
|---|---|
| Framework | Django 5.2, Django REST Framework, drf-spectacular |
| Data | PostgreSQL + PostGIS, Redis (cache and Celery broker) |
| Background work | Celery worker/beat, django-crontab |
| Python | 3.12 |

**Mobile-facing apps:** `accounts`, `banking` (9PSB wallets, transfers, card funding), `vas` (airtime, data, bills), `treasury` (Anchor BaaS), `user_profile`, `gamification` (PicaPoints, streaks, referrals, UGC), `tasks` (AI-verified social/brand tasks), `adverts`, `partners`, `self_service`, `fmcg`, `event`, `flights`, `agents`, `ai_support`, `waitlist`, `blog`.

**Web-facing apps:** `roles` (admin dashboard), `support` (support dashboard), `web` (marketing website).

**Integrations:** 9PSB (banking, VAS), Anchor, VTPass, Dojah (KYC), Paystack (cards), YourNotify (SMS/email/WhatsApp), Firebase (push), FlightsLogic, Anthropic Claude, Cloudinary.

## Environment variables

Every variable the code reads is listed in [`.env.example`](.env.example) with a safe placeholder. Never commit `.env`.

## Local setup without Docker (macOS)

1. Install system libraries: `brew install gdal spatialite-tools postgis redis`
2. `python3.12 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.lock`
4. `cp .env.example .env`, then set `DATABASE_URL` and `REDIS_LOCATION` to your local services
5. `python manage.py migrate && python manage.py runserver`

## Running tests

```bash
pytest                             # or: make test
pytest --cov                       # with coverage
```

Tests live in each app's `tests.py`. Under test, settings switch to an in-memory SpatiaLite database with migrations disabled (`TESTING` in `picadailys/settings.py`), and external providers are mocked.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull request:

- **lint**: `make lint` (flake8)
- **test**: `manage.py check` and the full pytest suite with coverage
- **audit**: `pip-audit` against `requirements.lock`

## Dependencies

`requirements.txt` holds the direct dependencies; `requirements.lock` pins the full tree for reproducible installs. After editing either requirements file, run `make lock`. Dependabot opens weekly update PRs.

## API documentation

- `/v1/docs/`: Scalar (primary)
- `/v1/swagger/`: Swagger UI
- `/v1/redoc/`: ReDoc
- `/v1/schema/`: raw OpenAPI schema

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
