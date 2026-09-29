"""
Fuel planning:
  1. find the fuel stations close to the route and their position ("mile marker") along it
  2. pick the cheapest set of fuel stops that respects the tank range
"""
import hashlib
import math
from functools import lru_cache

import numpy as np
from django.conf import settings
from django.core.cache import cache
from scipy.spatial import cKDTree

from .geocoding import geocode
from .models import FuelStation
from .routing import get_route

EARTH_RADIUS_MILES = 3958.8
MAX_ROUTE_POINTS_IN_RESPONSE = 2000


class PlanningError(Exception):
    pass


def to_xyz(lat, lon):
    """Lat/lon (degrees) -> 3D points in miles. Straight-line distance ~= road-map distance for short hops."""
    lat, lon = np.radians(lat), np.radians(lon)
    return EARTH_RADIUS_MILES * np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )


@lru_cache(maxsize=1)
def load_stations():
    """All stations kept in memory once per process: a list of dicts and their 3D coordinates."""
    stations = list(FuelStation.objects.values("opis_id", "name", "address", "city", "state", "price", "lat", "lon"))
    for s in stations:
        s["price"] = float(s["price"])
    xyz = to_xyz([s["lat"] for s in stations], [s["lon"] for s in stations]) if stations else np.empty((0, 3))
    return stations, xyz


def stations_along_route(coordinates, distance_miles, max_distance=None):
    """Return stations within `max_distance` miles of the route, sorted by their mile marker."""
    max_distance = max_distance or settings.MAX_STATION_DISTANCE_MILES
    stations, station_xyz = load_stations()
    if not stations:
        return []

    coords = np.asarray(coordinates, dtype=float)
    route_xyz = to_xyz(coords[:, 1], coords[:, 0])

    # Resample the route every half mile so long straight segments don't hide nearby stations.
    seg_lengths = np.linalg.norm(np.diff(route_xyz, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    samples = np.append(np.arange(0.0, cumulative[-1], 0.5), cumulative[-1])
    dense = np.column_stack([np.interp(samples, cumulative, route_xyz[:, i]) for i in range(3)])
    miles = samples * (distance_miles / cumulative[-1]) if cumulative[-1] else samples

    distances, nearest = cKDTree(dense).query(station_xyz, distance_upper_bound=max_distance)
    found = []
    for i in np.flatnonzero(np.isfinite(distances)):
        found.append({**stations[i], "mile": float(miles[nearest[i]]), "distance_from_route_miles": float(distances[i])})
    found.sort(key=lambda s: (s["mile"], s["price"]))
    return found


def plan_fuel_stops(stations, total_miles, tank_range=None, mpg=None):
    """
    Choose the cheapest set of fuel stops (dynamic programming / shortest path over the stations).

    At each stop the vehicle buys exactly the fuel needed to reach its next stop, which must be
    at most `tank_range` miles ahead. So every leg is paid at the price of the station it starts from:

        best[j] = min over stations i within range before j of
                  best[i] + leg_miles(i, j) / mpg * price(i) + STOP_PENALTY_DOLLARS

    Assumption: the vehicle starts with an empty tank and first fuels at the cheapest station within
    START_SEARCH_MILES of the start. The few miles driven to get there are paid at that station's
    price, so the total cost covers the whole trip.
    """
    tank_range = tank_range or settings.VEHICLE_RANGE_MILES
    mpg = mpg or settings.VEHICLE_MPG
    penalty = settings.STOP_PENALTY_DOLLARS

    near_start = [s for s in stations if s["mile"] <= settings.START_SEARCH_MILES] or stations[:1]
    if not near_start or near_start[0]["mile"] > tank_range:
        raise PlanningError("No fuel station found near the start of the route.")
    first = stations.index(min(near_start, key=lambda s: s["price"]))

    points = stations[first:] + [{"mile": total_miles, "price": 0.0, "destination": True}]
    best = [math.inf] * len(points)
    previous = [None] * len(points)
    best[0] = 0.0
    for i in range(len(points) - 1):
        if best[i] == math.inf:
            continue
        for j in range(i + 1, len(points)):
            leg = points[j]["mile"] - points[i]["mile"]
            if leg > tank_range:
                break
            cost = best[i] + leg / mpg * points[i]["price"] + (0 if points[j].get("destination") else penalty)
            if cost < best[j]:
                best[j], previous[j] = cost, i

    if best[-1] == math.inf:
        raise PlanningError(f"Part of this route has no fuel station within {tank_range} miles.")

    path = []  # walk back from the destination to collect the chosen stops
    j = len(points) - 1
    while previous[j] is not None:
        j = previous[j]
        path.append(j)
    path.reverse()

    stops = []
    for k, i in enumerate(path):
        next_mile = points[path[k + 1]]["mile"] if k + 1 < len(path) else total_miles
        stops.append({**points[i], "gallons": (next_mile - points[i]["mile"]) / mpg})
    stops[0]["gallons"] += stops[0]["mile"] / mpg  # fuel used to reach the first station

    for stop in stops:
        stop["cost"] = stop["gallons"] * stop["price"]
    return stops


def plan_trip(start_query, finish_query):
    trip = f"{start_query.strip().lower()}|{finish_query.strip().lower()}"
    cache_key = "plan:" + hashlib.md5(trip.encode()).hexdigest()
    plan = cache.get(cache_key)
    if plan is not None:
        return plan

    start, finish = geocode(start_query), geocode(finish_query)
    route = get_route(start, finish)
    candidates = stations_along_route(route["coordinates"], route["distance_miles"])
    stops = plan_fuel_stops(candidates, route["distance_miles"])

    coordinates = route["coordinates"]
    step = max(1, len(coordinates) // MAX_ROUTE_POINTS_IN_RESPONSE)
    geometry = coordinates[::step]
    if geometry[-1] != coordinates[-1]:
        geometry.append(coordinates[-1])

    plan = {
        "start": start,
        "finish": finish,
        "distance_miles": round(route["distance_miles"], 1),
        "duration_hours": round(route["duration_hours"], 2),
        "vehicle": {"range_miles": settings.VEHICLE_RANGE_MILES, "mpg": settings.VEHICLE_MPG},
        "total_gallons": round(sum(s["gallons"] for s in stops), 2),
        "total_fuel_cost": round(sum(s["cost"] for s in stops), 2),
        "fuel_stops": [
            {
                "opis_id": s["opis_id"],
                "name": s["name"],
                "address": s["address"],
                "city": s["city"],
                "state": s["state"],
                "lat": s["lat"],
                "lon": s["lon"],
                "price_per_gallon": s["price"],
                "mile_marker": round(s["mile"], 1),
                "distance_from_route_miles": round(s["distance_from_route_miles"], 1),
                "gallons": round(s["gallons"], 2),
                "cost": round(s["cost"], 2),
            }
            for s in stops
        ],
        "stations_considered": len(candidates),
        "route": {"type": "LineString", "coordinates": geometry},
    }
    cache.set(cache_key, plan)
    return plan
