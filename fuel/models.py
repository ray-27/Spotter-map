from django.db import models


class Place(models.Model):
    """A US city/town with its coordinates (from GeoNames). Used for offline geocoding."""

    key = models.CharField(max_length=200)  # normalized name, see fuel.text.normalize_place
    state = models.CharField(max_length=2)
    name = models.CharField(max_length=200)
    lat = models.FloatField()
    lon = models.FloatField()
    population = models.IntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["key", "state"])]

    def __str__(self):
        return f"{self.name}, {self.state}"


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=6, decimal_places=3)
    lat = models.FloatField()
    lon = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
