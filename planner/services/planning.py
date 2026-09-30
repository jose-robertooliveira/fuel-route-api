from django.conf import settings

from planner.services.geo import sample_route, simplify_coordinates
from planner.services.optimizer import (
    MAX_RANGE_MILES,
    MILES_PER_GALLON,
    TANK_GALLONS,
    plan_fuel_stops,
)
from planner.services.routing import fetch_route, resolve_place
from planner.services.stations import get_index

SAMPLE_MILES = 4
GEOMETRY_POINT_LIMIT = 900


def build_plan(start, finish):
    origin = resolve_place(start)
    destination = resolve_place(finish)
    route = fetch_route(origin, destination)
    samples = _samples(route)
    candidates = get_index().along(samples, settings.ROUTE_CORRIDOR_MILES)
    purchases = plan_fuel_stops(candidates, route.distance_miles)

    stops = []
    spent = 0.0
    gallons_purchased = 0.0
    for candidate, gallons in purchases:
        station = candidate.station
        gallons = round(gallons, 2)
        cost = round(gallons * station.price, 2)
        spent += cost
        gallons_purchased += gallons
        stops.append(
            {
                "name": station.name,
                "address": station.address,
                "city": station.city,
                "state": station.state,
                "latitude": round(station.latitude, 6),
                "longitude": round(station.longitude, 6),
                "price_per_gallon": round(station.price, 3),
                "mile_along_route": round(candidate.mile, 1),
                "distance_from_route_miles": round(candidate.offset_miles, 1),
                "gallons": round(gallons, 2),
                "cost": cost,
            }
        )

    gallons_consumed = route.distance_miles / MILES_PER_GALLON
    return {
        "start": _place_payload(origin),
        "finish": _place_payload(destination),
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_minutes": round(route.duration_seconds / 60),
            "geometry": {
                "type": "LineString",
                "coordinates": simplify_coordinates(
                    route.coordinates,
                    GEOMETRY_POINT_LIMIT,
                ),
            },
        },
        "vehicle": {
            "miles_per_gallon": MILES_PER_GALLON,
            "tank_gallons": TANK_GALLONS,
            "max_range_miles": MAX_RANGE_MILES,
            "departure_tank": "full",
        },
        "fuel_stops": stops,
        "gallons_consumed": round(gallons_consumed, 2),
        "gallons_purchased": round(gallons_purchased, 2),
        "total_fuel_cost": round(spent, 2),
        "note": (
            "Total cost counts fuel bought along the route. "
            "Departure is a full tank and is not billed again."
        ),
    }


def _samples(route):
    if route.distance_miles <= 0:
        longitude, latitude = route.coordinates[0]
        return [(latitude, longitude, 0.0)]
    return sample_route(route.coordinates, route.distance_miles, SAMPLE_MILES)


def _place_payload(place):
    return {
        "query": place.query,
        "label": place.label,
        "latitude": round(place.latitude, 6),
        "longitude": round(place.longitude, 6),
    }
