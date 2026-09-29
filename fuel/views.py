from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .geocoding import LocationError
from .planner import PlanningError, plan_trip
from .routing import RoutingError


@require_GET
def route_plan(request):
    """GET /api/route/?start=Chicago, IL&finish=Houston, TX"""
    start, finish = request.GET.get("start", ""), request.GET.get("finish", "")
    try:
        plan = plan_trip(start, finish)
    except LocationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except PlanningError as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    query = urlencode({"start": start, "finish": finish})
    map_url = request.build_absolute_uri(f"{reverse('map')}?{query}")
    return JsonResponse({"map_url": map_url, **plan})


@require_GET
def map_view(request):
    return render(request, "fuel/map.html")
