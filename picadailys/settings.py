from datetime import timedelta
from decouple import config as conf
import os
import sys
import dj_database_url
import cloudinary
from csp.constants import NONCE

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = conf("SECRET_KEY")
REDIS_LOCATION = conf("REDIS_LOCATION")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "False") == "True"

DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "False") == "True"
ENVIRONMENT = conf("ENVIRONMENT")

if ENVIRONMENT == "development":
    ALLOWED_HOSTS = ["*"]
elif ENVIRONMENT == "production":
    ALLOWED_HOSTS = [
        "127.0.0.1",
        "localhost",
        "api.picadailys.com",
        "miniature-waddle.onrender.com",
        "picadailysbackend.onrender.com",
        "167.71.174.242",
        "https://api.picadailys.com",
        "https://miniature-waddle-k5bz.onrender.com",
        "https://picadailysbackend.onrender.com",
        "https://web-y9g2.onrender.com",
        "https://support-y8lr.onrender.com",
        "https://support.picadailys.com",
        "https://admin-dashboard-9juk.onrender.com",
    ]


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
    "django_crontab",
    # Internal Project apps.
    "accounts",
    "adverts",
    "roles.apps.RolesConfig",
    "partners",
    "vas",
    "fmcg",
    "user_profile",
    "self_service",
    "banking",
    "support",
    "gamification",
    "web",
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
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://167.71.174.242",
    "https://api.picadailys.com",
    "http://127.0.0.1:8000",
    "https://picadailys.com",
    "https://web-y9g2.onrender.com",
    "https://admin-dashboard-9juk.onrender.com",
    "https://support-y8lr.onrender.com",
    "https://picadailys-admin.netlify.app",
    "https://picadailys-landing.vercel.app",
    "https://miniature-waddle-k5bz.onrender.com",
    "https://admin-dashboard-jade-phi.vercel.app",
    "https://admin.picadailys.com",
    "https://support.picadailys.com",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "idempotency-key",
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
                "django.template.context_processors.csp",
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

TIME_ZONE = "Africa/Lagos"

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
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],

    "DEFAULT_THROTTLE_RATES": {
        "user": "700/hour",
        "anon": "700/hour",
        "low_usage": "10/hour",
        "high_usage": "500/hour",

        # Custom per-endpoint scopes
        "otp": "5/minute",
        "otp_request": "3/minute",
        "login": "5/minute",
        "wallet_transfer": "10/hour",
        "pin_change": "5/hour",
        "password_change": "5/hour"
    },
}

# Use django-csp v4 configuration format (new style)
CONTENT_SECURITY_POLICY = {
    # Exclude the interactive docs endpoints because ReDoc/Swagger inject
    # styles at runtime (CSSOM/insertRule) which some CSP directives block.
    # Excluding them keeps CSP protection for the rest of the app while
    # allowing the docs to render normally.
    "EXCLUDE_URL_PREFIXES": [
        "/v1/docs/",
        "/v1/redoc/",
    ],
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "blob:",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
            "https://cdnjs.cloudflare.com",
            NONCE,
        ],
        "style-src": [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://fonts.googleapis.com",
            "'sha256-MMpT0iDxyjALd9PdfepImGX3DBfJPXZ4IlDWdPAgtn0='",
            NONCE,
        ],
        "style-src-elem": [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://fonts.googleapis.com",
            "'sha256-MMpT0iDxyjALd9PdfepImGX3DBfJPXZ4IlDWdPAgtn0='",
            NONCE,
        ],
        "img-src": [
            "'self'",
            "data:",
            "https://res.cloudinary.com/dzsnvj9qr",
            "https://cdn.jsdelivr.net",
        ],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "connect-src": [
            "'self'",
            "ws://localhost:5174",
            "http://localhost:8000",
            "https://api.picadailys.com/",
        ],
    }
}
CONTENT_SECURITY_POLICY_REPORT_ONLY = False




# Enable HTTP Strict Transport Security (HSTS)
if conf("ENVIRONMENT") == "production":
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year in seconds
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Apply HSTS to all subdomains
    SECURE_HSTS_PRELOAD = True  # Allow browsers to preload HSTS

else:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    "https://api.picadailys.com",
    "http://localhost:5173",
    "http://localhost:5174",
    "https://miniature-waddle-k5bz.onrender.com",
    "https://web-y9g2.onrender.com",
    "https://support-y8lr.onrender.com",
    "https://admin-dashboard-9juk.onrender.com",
    "https://picadailysbackend.onrender.com",
    "https://support.picadailys.com",
    "https://admin.picadailys.com",
]

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
    'TITLE': 'Picadailys API Documentation',
    'DESCRIPTION': "Picadailys is a digital and multi-faceted app aimed at providing "
    "online intermediary services with Value Added Services (VAS) and Self-Service options.",
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'ENABLE_DELETE_REQUEST_BODY': True,
    'TAGS': [
        {'name': 'KYC', 'description': 'Know Your Customer verification endpoints'},
        {'name': 'Wallet', 'description': 'Wallet management and operations'},
        {'name': 'Banking', 'description': 'All banking-related operations (transfers, cards, transactions)'},
        {'name': 'VAS', 'description': 'Airtime, Data, TV, Electricity and all value-added services'},
        {'name': 'Partner Services', 'description': 'Services provided by partner organizations'},
        {'name': 'Brand Ads', 'description': 'Brand marketing, advertisement and promotions'},
        {'name': 'Webhooks', 'description': 'Payment gateway webhook endpoints'},
    ],
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

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',  # Use an in-memory database for tests
        }
    }

    class DisableMigrations(object):

        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = DisableMigrations()


CRONJOBS = [
    ("*/5 * * * *", "gamification.jobs.refresh_all_users_points")
]

if conf("ENVIRONMENT") == "production":
    # CACHES = {
    #     "default": {
    #         "BACKEND": "django_redis.cache.RedisCache",
    #         "LOCATION": f"redis://127.0.0.1:6379/1",   # DB 1 for caching
    #         "OPTIONS": {
    #             "CLIENT_CLASS": "django_redis.client.DefaultClient",
    #             "CONNECTION_POOL_KWARGS": {
    #                 "max_connections": 200,
    #                 "retry_on_timeout": True
    #             },
    #             "TIMEOUT": 300,  # 5 mins cache timeout (recommended)
    #         }
    #     }
    # }
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_LOCATION,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {"max_connections": 200, "retry_on_timeout": True},
                # SSL only if your Redis URL is rediss://
                "SSL": REDIS_LOCATION.startswith("rediss://"),
            },
            "TIMEOUT": 300,
        }
    }
    DEFAULT_THROTTLE_CLASSES = [
        "rest_framework.throttling.ScopedRateThrottle",
    ]
elif conf("ENVIRONMENT") == "development":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
            "TIMEOUT": 300,
        }
    }
    DEFAULT_THROTTLE_CLASSES = [
        "rest_framework.throttling.ScopedRateThrottle",
    ]

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
            'level': 'INFO',   # changed from DEBUG → INFO
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },

    # Loggers
    'loggers': {
        # Django core logs (remove DEBUG noise)
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',    # changed from DEBUG → WARNING
            'propagate': True,
        },

        # Remove SQL debug log noise
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },

        # Suppress runserver & autoreloader debug spam
        'django.server': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },

        # Your apps (unchanged — keep INFO)
        'accounts': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'adverts': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'banking': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'fmcg': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'partners': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'roles': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'self_service': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'support': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'user_profile': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'vas': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
