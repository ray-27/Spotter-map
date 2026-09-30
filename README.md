# Fuel Route Planner (Django)

Give it a start and finish location in the USA. It returns the driving route, the most
cost-effective fuel stops along the way (500-mile range), and the total fuel cost at 10 MPG.

## Run

Build the US city list first. Docker does not do this. `scripts/build_places.py` downloads nothing itself; it reads the GeoNames US dump and writes `data/us_places.csv.gz`, which `docker compose` then loads into the database.

```bash
curl -O https://download.geonames.org/export/dump/US.zip && unzip US.zip
python scripts/build_places.py US.txt
docker compose up --build
```

- Map UI: http://localhost:8000/map/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA
- API: http://localhost:8000/api/route/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA

Tests: `docker compose run --rm web python manage.py test`

## API

`GET /api/route/?start=<location>&finish=<location>`

A location can be:

| Format | Example | External calls |
|---|---|---|
| `City, ST` | `Chicago, IL` | none (offline lookup) |
| `lat,lon` | `41.8781,-87.6298` | none |
| anything else | `Space Needle, Seattle` | 1 Nominatim call (cached) |

Response (shortened):

```json
{
  "map_url": "http://localhost:8000/map/?start=...&finish=...",
  "start":  {"query": "New York, NY", "name": "New York City, NY", "lat": 40.71, "lon": -74.0, "source": "offline"},
  "finish": {"query": "Los Angeles, CA", "name": "Los Angeles, CA", "lat": 34.05, "lon": -118.24, "source": "offline"},
  "distance_miles": 2793.9,
  "duration_hours": 49.8,
  "vehicle": {"range_miles": 500, "mpg": 10},
  "total_gallons": 279.39,
  "total_fuel_cost": 859.81,
  "fuel_stops": [
    {"name": "SHEETZ #639", "city": "Youngstown", "state": "OH", "price_per_gallon": 3.059,
     "mile_marker": 390.6, "gallons": 46.22, "cost": 141.39, "lat": 41.1, "lon": -80.65, "...": "..."}
  ],
  "route": {"type": "LineString", "coordinates": [[-74.0, 40.71], "..."]}
}
```

`route` is GeoJSON, so it can be drawn directly on any map (Leaflet, Mapbox, geojson.io).
Errors return `{"error": "..."}` with status 400 (bad location), 422 (no fuel plan possible) or 502 (routing service down).

## How it works

1. **Geocoding the stations (offline, once).** The CSV only has city + state, so `manage.py load_data`
   matches each station to a city centre from the GeoNames US place list (`data/us_places.csv.gz`).
   About 99.7% of US rows match. Canadian stations are skipped, and duplicate rows are merged (cheapest price wins).
   This runs during `docker build`, so the SQLite database ships inside the image.
2. **Routing: 1 API call.** The free [OSRM](https://project-osrm.org/) server (OpenStreetMap data)
   returns the full route geometry. Responses are cached.
3. **Stations near the route.** The route is resampled every 0.5 miles and put in a KD-tree (scipy).
   Stations within 10 miles of the route are kept, together with their mile marker along the route.
4. **Choosing stops.** A dynamic-programming / shortest-path search over those stations. Each stop
   buys exactly the fuel needed to reach the next stop, which must be ≤ 500 miles away, so each leg
   costs `miles / 10 * price`. A small $2 penalty per stop stops the planner from adding a stop to
   save a few cents. See `fuel/planner.py`.
5. **Map.** `/map/` is a Leaflet + OpenStreetMap page that calls the API and draws the route and stops.

### Speed
- Typical request: ~0.3–1.5 s, almost all of it the OSRM call. Everything else takes a few milliseconds.
- Repeated requests are served from the cache in ~5 ms.
- External calls per request: **1** (OSRM). Up to 2 more (Nominatim) only for free-text addresses.

### Assumptions
- The vehicle starts with an empty tank and fills up at the cheapest station within 25 miles of the start.
  Fuel for those first miles is charged at that station's price, so the total cost covers the whole trip.
- It arrives at the destination with an empty tank.
- Station coordinates are city centres (the CSV has no exact coordinates). That's why a
  station counts as "on the route" if it is within 10 miles of it.

Settings (range, MPG, search distance, stop penalty, OSRM/Nominatim URLs) are in `config/settings.py`.

## Project layout

```
config/            Django settings + urls
fuel/
  geocoding.py     user input -> lat/lon (coordinates, offline city lookup, Nominatim fallback)
  routing.py       one OSRM call -> distance, duration, geometry
  planner.py       stations near route + cheapest fuel stops + response
  views.py         /api/route/ and /map/
  models.py        Place, FuelStation
  management/commands/load_data.py   import CSV + places into SQLite
  templates/fuel/map.html            Leaflet map
data/us_places.csv.gz                US places (GeoNames, CC-BY 4.0)
scripts/build_places.py              regenerates data/us_places.csv.gz from GeoNames
```
