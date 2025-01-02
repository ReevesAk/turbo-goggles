from datetime import timedelta
from decouple import config as conf
import os
import sys
import dj_database_url
import cloudinary

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = conf("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "False") == "True"

DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "False") == "True"
ENVIRONMENT = conf("ENVIRONMENT")

if ENVIRONMENT == "development":
    ALLOWED_HOSTS = ["127.0.0.1", "localhost", "api.picadailys.com", "https://api.picadailys.com", "miniature-waddle.onrender.com"]
elif ENVIRONMENT == "production":
    ALLOWED_HOSTS = ["127.0.0.1", "localhost", "api.picadailys.com", " https://api.picadailys.com"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party External Packages.
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "cloudinary",
    "corsheaders",
    # Internal Project apps.
    "accounts",
    "adverts",
    "roles",
    "partners",
    "vas",
    "fmcg",
    "user_profile",
    "self_service",
    "banking",
    "support",
    "csp",
]

MIDDLEWARE = [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://167.71.174.242",
    "https://api.picadailys.com",
    "http://127.0.0.1:8000",
    "https://picadailys.com",
    "http://localhost:5174",
    "https://miniature-waddle.onrender.com",
    "https://admin-dashboard-jade-phi.vercel.app",
    "https://admin.picadailys.com"
]

ROOT_URLCONF = "picadailys.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "picadailys.wsgi.application"

DATABASES = {}
if ENVIRONMENT == "development":
    DEBUG = True
    database_url = conf("DATABASE_URL")
    DATABASES["default"] = dj_database_url.parse(database_url)
elif ENVIRONMENT == "production":
    DEBUG = False
    database_url = conf("DATABASE_URL")
    DATABASES["default"] = dj_database_url.parse(database_url)

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STORAGES = {
    'default': {
        'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# defining the custom user model.
AUTH_USER_MODEL = "accounts.User"

# Rest framework setting for drf spectacular configuration.
REST_FRAMEWORK = {
    "NON_FIELD_ERRORS_KEY": "errors",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

# CSP configuration.
CSP_DEFAULT_SRC = ("'self'",)  # Only allow resources from the same origin
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net")  # Allow external styles from Google Fonts
CSP_STYLE_SRC_ELEM = CSP_STYLE_SRC

CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "blob:",
    "http://localhost:5174",
    "https://api.picadailys.com/",
    "https://cdn.jsdelivr.net",
    "https://admin-dashboard-jade-phi.vercel.app",
    "https://admin.picadailys.com",
    "https://miniature-waddle.onrender.com/api/v1",
    "127.0.0.1:8000/api/v1",
)  # Allow external scripts
CSP_IMG_SRC = ("'self'", "data:", "https://res.cloudinary.com/dzsnvj9qr", "https://cdn.jsdelivr.net")  # Allow images from specified sources

# Enable HTTP Strict Transport Security (HSTS)
SECURE_HSTS_SECONDS = 31536000  # 1 year in seconds
SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Apply HSTS to all subdomains
SECURE_HSTS_PRELOAD = True  # Allow browsers to preload HSTS
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = ["https://api.picadailys.com"]

X_FRAME_OPTIONS = 'DENY'

# Prevent browsers from interpreting files as a different MIME type
SECURE_CONTENT_TYPE_NOSNIFF = True

# Set Referrer-Policy to control what information is sent in referrer headers
SECURE_REFERRER_POLICY = 'no-referrer-when-downgrade'

SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_LIFETIME": timedelta(days=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=4),
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # "Bearer <Token>"
    "AUDIENCE": "picadailys",
    "ISSUER": "https://api.picadailys.com/",
}

# Spectacular settings for Title and description of api documentation.
SPECTACULAR_SETTINGS = {
    "TITLE": "Picadailys API Documentation",
    "DESCRIPTION": "Picadailys is a digital and multi-faceted app aimed at providing "
    "online intermediary services, e.g" "```Value Added Servies(VAS)```",
    "```Self-Servives(SELF-SERV)```" "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": True,
    "USE_SESSION_AUTH": False,
    "SECURITY_DEFINITIONS": None,
    "DOC_EXPANSION": "none",
    "DEFAULT_MODEL_RENDERING": "example",
    "DEFAULT_MODEL_DEPTH": 1,
}

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(PROJECT_ROOT, "static")

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

cloudinary.config(
    cloud_name=conf("CLOUDINARY_CLOUD_NAME"),
    api_key=conf("CLOUDINARY_API_KEY"),
    api_secret=conf("CLOUDINARY_API_SECRET"),
)

TESTING = 'test' in sys.argv[1:]
if TESTING:
    print('=========================')
    print('In TEST Mode - Disabling Migrations')
    print('=========================')

    class DisableMigrations(object):

        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = DisableMigrations()


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # Formatters
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },

    # Handlers
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/picadailys_server.log'),
            'formatter': 'verbose',
        },
    },

    # Loggers for each app
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'accounts': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'adverts': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'banking': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'fmcg': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'partners': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'roles': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'self_service': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'support': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'user_profile': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'vas': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

if DEBUG is False:
    LOGGING['handlers']['file'] = {
        'level': 'INFO',
        'class': 'logging.NullHandler',
    }
