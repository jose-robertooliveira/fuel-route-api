import math

from planner.services.errors import DestinationUnreachable

MILES_PER_GALLON = 10
TANK_GALLONS = 50
MAX_RANGE_MILES = MILES_PER_GALLON * TANK_GALLONS


def plan_fuel_stops(candidates, total_miles):
    """Cheapest fill-ups for a tank that is already full at mile 0.

    From the current stop, drive to the nearest cheaper station if one is
    inside a full tank, buying only what that hop requires. Otherwise fill
    the tank and drive to the cheapest station still in range. The finish
    line is used the same way once it is inside range.
    """
    if total_miles <= MAX_RANGE_MILES + 1e-6:
        return []

    chosen = sorted(
        (
            candidate
            for candidate in candidates
            if 0 < candidate.mile < total_miles
        ),
        key=lambda candidate: (
            candidate.mile,
            candidate.station.price,
            candidate.station.key,
        ),
    )
    miles = [0.0, *(candidate.mile for candidate in chosen)]
    prices = [math.inf, *(candidate.station.price for candidate in chosen)]
    bought = [0.0] * len(miles)
    fuel = float(TANK_GALLONS)
    now = 0

    def buy_up_to(level):
        nonlocal fuel
        if fuel + 1e-9 >= level:
            return
        if now == 0:
            raise DestinationUnreachable(
                "No station inside the vehicle range can cover the next stretch of this route."
            )
        bought[now] += level - fuel
        fuel = level

    while miles[now] < total_miles - 1e-6:
        cheaper = None
        cheapest = None
        cheapest_price = math.inf
        for nxt in range(now + 1, len(miles)):
            gap = miles[nxt] - miles[now]
            if gap > MAX_RANGE_MILES + 1e-9:
                break
            if gap <= 1e-9:
                continue
            if prices[nxt] < prices[now]:
                cheaper = nxt
                break
            if prices[nxt] < cheapest_price:
                cheapest_price = prices[nxt]
                cheapest = nxt

        if cheaper is not None:
            need = (miles[cheaper] - miles[now]) / MILES_PER_GALLON
            buy_up_to(need)
            fuel -= need
            now = cheaper
            continue

        end_gap = total_miles - miles[now]
        if end_gap <= MAX_RANGE_MILES + 1e-9:
            buy_up_to(end_gap / MILES_PER_GALLON)
            break

        if cheapest is None:
            raise DestinationUnreachable(
                "No station inside the vehicle range can cover the next stretch of this route."
            )
        buy_up_to(float(TANK_GALLONS))
        need = (miles[cheapest] - miles[now]) / MILES_PER_GALLON
        fuel -= need
        now = cheapest

    if fuel < -1e-6:
        raise DestinationUnreachable(
            "No station inside the vehicle range can cover the next stretch of this route."
        )

    stops = []
    for index, gallons in enumerate(bought):
        if gallons > 1e-6:
            stops.append((chosen[index - 1], gallons))
    return stops
