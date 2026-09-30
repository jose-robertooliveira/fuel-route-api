import hashlib
import json
import logging
import uuid

from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from planner.services.errors import PlannerError
from planner.services.planning import build_plan
from planner.services.stations import get_index

logger = logging.getLogger(__name__)
PLAN_TTL_SECONDS = 60 * 60


@require_GET
def index(request):
    return JsonResponse(
        {
            "plan": "POST /api/v1/route/",
            "health": "GET /api/v1/health/",
            "example": {
                "start": "Dallas, TX",
                "finish": "Atlanta, GA",
            },
        }
    )


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "stations": get_index().count})


@csrf_exempt
@require_POST
def plan_route(request):
    try:
        body = _json_object(request)
        start = _place_field(body, "start")
        finish = _place_field(body, "finish")
        digest = hashlib.sha256(f"{start.casefold()}|{finish.casefold()}".encode()).hexdigest()
        cache_key = f"route-query:{digest}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        payload = build_plan(start, finish)
        plan_id = uuid.uuid4().hex[:16]
        payload["map_url"] = request.build_absolute_uri(
            reverse("route-map", args=[plan_id])
        )
        cache.set(f"route-plan:{plan_id}", payload, PLAN_TTL_SECONDS)
        cache.set(cache_key, payload, PLAN_TTL_SECONDS)
    except PlannerError as exc:
        if exc.status >= 500:
            logger.warning("%s", exc)
        return JsonResponse({"error": str(exc)}, status=exc.status)
    return JsonResponse(payload)


@require_GET
def route_map(request, plan_id):
    payload = cache.get(f"route-plan:{plan_id}")
    if payload is None:
        raise Http404("This route map has expired.")
    return render(request, "planner/map.html", {"plan": payload})


def _json_object(request):
    if not request.body:
        raise PlannerError("Request body is required.")
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise PlannerError("Request body must be JSON.") from exc
    if not isinstance(body, dict):
        raise PlannerError("Request body must be a JSON object.")
    return body


def _place_field(body, name):
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise PlannerError(f"{name} is required.")
    value = " ".join(value.split())
    if len(value) > 200:
        raise PlannerError(f"{name} must be 200 characters or fewer.")
    return value
