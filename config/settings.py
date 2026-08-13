import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-secret-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]

ROOT_URLCONF = "config.urls"
INSTALLED_APPS = ["django.contrib.contenttypes", "video_api"]
MIDDLEWARE = []
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MINIMAX_API_BASE_URL = os.environ.get("MINIMAX_API_BASE_URL", "https://api.minimaxi.com").rstrip("/")
MINIMAX_API_TIMEOUT = float(os.environ.get("MINIMAX_API_TIMEOUT", "30"))

