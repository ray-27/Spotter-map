"""
Turn user input into coordinates. Accepted formats, cheapest first:
  1. "lat,lon"          e.g. "41.8781,-87.6298"      -> no external call
  2. "City, ST"         e.g. "Chicago, IL"           -> offline lookup in the Place table
  3. anything else      e.g. "1600 Amphitheatre Pkwy" -> Nominatim (OpenStreetMap), cached
"""
import hashlib
import re

import requests
from django.conf import settings
from django.core.cache import cache

from .models import Place
from .text import normalize_place

COORDS_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_STATE_RE = re.compile(r"^\s*(.+?)\s*,\s*([A-Za-z]{2})\s*$")
COUNTRY_SUFFIX_RE = re.compile(r",\s*(usa|us|united states( of america)?)\s*$", re.I)
US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)

http = requests.Session()
http.headers["User-Agent"] = settings.HTTP_USER_AGENT


class LocationError(Exception):
    pass


def in_usa(lat, lon):
    """Rough bounding box covering the 50 states."""
    return 18.5 <= lat <= 71.5 and -179.2 <= lon <= -66.9


def geocode(query):
    query = (query or "").strip()
    if not query:
        raise LocationError("Both 'start' and 'finish' are required.")

    location = parse_coordinates(query) or lookup_place(query) or nominatim(query)
    if location is None:
        raise LocationError(f"Could not find location '{query}'.")
    if not in_usa(location["lat"], location["lon"]):
        raise LocationError(f"Location '{query}' is not in the USA.")
    return {"query": query, **location}


def parse_coordinates(query):
    match = COORDS_RE.match(query)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    return {"name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon, "source": "coordinates"}


def lookup_place(query):
    match = CITY_STATE_RE.match(COUNTRY_SUFFIX_RE.sub("", query))
    if not match:
        return None
    city, state = match.group(1), match.group(2).upper()
    if state not in US_STATES:
        raise LocationError(f"'{state}' is not a US state code; start and finish must be in the USA.")
    place = (Place.objects.filter(key=normalize_place(city), state=state)
             .order_by("-population").first())
    if place is None:
        return None
    return {"name": f"{place.name}, {place.state}", "lat": place.lat, "lon": place.lon, "source": "offline"}


def nominatim(query):
    cache_key = "nominatim:" + hashlib.md5(query.lower().encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None  # {} means "known to be not found"

    try:
        resp = http.get(
            f"{settings.NOMINATIM_URL}/search",
            params={"q": query, "format": "jsonv2", "countrycodes": "us", "limit": 1},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        raise LocationError(f"Geocoding service unavailable: {exc}") from exc

    location = {}
    if results:
        r = results[0]
        location = {"name": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"]), "source": "nominatim"}
    cache.set(cache_key, location)
    return location or None
