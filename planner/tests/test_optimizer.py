import math
import random
from functools import cache

from django.test import SimpleTestCase

from planner.services.errors import DestinationUnreachable
from planner.services.geo import haversine_miles, in_united_states, sample_route
from planner.services.optimizer import MILES_PER_GALLON, TANK_GALLONS, plan_fuel_stops
from planner.services.routing import resolve_place
from planner.services.stations import Candidate, Station, get_index


def station(key, price, latitude=31.0, longitude=-97.0):
    return Station(
        key=key,
        name=f"Stop {key}",
        address="Highway",
        city="Town",
        state="TX",
        price=price,
        latitude=latitude,
        longitude=longitude,
    )


def candidate(mile, price, key):
    return Candidate(
        station=station(key, price),
        mile=float(mile),
        offset_miles=1.0,
    )


def spent(stops):
    return sum(gallons * item.station.price for item, gallons in stops)


def feasible(total_miles, stops):
    fuel = float(TANK_GALLONS)
    position = 0.0
    for item, gallons in stops:
        fuel -= (item.mile - position) / MILES_PER_GALLON
        if fuel < -1e-6 or gallons < -1e-9:
            return False
        fuel += gallons
        if fuel > TANK_GALLONS + 1e-6:
            return False
        position = item.mile
    fuel -= (total_miles - position) / MILES_PER_GALLON
    return fuel >= -1e-6


def exact_cost(candidates, total_miles):
    points = sorted(
        (
            item
            for item in candidates
            if 0 <= item.mile <= total_miles
        ),
        key=lambda item: (item.mile, item.station.price, item.station.key),
    )
    nodes = [(0.0, None)] + [(item.mile, item.station.price) for item in points]
    nodes.append((float(total_miles), None))

    @cache
    def search(index, fuel):
        if index == len(nodes) - 1:
            return 0.0
        mile, price = nodes[index]
        best = math.inf
        departures = (fuel,) if price is None else range(fuel, TANK_GALLONS + 1)
        for depart in departures:
            pay = 0.0 if price is None else (depart - fuel) * price
            for nxt in range(index + 1, len(nodes)):
                need = int(round((nodes[nxt][0] - mile) / MILES_PER_GALLON))
                if need > depart:
                    break
                best = min(best, pay + search(nxt, depart - need))
        return best

    result = search(0, TANK_GALLONS)
    if math.isinf(result):
        return None
    return result


class FuelPlanTests(SimpleTestCase):
    def test_full_tank_covers_a_short_trip(self):
        stops = plan_fuel_stops([candidate(100, 9, 1)], 200)
        self.assertEqual(stops, [])

    def test_buys_the_later_cheaper_station(self):
        stops = plan_fuel_stops(
            [candidate(200, 5, 1), candidate(400, 2, 2)],
            600,
        )
        self.assertEqual([(item.mile, gallons) for item, gallons in stops], [(400, 10)])
        self.assertAlmostEqual(spent(stops), 20)

    def test_partial_fill_beats_filling_the_tank(self):
        stops = plan_fuel_stops(
            [candidate(400, 4, 1), candidate(550, 2, 2)],
            700,
        )
        self.assertEqual(
            [(item.station.price, gallons) for item, gallons in stops],
            [(4, 5), (2, 15)],
        )
        self.assertAlmostEqual(spent(stops), 50)
        self.assertTrue(feasible(700, stops))

    def test_buys_expensive_fuel_only_to_reach_a_cheaper_station(self):
        stops = plan_fuel_stops(
            [candidate(450, 9, 1), candidate(800, 1, 2)],
            1000,
        )
        self.assertAlmostEqual(spent(stops), 290)
        self.assertTrue(feasible(1000, stops))

    def test_unreachable_without_a_station_in_range(self):
        with self.assertRaises(DestinationUnreachable):
            plan_fuel_stops([candidate(100, 3, 1)], 800)

    def test_matches_exact_search_on_random_trips(self):
        picker = random.Random(7)
        prices = (2.5, 3, 3.5, 4, 5, 6)
        for _ in range(40):
            total = picker.randrange(50, 901, 10)
            chosen = []
            for key in range(picker.randint(0, 6)):
                mile = picker.randrange(0, total + 1, 10)
                chosen.append(candidate(mile, picker.choice(prices), key))
            expected = exact_cost(chosen, total)
            try:
                stops = plan_fuel_stops(chosen, total)
            except DestinationUnreachable:
                stops = None
            if expected is None:
                self.assertIsNone(stops)
                continue
            self.assertIsNotNone(stops, msg=f"total={total} stations={chosen}")
            self.assertTrue(feasible(total, stops))
            self.assertAlmostEqual(spent(stops), expected, places=5)


class GeoTests(SimpleTestCase):
    def test_united_states_bounds(self):
        self.assertTrue(in_united_states(32.78, -96.80))
        self.assertTrue(in_united_states(64.84, -147.72))
        self.assertTrue(in_united_states(21.31, -157.86))
        self.assertFalse(in_united_states(51.50, -0.12))

    def test_coordinate_order_is_accepted_either_way(self):
        place = resolve_place("-96.7970, 32.7767")
        self.assertAlmostEqual(place.latitude, 32.7767, places=4)
        self.assertAlmostEqual(place.longitude, -96.7970, places=4)

    def test_samples_follow_the_driving_distance(self):
        coordinates = ((-97.0, 31.0), (-97.0, 32.0))
        distance = haversine_miles(31.0, -97.0, 32.0, -97.0)
        samples = sample_route(coordinates, distance, 20)
        self.assertEqual(samples[0][2], 0)
        self.assertAlmostEqual(samples[-1][2], distance, places=5)
        self.assertLess(abs(samples[-1][0] - 32.0), 1e-6)

    def test_price_sheet_indexes_real_stations(self):
        index = get_index()
        self.assertGreater(index.count, 1000)
        station_row = index.stations[0]
        found = index.along(
            [(station_row.latitude, station_row.longitude, 40)],
            30,
        )
        self.assertTrue(any(item.station.key == station_row.key for item in found))
        missed = index.along(
            [(station_row.latitude + 5, station_row.longitude, 40)],
            30,
        )
        self.assertFalse(any(item.station.key == station_row.key for item in missed))
