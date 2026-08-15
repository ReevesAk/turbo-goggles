# settings_test.py
from picadailys.settings import *

# Override for testing - use local PostgreSQL with PostGIS
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "test_picadailys",
        "USER": "postgres",
        "PASSWORD": "postgres",  # Add the password
        "HOST": "localhost",
        "PORT": "5432",
    }
}


# Keep migration disabling for faster tests
class DisableMigrations(object):
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Speed up test runs
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable throttling for tests
REST_FRAMEWORK = REST_FRAMEWORK.copy()
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "user": "10000/hour",
    "anon": "10000/hour",
}
