import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

import requests
from django.conf import settings

from planner.services.errors import (
    LocationNotFound,
    NoDrivingRoute,
    OutsideUnitedStates,
    RouteUnavailable,
)
from planner.services.geo import in_united_states

METERS_TO_MILES = 0.000621371192
COORDINATES = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$"
)

_session = None
_http_lock = threading.Lock()
_pace_lock = threading.Lock()
_last_geocode = 0.0


@dataclass(frozen=True, slots=True)
class Place:
    query: str
    label: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class DrivingRoute:
    distance_miles: float
    duration_seconds: float
    coordinates: tuple


def resolve_place(query):
    match = COORDINATES.match(query)
    if match:
        first = float(match.group(1))
        second = float(match.group(2))
        if in_united_states(first, second):
            latitude, longitude = first, second
        elif in_united_states(second, first):
            latitude, longitude = second, first
        else:
            raise OutsideUnitedStates(f"'{query}' is outside the United States.")
        label = f"{latitude:.5f}, {longitude:.5f}"
        return Place(query=query, label=label, latitude=latitude, longitude=longitude)

    normalized = " ".join(query.split())
    outcome = _cached_geocode(normalized)
    kind = outcome[0]
    if kind == "missing":
        raise LocationNotFound(f"No US match for '{query}'.")
    if kind == "outside":
        raise OutsideUnitedStates(f"'{query}' is outside the United States.")
    _, latitude, longitude, label = outcome
    return Place(query=query, label=label, latitude=latitude, longitude=longitude)


def fetch_route(origin, destination):
    key = (
        round(origin.latitude, 4),
        round(origin.longitude, 4),
        round(destination.latitude, 4),
        round(destination.longitude, 4),
    )
    if key[0] == key[2] and key[1] == key[3]:
        return DrivingRoute(0.0, 0.0, ((origin.longitude, origin.latitude),))
    payload = _cached_route(*key)
    if payload is None:
        raise NoDrivingRoute("No drivable route was found between those points.")
    distance_miles, duration_seconds, coordinates = payload
    return DrivingRoute(
        distance_miles=distance_miles,
        duration_seconds=duration_seconds,
        coordinates=coordinates,
    )


def _http():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(
            {
                "User-Agent": settings.HTTP_USER_AGENT,
                "Accept": "application/json",
            }
        )
    return _session


def _get(url, **kwargs):
    with _http_lock:
        return _http().get(url, **kwargs)


def _pace_geocoder():
    global _last_geocode
    with _pace_lock:
        wait = 1.05 - (time.monotonic() - _last_geocode)
        if wait > 0:
            time.sleep(wait)
        _last_geocode = time.monotonic()


@lru_cache(maxsize=512)
def _cached_geocode(query):
    _pace_geocoder()
    try:
        response = _get(
            f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/search",
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "countrycodes": "us",
                "limit": 1,
            },
            timeout=(3.05, 12),
        )
    except requests.RequestException as exc:
        raise RouteUnavailable("The geocoder did not respond.") from exc
    if response.status_code != 200:
        raise RouteUnavailable("The geocoder did not respond.")
    payload = response.json()
    if not payload:
        return ("missing",)
    hit = payload[0]
    try:
        latitude = float(hit["lat"])
        longitude = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return ("missing",)
    country = (hit.get("address") or {}).get("country_code", "us")
    if country != "us" or not in_united_states(latitude, longitude):
        return ("outside",)
    address = hit.get("address") or {}
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("county")
    )
    state = address.get("state")
    if city and state:
        label = f"{city}, {state}"
    else:
        label = (hit.get("display_name") or query)[:160]
    return ("ok", latitude, longitude, label)


@lru_cache(maxsize=256)
def _cached_route(origin_lat, origin_lon, dest_lat, dest_lon):
    path = (
        f"{origin_lon:.6f},{origin_lat:.6f};"
        f"{dest_lon:.6f},{dest_lat:.6f}"
    )
    url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{path}"
    payload = None
    for attempt in range(2):
        try:
            response = _get(
                url,
                params={
                    "overview": "full",
                    "geometries": "geojson",
                    "steps": "false",
                },
                timeout=(3.05, 20),
            )
        except requests.RequestException as exc:
            raise RouteUnavailable("The routing service did not respond.") from exc
        if response.status_code == 429 and attempt == 0:
            time.sleep(1.1)
            continue
        if response.status_code != 200:
            raise RouteUnavailable("The routing service did not respond.")
        payload = response.json()
        break
    if not payload or payload.get("code") == "NoRoute":
        return None
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RouteUnavailable("The routing service did not return a route.")
    route = payload["routes"][0]
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    if len(geometry) < 2:
        return None
    distance_miles = float(route["distance"]) * METERS_TO_MILES
    duration_seconds = float(route.get("duration") or 0)
    coordinates = tuple((float(lon), float(lat)) for lon, lat in geometry)
    return (distance_miles, duration_seconds, coordinates)
