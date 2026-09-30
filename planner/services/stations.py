import csv
import math
from dataclasses import dataclass

from django.conf import settings

from planner.services.geo import haversine_miles, in_united_states

CELL_DEGREES = 0.5


@dataclass(frozen=True, slots=True)
class Station:
    key: int
    name: str
    address: str
    city: str
    state: str
    price: float
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Candidate:
    station: Station
    mile: float
    offset_miles: float


class StationIndex:
    def __init__(self, stations, cells):
        self.stations = stations
        self._cells = cells

    @property
    def count(self):
        return len(self.stations)

    @classmethod
    def from_csv(cls, path):
        cheapest = {}
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                parsed = _parse_row(row)
                if parsed is None:
                    continue
                name, address, city, state, price, latitude, longitude = parsed
                coord_key = (round(latitude, 3), round(longitude, 3))
                current = cheapest.get(coord_key)
                if current is None or price < current[4]:
                    cheapest[coord_key] = (
                        name,
                        address,
                        city,
                        state,
                        price,
                        latitude,
                        longitude,
                    )

        stations = []
        cells = {}
        for key, fields in enumerate(cheapest.values()):
            name, address, city, state, price, latitude, longitude = fields
            station = Station(
                key=key,
                name=name,
                address=address,
                city=city,
                state=state,
                price=price,
                latitude=latitude,
                longitude=longitude,
            )
            stations.append(station)
            cell = _cell(latitude, longitude)
            cells.setdefault(cell, []).append(station)
        return cls(stations, cells)

    def along(self, samples, corridor_miles):
        nearest = {}
        span = max(1, math.ceil(corridor_miles / (CELL_DEGREES * 45)))
        for latitude, longitude, mile in samples:
            base_x, base_y = _cell(latitude, longitude)
            for dx in range(-span, span + 1):
                for dy in range(-span, span + 1):
                    group = self._cells.get((base_x + dx, base_y + dy))
                    if not group:
                        continue
                    for station in group:
                        offset = haversine_miles(
                            latitude,
                            longitude,
                            station.latitude,
                            station.longitude,
                        )
                        if offset > corridor_miles:
                            continue
                        current = nearest.get(station.key)
                        if current is None or offset < current[0]:
                            nearest[station.key] = (offset, mile, station)
        found = [
            Candidate(station=station, mile=mile, offset_miles=offset)
            for offset, mile, station in nearest.values()
        ]
        found.sort(key=lambda item: (item.mile, item.station.price, item.station.key))
        return found


def _cell(latitude, longitude):
    return (
        math.floor(latitude / CELL_DEGREES),
        math.floor(longitude / CELL_DEGREES),
    )


def _parse_row(row):
    try:
        latitude = float(row["Latitude"])
        longitude = float(row["Longitude"])
        price = float(row["Retail Price"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0 or not in_united_states(latitude, longitude):
        return None
    name = (row.get("Truckstop Name") or "").strip()
    city = (row.get("City") or "").strip()
    state = (row.get("State") or "").strip().upper()
    address = (row.get("Address") or "").strip()
    if not name or not city or len(state) != 2:
        return None
    return name, address, city, state, price, latitude, longitude


_index = None


def load_stations():
    global _index
    path = settings.FUEL_PRICE_CSV
    if not path.exists():
        raise FileNotFoundError(f"Fuel price sheet not found at {path}")
    _index = StationIndex.from_csv(path)
    return _index


def get_index():
    if _index is None:
        return load_stations()
    return _index
