"""
Django settings for FreightFlow.

Reads configuration from environment variables (via python-decouple) so the
same code runs locally against SQLite and in AWS against RDS PostgreSQL.
Every variable in Schema Spec §7.1 is read here.
"""
from pathlib import Path

import dj_database_url
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

# -- Core --------------------------------------------------------------------
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

# -- Apps --------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'shipments',
    'analytics',
    'ai_assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'freightflow.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'freightflow.wsgi.application'
ASGI_APPLICATION = 'freightflow.asgi.application'

# -- Database ----------------------------------------------------------------
# Default is SQLite for zero-setup local dev. Set DATABASE_URL to
# postgresql://user:pass@host:5432/dbname to point at RDS in production.
DATABASE_URL = config('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600),
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -- Static & media ----------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -- AWS / environment-driven settings (Schema Spec §7.1) --------------------
AWS_REGION = config('AWS_REGION', default='us-west-2')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')

TELEMETRY_INGEST_URL = config('TELEMETRY_INGEST_URL', default='')
TELEMETRY_API_KEY = config('TELEMETRY_API_KEY', default='')

SNS_STATUS_TOPIC_ARN = config('SNS_STATUS_TOPIC_ARN', default='')

ATHENA_WORKGROUP = config('ATHENA_WORKGROUP', default='')
ATHENA_OUTPUT_LOCATION = config('ATHENA_OUTPUT_LOCATION', default='')
ATHENA_DATABASE = config('ATHENA_DATABASE', default='')

BEDROCK_MODEL_ID = config('BEDROCK_MODEL_ID', default='')
BEDROCK_REGION = config('BEDROCK_REGION', default=AWS_REGION)

KINESIS_STREAM_NAME = config('KINESIS_STREAM_NAME', default='')

# -- Storage backend toggle --------------------------------------------------
# When AWS_STORAGE_BUCKET_NAME is set, use S3 via django-storages.
# When unset, use local filesystem storage. Single env var flips the backend;
# FileField/ImageField pick up STORAGES['default'] automatically.
if AWS_STORAGE_BUCKET_NAME:
    _default_storage = {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        'OPTIONS': {
            'bucket_name': AWS_STORAGE_BUCKET_NAME,
            'region_name': AWS_REGION,
            'default_acl': None,
            'querystring_auth': True,
        },
    }
else:
    _default_storage = {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    }

STORAGES = {
    'default': _default_storage,
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
