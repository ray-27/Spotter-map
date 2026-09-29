import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "fuel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

# File cache is shared between gunicorn workers, so a route is fetched from OSRM only once.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("CACHE_DIR", "/tmp/fuel_route_cache"),
        "TIMEOUT": 60 * 60 * 24,
    }
}

# OpenStreetMap's tile servers require a Referer header; Django's default ("same-origin") strips it.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Fuel planner settings ---
FUEL_PRICES_FILE = BASE_DIR / "fuel-prices-for-be-assessment.csv"
PLACES_FILE = BASE_DIR / "data" / "us_places.csv.gz"

VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
# Stations are geocoded to their city centre, so allow a few miles of distance from the route.
MAX_STATION_DISTANCE_MILES = 10
# The first fill-up is the cheapest station within this many miles of the start.
START_SEARCH_MILES = 25
# Each extra stop is treated as costing this much (time/detour), so the planner
# won't add a stop just to save a few cents. Set to 0 for the pure cheapest plan.
STOP_PENALTY_DOLLARS = 2.0

OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
HTTP_USER_AGENT = "spotter-fuel-planner/1.0"
HTTP_TIMEOUT_SECONDS = 15
