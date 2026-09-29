from django.urls import path
from django.views.generic import RedirectView

from fuel import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="map")),
    path("api/route/", views.route_plan, name="route-plan"),
    path("map/", views.map_view, name="map"),
]
