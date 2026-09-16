from datetime import timedelta
from decouple import config as conf
import os
import sys
import dj_database_url
import cloudinary
from csp.constants import NONCE
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Central accounts for VAS payment orchestration (from .env)
CENTRAL_OPERATIONAL_ACCOUNT = conf("CENTRAL_OPERATIONAL_ACCOUNT")
CENTRAL_COLLECTION_ACCOUNT = conf("CENTRAL_COLLECTION_ACCOUNT")

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
        # Dev Environment
        "127.0.0.1",
        "localhost",
        # API
        "picadailys.app",
        "www.picadailys.app",
        "picadailysbackend.onrender.com",
        # "miniature-waddle.onrender.com", #SUSPENDED
        # Web
        "web-y9g2.onrender.com",
        # Support
        "support-y8lr.onrender.com",
        "support.picadailys.com",
        # Admin
        "admin-dashboard-9juk.onrender.com",
        # Server IP
        "46.101.234.74",
    ]

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
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
    "accounts.apps.AccountsConfig",
    "adverts.apps.AdvertsConfig",
    "roles.apps.RolesConfig",
    "partners",
    "blog",
    "vas",
    "fmcg.apps.FmcgConfig",
    "user_profile",
    "self_service",
    "banking.apps.BankingConfig",
    "support",
    "gamification.apps.GamificationConfig",
    "waitlist",
    "web",
    "treasury.apps.TreasuryConfig",
    "ai_support.apps.AiSupportConfig",
    "csp",
    "tasks",
    "flights",
    "event",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
    "http://46.101.234.74",
    "https://picadailys.app",
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
    DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
elif ENVIRONMENT == "production":
    DEBUG = False
    database_url = conf("DATABASE_URL")
    DATABASES["default"] = dj_database_url.parse(database_url)
    DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

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
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
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
        "accounts.authentication.SessionAwareJWTAuthentication",
    ),
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "picadailys.exception_handlers.custom_exception_handler",
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
        "wallet_transfer": "20/hour",
        "pin_change": "5/hour",
        "password_change": "5/hour",
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
        "/v1/scalar/",
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
            "https://picadailysbackend.onrender.com",
        ],
    },
}
CONTENT_SECURITY_POLICY_REPORT_ONLY = False

# Enable HTTP Strict Transport Security (HSTS)
if conf("ENVIRONMENT") == "production":
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 31536000  # 1 year in seconds
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Apply HSTS to all subdomains
    SECURE_HSTS_PRELOAD = True  # Allow browsers to preload HSTS

else:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    "https://picadailys.app",
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

X_FRAME_OPTIONS = "DENY"

# Prevent browsers from interpreting files as a different MIME type
SECURE_CONTENT_TYPE_NOSNIFF = True

# Set Referrer-Policy to control what information is sent in referrer headers
SECURE_REFERRER_POLICY = "no-referrer-when-downgrade"

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
    "online intermediary services with Value Added Services (VAS) and Self-Service options.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENABLE_DELETE_REQUEST_BODY": True,
    "SCHEMA_PATH_PREFIX": r"/v1/",
    "SORT_OPERATIONS": False,
    "ENUM_GENERATE_CHOICE_DESCRIPTION": False,
    "CAMELIZE_NAMES": False,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "picadailys.schema_hooks.normalize_tags",
    ],
    "TAGS": [
        {"name": "KYC", "description": "Know Your Customer verification endpoints"},
        {"name": "Wallet", "description": "Wallet management and operations"},
        {
            "name": "Banking",
            "description": "All banking-related operations (transfers, cards, transactions)",
        },
        {
            "name": "VAS",
            "description": "Airtime, Data, TV, Electricity and all value-added services",
        },
        {
            "name": "Partner Services",
            "description": "Services provided by partner organizations",
        },
        {
            "name": "Brand Ads",
            "description": "Brand marketing, advertisement and promotions",
        },
        {"name": "Webhooks", "description": "Payment gateway webhook endpoints"},
    ],
}

CELERY_BROKER_URL = REDIS_LOCATION
if REDIS_LOCATION.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "CERT_NONE"}

CELERY_BEAT_SCHEDULE = {
    # ===============
    # Streak Tasks
    # ==============
    "check-streaks-daily": {
        "task": "gamification.tasks.check_and_update_streaks",
        "schedule": crontab(hour=0, minute=5),  # 12:05 AM daily
        "description": "Check and update user streak progress",
    },
    "send-streak-reminders": {
        "task": "gamification.tasks.send_streak_reminders",
        "schedule": crontab(hour=20, minute=0),  # 8:00 PM daily
        "description": "Send push reminders for active streaks",
    },
    # ======================
    # UGC Gamification Tasks
    # ======================
    "calculate-ugc-leaderboard": {
        "task": "gamification.tasks.calculate_ugc_leaderboard",
        "schedule": crontab(hour=1, minute=0),  # 1:00 AM daily
        "description": "Recalculate UGC leaderboards for all timeframes",
    },
    "check-ugc-achievements": {
        "task": "gamification.tasks.check_ugc_achievements",
        "schedule": crontab(minute=0),  # Every hour at :00
        "description": "Award UGC achievement bonuses to users",
    },
    "update-ugc-levels": {
        "task": "gamification.tasks.update_ugc_levels",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM daily
        "description": "Update UGC levels based on approved submissions",
    },
    "cleanup-old-leaderboard-entries": {
        "task": "gamification.tasks.cleanup_old_leaderboard_entries",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3:00 AM
        "description": "Clean up leaderboard entries older than 30 days",
    },
    "sync-ugc-progress": {
        "task": "gamification.tasks.sync_ugc_progress",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4:00 AM
        "description": "Sync and correct UGC progress data",
    },
    "cleanup-rejected-submissions": {
        "task": "gamification.tasks.cleanup_rejected_submissions",
        "schedule": crontab(
            hour=5, minute=0, day_of_month=1
        ),  # 1st day of month at 5:00 AM
        "description": "Clean up rejected submissions older than 90 days",
    },
    # =================================
    #  Data Retention / NDPR Compliance
    # =================================
    "purge-expired-otps": {
        "task": "accounts.tasks.purge_expired_otps",
        "schedule": crontab(minute="*/30"),  # every 30 minutes
        "description": "Remove expired OTP records",
    },
    "purge-old-notifications": {
        "task": "accounts.tasks.purge_old_notifications",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM daily
        "description": "Remove old user notifications",
    },
    "purge-old-activity-logs": {
        "task": "accounts.tasks.purge_old_activity_logs",
        "schedule": crontab(hour=2, minute=30),  # 2:30 AM daily
        "description": "Remove old activity logs",
    },
    "purge-stale-devices": {
        "task": "accounts.tasks.purge_stale_devices",
        "schedule": crontab(hour=3, minute=30, day_of_week="sunday"),  # Sunday 3:00 AM
        "description": "Remove stale device records",
    },
    "cleanup-expired-ads": {
        "task": "adverts.tasks.cleanup_expired_ads",
        "schedule": crontab(hour=2, minute=15),  # 2:15 AM daily
        "description": "Remove brand ad campaigns 3 days after they expire",
    },
    "cleanup-completed-brand-submissions": {
        "task": "tasks.jobs.cleanup_completed_brand_submissions",
        "schedule": crontab(
            hour=5, minute=30, day_of_month=1
        ),  # 1st day of month at 5:30 AM
        "description": "Remove completed brand task submissions older than 1 month",
    },
}

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(PROJECT_ROOT, "staticfiles")

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

cloudinary.config(
    cloud_name=conf("CLOUDINARY_CLOUD_NAME"),
    api_key=conf("CLOUDINARY_API_KEY"),
    api_secret=conf("CLOUDINARY_API_SECRET"),
)

ANTHROPIC_API_KEY = conf("ANTHROPIC_API_KEY", default="")

TESTING = (
    any(
        arg in ("test", "pytest", "py.test") or arg.endswith(("/pytest", "/py.test"))
        for arg in sys.argv
    )
    or "PYTEST_CURRENT_TEST" in os.environ
    # `python -m pytest` sets sys.argv[0] to pytest's __main__.py path, which
    # matches none of the argv checks above — but pytest is already imported
    # into sys.modules by the time Django settings load, regardless of
    # whether it was launched via the console script, `-m pytest`, or
    # `py.test`. This is what actually caught the invocation the argv checks
    # missed.
    or "pytest" in sys.modules
)
if TESTING:
    print("=========================")
    print("In TEST Mode - Disabling Migrations")
    print("=========================")

    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.spatialite",
            "NAME": ":memory:",  # Use an in-memory database for tests
        }
    }

    class DisableMigrations(object):

        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = DisableMigrations()

    # Speed up test runs by avoiding expensive PBKDF2 hashing.
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


CRONJOBS = [
    # refresh_all_users_points removed - it overwrote every user's internal
    # points balance with NextBee's external number every 5 minutes, which
    # is now stale/wrong and was clobbering the internal Points engine.
    ("*/30 * * * *", "banking.tasks.reconcile_pending_transfers"),
    ("*/15 * * * *", "vas.tasks.reconcile_pending_vas_transactions"),
    ("0 0 * * *", "waitlist.jobs.remove_unverified_waitlist_users"),
    ("0 3 * * *", "flights.jobs.sync_airports"),
]

if conf("ENVIRONMENT") == "production":
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://127.0.0.1:6379/1",  # DB 1 for caching
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 200,
                    "retry_on_timeout": True,
                },
                "TIMEOUT": 300,  # 5 mins cache timeout (recommended)
            },
        }
    }
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_LOCATION,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 200,
                    "retry_on_timeout": True,
                },
                # SSL only if your Redis URL is rediss://
                "SSL": REDIS_LOCATION.startswith("rediss://"),
                "IGNORE_EXCEPTIONS": True,
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
    "version": 1,
    "disable_existing_loggers": False,
    # Formatters
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{asctime} {levelname} {message}",
            "style": "{",
        },
    },
    # Handlers
    "handlers": {
        "console": {
            "level": "INFO",  # changed from DEBUG → INFO
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    # Loggers
    "loggers": {
        # Django core logs (remove DEBUG noise)
        "django": {
            "handlers": ["console"],
            "level": "WARNING",  # changed from DEBUG → WARNING
            "propagate": True,
        },
        # Remove SQL debug log noise
        "django.db.backends": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Suppress runserver & autoreloader debug spam
        "django.server": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Your apps (unchanged — keep INFO)
        "ai_support": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "accounts": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "adverts": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "banking": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "fmcg": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "gamification": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "partners": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "roles": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "self_service": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "support": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "tasks": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "user_profile": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "vas": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "waitlist": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "web": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
