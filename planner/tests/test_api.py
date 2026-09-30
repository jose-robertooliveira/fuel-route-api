import json
from unittest.mock import patch
from urllib.parse import urlparse

from django.test import Client, SimpleTestCase

from planner.services.routing import DrivingRoute, Place
from planner.services.stations import Candidate, Station


class RouteApiTests(SimpleTestCase):
    def test_health_lists_loaded_stations(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["stations"], 1000)

    def test_post_requires_both_places(self):
        response = self.client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "Dallas, TX"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("finish", response.json()["error"])

    def test_coordinates_outside_the_united_states_are_rejected(self):
        response = self.client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "51.5074,-0.1278", "finish": "32.7767,-96.7970"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_json_post_does_not_require_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "51.5074,-0.1278", "finish": "32.7767,-96.7970"}),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 403)

    @patch("planner.services.planning.fetch_route")
    @patch("planner.services.planning.resolve_place")
    @patch("planner.services.planning.get_index")
    def test_plan_returns_cost_and_a_map(self, get_index, resolve_place, fetch_route):
        resolve_place.side_effect = [
            Place("Dallas, TX", "Dallas, Texas", 32.7767, -96.7970),
            Place("Atlanta, GA", "Atlanta, Georgia", 33.7490, -84.3880),
        ]
        fetch_route.return_value = DrivingRoute(
            distance_miles=700,
            duration_seconds=36000,
            coordinates=((-96.7970, 32.7767), (-90.0, 33.2), (-84.3880, 33.7490)),
        )
        get_index.return_value.along.return_value = [
            Candidate(station=_stop(1, "West", 4), mile=400, offset_miles=2),
            Candidate(station=_stop(2, "East", 2), mile=550, offset_miles=4),
        ]

        response = self.client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "Dallas, TX", "finish": "Atlanta, GA"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_fuel_cost"], 50)
        self.assertEqual(body["fuel_stops"][0]["gallons"], 5)
        self.assertEqual(body["fuel_stops"][1]["name"], "East")
        self.assertEqual(body["route"]["distance_miles"], 700)
        self.assertEqual(len(fetch_route.mock_calls), 1)

        map_response = self.client.get(urlparse(body["map_url"]).path)
        self.assertEqual(map_response.status_code, 200)
        self.assertContains(map_response, "East")
        self.assertContains(map_response, "50.00")

    def test_unknown_map_is_not_found(self):
        response = self.client.get("/api/v1/route/missing-plan/map/")
        self.assertEqual(response.status_code, 404)


def _stop(key, name, price):
    return Station(
        key=key,
        name=name,
        address="I-20",
        city="Town",
        state="TX",
        price=price,
        latitude=32.5,
        longitude=-90.0,
    )
