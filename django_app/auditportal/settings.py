
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get('AUDIT_DJANGO_SECRET_KEY', 'change-me')
DEBUG = os.environ.get('AUDIT_DEBUG', 'False').lower() in ('1', 'true', 'yes', 'on')
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('AUDIT_ALLOWED_HOSTS', '*').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'corsheaders',
    'dashboard',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'auditportal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'auditportal.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('AUDIT_DB_NAME', os.path.join(os.path.dirname(BASE_DIR), 'audit_v2.db')),
    }
}

# PostgreSQL opcional (recomendado em produção). Exemplo:
#   AUDIT_DATABASE_URL=postgres://user:pass@localhost:5432/audit
_db_url = os.environ.get('AUDIT_DATABASE_URL')
if _db_url:
    import re as _re
    _m = _re.match(
        r'(?P<engine>\w+)://(?P<user>[^:]*):(?P<pass>[^@]*)@(?P<host>[^:/]*)(?::(?P<port>\d+))?/(?P<name>.+)',
        _db_url)
    if _m:
        _engines = {'postgres': 'django.db.backends.postgresql', 'postgresql': 'django.db.backends.postgresql',
                    'mysql': 'django.db.backends.mysql', 'sqlite': 'django.db.backends.sqlite3'}
        DATABASES = {'default': {
            'ENGINE': _engines.get(_m.group('engine'), 'django.db.backends.postgresql'),
            'NAME': _m.group('name'),
            'USER': _m.group('user') or None,
            'PASSWORD': _m.group('pass') or '',
            'HOST': _m.group('host'),
            'PORT': _m.group('port') or '',
            'CONN_MAX_AGE': 60,
        }}

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Email Backend for Development (Console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

STATIC_URL = '/django/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_URL = '/django/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Fallback for when Redis is not available (Development/Testing)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'dashboard.auth.ApiTokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.environ.get('AUDIT_THROTTLE_ANON', '60/min'),
        'user': os.environ.get('AUDIT_THROTTLE_USER', '600/min'),
    },
}

CORS_ALLOW_ALL_ORIGINS = os.environ.get('AUDIT_CORS_ALLOW_ALL', 'True' if DEBUG else 'False').lower() in ('1', 'true', 'yes', 'on')
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get('AUDIT_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    if o.strip()
]

# --- Segurança (hardening) ------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
if os.environ.get('AUDIT_SSL_REDIRECT', 'False').lower() in ('1', 'true', 'yes'):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
if not DEBUG and os.environ.get('AUDIT_DJANGO_SECRET_KEY'):
    SECURE_HSTS_SECONDS = int(os.environ.get('AUDIT_HSTS_SECONDS', 31536000))

# Limite de upload (Excel Studio: 25 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
