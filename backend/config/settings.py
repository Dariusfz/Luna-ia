"""
Configuración de Django para LUNA-IA.

Todos los valores sensibles o dependientes del entorno se leen de variables
de entorno (o de backend/.env en desarrollo). Ver backend/.env.example.
"""

import sys
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = "test" in sys.argv

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", ".ngrok-free.dev"]),
)

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(_env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# Orígenes del frontend (Vite en desarrollo) permitidos para peticiones con CSRF
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://*.ngrok-free.dev",
    ],
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "drf_spectacular",
    "simple_history",
    "axes",
    # Dominio LUNA-IA
    "users",
    "sedes",
    "pacientes",
    "agenda",
    "servicios",
    "tratamientos",
    "inventario",
    "pagos",
    "documentos",
    "analitica",
    "auditoria",
    "api_agente",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    # Debe ir al final: registra intentos fallidos de login
    "axes.middleware.AxesMiddleware",
]

# Autenticación: axes primero para bloquear por intentos fallidos
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Bloqueo por intentos fallidos (plan §6)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]

# 2FA TOTP (obligatorio para admin y doctor, plan §6)
# Clave Fernet para cifrar los secretos TOTP. En producción debe venir de la variable de entorno.
_totp_key = env("TOTP_ENCRYPTION_KEY", default="")
if not _totp_key:
    import base64
    import hashlib

    _totp_key = base64.urlsafe_b64encode(
        hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    ).decode("ascii")
TOTP_ENCRYPTION_KEY = _totp_key
TOTP_EMISOR = "LUNA-IA"

# Clave Fernet para cifrar el contenido de los mensajes de WhatsApp (api_agente).
# Distinta de TOTP_ENCRYPTION_KEY a propósito: rotar una no obliga a rotar la otra.
_mensajes_key = env("MENSAJES_ENCRYPTION_KEY", default="")
if not _mensajes_key:
    import base64 as _b64
    import hashlib as _hl

    _mensajes_key = _b64.urlsafe_b64encode(
        _hl.sha256(("mensajes:" + SECRET_KEY).encode("utf-8")).digest()
    ).decode("ascii")
MENSAJES_ENCRYPTION_KEY = _mensajes_key
TWO_FACTOR_PENDIENTE_MINUTOS = 5
TWO_FACTOR_MAX_INTENTOS = 5

# URL del frontend para los enlaces de invitación
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
INVITACION_HORAS_VALIDEZ = 72
RECUPERACION_MINUTOS = 30

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Base de datos: PostgreSQL 16 (ver infra/docker-compose.dev.yml)
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# Usuario propio (login por email/invitación; el modelo se completa en la Semana 2)
AUTH_USER_MODEL = "users.Usuario"


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Localización: Honduras
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Tegucigalpa"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Redis: caché y broker de Celery
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
# Audio (transcripción y descarga de notas de voz) en cola propia, con concurrencia 1 (GPU compartida).
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "api_agente.tasks.procesar_audio": {"queue": "audio"},
}

# WhatsApp: Evolution API (plan §5.2). Solo por entorno.
EVOLUTION_BASE_URL = env("EVOLUTION_BASE_URL", default="http://127.0.0.1:8080")
EVOLUTION_API_KEY = env("EVOLUTION_API_KEY", default="")
EVOLUTION_INSTANCE = env("EVOLUTION_INSTANCE", default="luna-ia")
EVOLUTION_WEBHOOK_SECRET = env("EVOLUTION_WEBHOOK_SECRET", default="")

# Número(s) de WhatsApp que reciben los avisos internos del agente (citas nuevas,
# tratamientos no disponibles). Separados por coma. Vacío = no se envía nada.
ADMIN_WHATSAPP = env("ADMIN_WHATSAPP", default="")
# Interruptor general de esos avisos. En tests se apaga para no enviar mensajes reales.
NOTIFICACIONES_WHATSAPP = env.bool("NOTIFICACIONES_WHATSAPP", default=not TESTING)


# Django REST Framework + OpenAPI
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "LUNA-IA API",
    "DESCRIPTION": "ERP clínico para clínica odontológica (3 sedes) con agente de IA.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# Agente de IA: LLM agnóstico, configurado solo por entorno (ver AGENTS.md regla 2)
LLM_PROVIDER = env("LLM_PROVIDER", default="ollama")
LLM_BASE_URL = env("LLM_BASE_URL", default="http://127.0.0.1:11434/v1")
LLM_API_KEY = env("LLM_API_KEY", default="")
LLM_MODEL = env("LLM_MODEL", default="qwen3:8b")
LLM_TIMEOUT_SEGUNDOS = env.int("LLM_TIMEOUT_SEGUNDOS", default=120)
LLM_REINTENTOS_429 = env.int("LLM_REINTENTOS_429", default=2)
LLM_USER_AGENT = env("LLM_USER_AGENT", default="LUNA-IA/1.0")


# Archivos: en desarrollo local; MinIO (S3) se conecta en la fase de documentos
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# Correo saliente. Por defecto apunta a Mailpit (solo captura, no entrega).
# Para enviar a bandejas reales, definir EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS,
# EMAIL_HOST_USER y EMAIL_HOST_PASSWORD en backend/.env (ver .env.example).
EMAIL_HOST = env("EMAIL_HOST", default="127.0.0.1")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="LUNA-IA <no-reply@luna-ia.local>")
