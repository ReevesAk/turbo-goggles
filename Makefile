# Build all services
run:
	python3 manage.py runserver

# Run django makemigrations.
migrations:
	python3 manage.py makemigrations

# Run django migrate.
migrate:
	python3 manage.py migrate

lint:
	flake8 accounts ai_support adverts banking blog flights gamification partners roles self_service support tasks treasury user_profile vas waitlist web

fmt:
	black accounts ai_support adverts banking blog flights gamification partners roles self_service support tasks treasury user_profile vas waitlist web

purge:
	python3 manage.py flush --no-input

showcron:
	python3 manage.py crontab show

removecron:
	python manage.py crontab remove

test:
	python -m pytest -v

test-app:
	python -m pytest $(app)/tests.py -v

# Full local stack (web, worker, postgis, redis).
up:
	docker compose up --build

# Run the test suite in an isolated container (placeholder env only).
docker-test:
	docker compose --profile test run --rm test

# Regenerate the pinned lockfile after editing requirements*.txt.
lock:
	uv pip compile requirements.txt requirements-test.txt -o requirements.lock --python-version 3.12
