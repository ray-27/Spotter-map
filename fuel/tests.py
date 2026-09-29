from unittest import mock

from django.test import TestCase, override_settings

from .geocoding import LocationError, geocode
from .models import FuelStation, Place
from .planner import PlanningError, load_stations, plan_fuel_stops

NO_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}


def station(mile, price, name=None):
    return {"name": name or f"S{mile}", "mile": mile, "price": price}


@override_settings(STOP_PENALTY_DOLLARS=0)
class PlanFuelStopsTests(TestCase):
    def test_short_trip_needs_one_stop(self):
        stops = plan_fuel_stops([station(0, 3.0), station(100, 2.0)], total_miles=300)
        self.assertEqual([s["name"] for s in stops], ["S0", "S100"])
        self.assertAlmostEqual(sum(s["gallons"] for s in stops), 30)

    def test_buys_cheap_fuel_and_skips_expensive_station(self):
        stations = [station(0, 3.0), station(400, 2.5), station(600, 4.0), station(850, 3.0)]
        stops = plan_fuel_stops(stations, total_miles=1200)
        self.assertEqual([s["name"] for s in stops], ["S0", "S400", "S850"])
        self.assertAlmostEqual(sum(s["gallons"] for s in stops), 120)
        self.assertAlmostEqual(sum(s["cost"] for s in stops), 40 * 3.0 + 45 * 2.5 + 35 * 3.0)

    def test_starts_at_cheapest_station_near_start(self):
        stops = plan_fuel_stops([station(1, 3.5), station(10, 3.0)], total_miles=100)
        self.assertEqual(stops[0]["name"], "S10")
        self.assertAlmostEqual(stops[0]["gallons"], 10)  # includes the 10 miles driven to reach it

    def test_gap_longer_than_range_fails(self):
        with self.assertRaises(PlanningError):
            plan_fuel_stops([station(0, 3.0), station(600, 3.0)], total_miles=900)

    @override_settings(STOP_PENALTY_DOLLARS=5)
    def test_stop_penalty_avoids_tiny_savings(self):
        stations = [station(0, 3.00), station(100, 2.99)]
        stops = plan_fuel_stops(stations, total_miles=400)
        self.assertEqual([s["name"] for s in stops], ["S0"])


@override_settings(CACHES=NO_CACHE)
class GeocodeTests(TestCase):
    def setUp(self):
        Place.objects.create(key="chicago", state="IL", name="Chicago", lat=41.85, lon=-87.65, population=2_700_000)

    def test_coordinates(self):
        self.assertEqual(geocode("41.5, -87.5")["source"], "coordinates")

    def test_offline_city_lookup(self):
        loc = geocode("Chicago, IL")
        self.assertEqual((loc["source"], loc["lat"]), ("offline", 41.85))

    def test_rejects_location_outside_usa(self):
        with self.assertRaises(LocationError):
            geocode("51.5, -0.12")  # London
        with self.assertRaises(LocationError):
            geocode("Toronto, ON")


@override_settings(CACHES=NO_CACHE, STOP_PENALTY_DOLLARS=0)
class RouteApiTests(TestCase):
    def setUp(self):
        FuelStation.objects.create(opis_id=1, name="Cheap", address="I-1", city="A", state="IL",
                                   price="3.000", lat=40.0, lon=-90.0)
        FuelStation.objects.create(opis_id=2, name="Far away", address="I-2", city="B", state="CA",
                                   price="1.000", lat=34.0, lon=-118.0)
        load_stations.cache_clear()

    def tearDown(self):
        load_stations.cache_clear()

    @mock.patch("fuel.routing.http.get")
    def test_route_plan(self, get):
        get.return_value.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 160934.4,  # 100 miles
                "duration": 5400,
                "geometry": {"type": "LineString", "coordinates": [[-90.0, 40.0], [-90.0, 41.45]]},
            }],
        }
        resp = self.client.get("/api/route/", {"start": "40.0,-90.0", "finish": "41.45,-90.0"})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(get.call_count, 1)  # exactly one call to the routing API
        self.assertEqual([s["name"] for s in data["fuel_stops"]], ["Cheap"])
        self.assertEqual(data["total_gallons"], 10.0)
        self.assertEqual(data["total_fuel_cost"], 30.0)
        self.assertIn("/map/?start=", data["map_url"])

    def test_missing_params(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 400)
