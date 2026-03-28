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
	flake8 accounts adverts banking partners roles self_service user_profile vas waitlist web

fmt:
	black accounts adverts banking partners roles self_service user_profile vas waitlist web

purge:
	python3 manage.py flush --no-input

showcron:
	python3 manage.py crontab show

removecron:
	python manage.py crontab remove
