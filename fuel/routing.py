"""Driving route from the free OSRM demo server (OpenStreetMap data). One HTTP call per route."""
import requests
from django.conf import settings
from django.core.cache import cache

METERS_PER_MILE = 1609.344

http = requests.Session()
http.headers["User-Agent"] = settings.HTTP_USER_AGENT


class RoutingError(Exception):
    pass


def get_route(start, finish):
    """Return {"distance_miles", "duration_hours", "coordinates": [[lon, lat], ...]}."""
    points = f"{start['lon']:.5f},{start['lat']:.5f};{finish['lon']:.5f},{finish['lat']:.5f}"
    cache_key = f"osrm:{points}"
    route = cache.get(cache_key)
    if route is not None:
        return route

    try:
        resp = http.get(
            f"{settings.OSRM_URL}/route/v1/driving/{points}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No driving route found ({data.get('message') or data.get('code')}).")

    best = data["routes"][0]
    route = {
        "distance_miles": best["distance"] / METERS_PER_MILE,
        "duration_hours": best["duration"] / 3600,
        "coordinates": best["geometry"]["coordinates"],
    }
    cache.set(cache_key, route)
    return route
