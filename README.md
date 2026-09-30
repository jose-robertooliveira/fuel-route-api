# Fuel route API

Django service that plans a driving route inside the United States and chooses where to buy fuel so the trip costs as little as possible.

The vehicle leaves with a full 50-gallon tank, gets 10 miles per gallon, and cannot drive more than 500 miles between fill-ups. `total_fuel_cost` is money paid at stations along the route. Fuel already in the tank at departure is not charged again.

## Run

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py runserver
```

On macOS or Linux, use `.venv/bin/python` instead of `.venv\Scripts\python`.

## Plan a trip

`POST /api/v1/route/`

```json
{
  "start": "Dallas, TX",
  "finish": "Atlanta, GA"
}
```

Coordinates work too: `"32.7767,-96.7970"` or `"-96.7970, 32.7767"`.

The response includes the road distance, a GeoJSON line, each fill-up (station, price, gallons, cost, mile along the route), the total fuel spend, and a `map_url`. Open that URL in a browser for the route and the stops. Map links stay in memory for one hour.

`GET /api/v1/health/` reports how many stations were loaded.

A Postman collection is in `postman/fuel-route.postman_collection.json`.

## External calls

Place names are geocoded with [Nominatim](https://nominatim.openstreetmap.org/). The drive is one request to the public [OSRM demo router](https://router.project-osrm.org/). A trip that passes coordinates skips geocoding, so the router is the only external call. Results are cached in the process, and the station list is never geocoded during a request.

The OSRM host is a demo server. Do not point production traffic at it.

## Price sheet

`data/fuel_prices.csv` is the assessment price sheet, with latitude and longitude resolved ahead of time (a street hit when the geocoder had one, otherwise the city). Rows that land on the same coordinate keep the lowest posted price. A station is a candidate when it sits within 30 miles of the route.

## Tests

```bash
.venv\Scripts\python manage.py test
```
