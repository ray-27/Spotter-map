import re


def normalize_place(name: str) -> str:
    """Normalize a city name so 'St. Louis', 'Saint Louis' and 'ST LOUIS' all match."""
    s = name.lower().replace("-", " ")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(saint|ste)\b", "st", s)
    s = re.sub(r"\bft\b", "fort", s)
    s = re.sub(r"\bmt\b", "mount", s)
    s = re.sub(r"\b(mc|de|la|du) ", r"\1", s)  # "Mc Calla" -> "mccalla"
    s = re.sub(r"^([nsew]) ", lambda m: {"n": "north ", "s": "south ", "e": "east ", "w": "west "}[m.group(1)], s)
    return re.sub(r"\s+", " ", s).strip()
