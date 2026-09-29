import csv
import gzip
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from fuel.models import FuelStation, Place
from fuel.text import normalize_place


class Command(BaseCommand):
    help = "Load US places and fuel stations (geocoded offline by city + state) into the database."

    @transaction.atomic
    def handle(self, *args, **options):
        places = self.load_places()
        self.load_stations(places)

    def load_places(self):
        Place.objects.all().delete()
        lookup = {}
        rows = []
        with gzip.open(settings.PLACES_FILE, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lat, lon = float(r["lat"]), float(r["lon"])
                lookup[(r["key"], r["state"])] = (lat, lon)
                rows.append(Place(key=r["key"], state=r["state"], name=r["name"],
                                  lat=lat, lon=lon, population=int(r["population"])))
        Place.objects.bulk_create(rows, batch_size=5000)
        self.stdout.write(f"Loaded {len(rows)} places")
        return lookup

    def load_stations(self, places):
        FuelStation.objects.all().delete()
        stations = {}  # the CSV repeats some stations; keep the cheapest price per OPIS id
        skipped = 0
        with open(settings.FUEL_PRICES_FILE, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                state = r["State"].strip()
                coords = places.get((normalize_place(r["City"]), state))
                if coords is None:  # Canadian stations and a handful of unknown towns
                    skipped += 1
                    continue
                opis_id = int(r["OPIS Truckstop ID"])
                price = Decimal(r["Retail Price"]).quantize(Decimal("0.001"))
                if opis_id in stations and stations[opis_id].price <= price:
                    continue
                stations[opis_id] = FuelStation(
                    opis_id=opis_id, name=r["Truckstop Name"].strip(), address=r["Address"].strip(),
                    city=r["City"].strip(), state=state, price=price, lat=coords[0], lon=coords[1],
                )
        FuelStation.objects.bulk_create(stations.values(), batch_size=2000)
        self.stdout.write(f"Loaded {len(stations)} fuel stations ({skipped} rows skipped: not in the USA or unknown city)")
