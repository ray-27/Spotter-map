"""
One-time helper that builds data/us_places.csv.gz from the GeoNames US dump.

The fuel price CSV only has city + state, so we need a city -> lat/lon table.
Doing this offline means we never call a geocoding API for the 8k stations.

Usage:
    curl -O https://download.geonames.org/export/dump/US.zip && unzip US.zip
    python scripts/build_places.py US.txt
"""
import csv
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fuel.text import normalize_place  # noqa: E402

csv.field_size_limit(10**9)
OUT = Path(__file__).resolve().parent.parent / "data" / "us_places.csv.gz"


def main(path):
    places = {}  # (normalized name, state) -> (display name, lat, lon, population)
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row[6] != "P":  # only populated places
                continue
            name, state = row[1], row[10]
            lat, lon, pop = float(row[4]), float(row[5]), int(row[14] or 0)
            for variant in {row[1], row[2]}:  # name and ascii name
                key = (normalize_place(variant), state)
                # When a state has several places with the same name, keep the biggest.
                if key not in places or pop > places[key][3]:
                    places[key] = (name, lat, lon, pop)

    # "New York City" / "Oklahoma City" should also match "New York" / "Oklahoma" if nothing else does.
    for (key, state), value in list(places.items()):
        if key.endswith(" city"):
            places.setdefault((key.removesuffix(" city"), state), value)

    OUT.parent.mkdir(exist_ok=True)
    with gzip.open(OUT, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["key", "state", "name", "lat", "lon", "population"])
        for (key, state), (name, lat, lon, pop) in sorted(places.items()):
            writer.writerow([key, state, name, lat, lon, pop])
    print(f"Wrote {len(places)} places to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
