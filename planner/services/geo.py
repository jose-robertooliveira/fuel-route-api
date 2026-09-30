import math

EARTH_MILES = 3958.7613


def haversine_miles(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    chord = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_MILES * math.asin(math.sqrt(chord))


def in_united_states(latitude, longitude):
    if 24.4 <= latitude <= 49.5 and -125.0 <= longitude <= -66.9:
        return True
    if 51.0 <= latitude <= 71.6 and -170.0 <= longitude <= -129.0:
        return True
    if 18.8 <= latitude <= 22.3 and -160.3 <= longitude <= -154.7:
        return True
    if 17.8 <= latitude <= 18.6 and -67.5 <= longitude <= -65.1:
        return True
    return False


def sample_route(coordinates, total_miles, spacing_miles):
    if not coordinates:
        return []
    if len(coordinates) == 1 or total_miles <= 0:
        longitude, latitude = coordinates[0]
        return [(latitude, longitude, 0.0)]

    raw_lengths = []
    raw_total = 0.0
    pairs = zip(coordinates, coordinates[1:])
    for (lon1, lat1), (lon2, lat2) in pairs:
        length = haversine_miles(lat1, lon1, lat2, lon2)
        raw_lengths.append(length)
        raw_total += length
    scale = (total_miles / raw_total) if raw_total else 0.0

    samples = [(coordinates[0][1], coordinates[0][0], 0.0)]
    walked = 0.0
    next_mark = spacing_miles
    for index, length in enumerate(raw_lengths):
        lon1, lat1 = coordinates[index]
        lon2, lat2 = coordinates[index + 1]
        segment = length * scale
        if segment > 0:
            while next_mark <= walked + segment + 1e-9:
                if next_mark >= total_miles:
                    break
                ratio = (next_mark - walked) / segment
                if ratio > 1:
                    break
                if ratio < 0:
                    ratio = 0.0
                latitude = lat1 + (lat2 - lat1) * ratio
                longitude = lon1 + (lon2 - lon1) * ratio
                samples.append((latitude, longitude, next_mark))
                next_mark += spacing_miles
        walked += segment

    end_lon, end_lat = coordinates[-1]
    if samples[-1][2] < total_miles - 1e-6:
        samples.append((end_lat, end_lon, total_miles))
    return samples


def simplify_coordinates(coordinates, limit):
    if not coordinates:
        return []
    if len(coordinates) <= limit:
        picked = coordinates
    else:
        step = (len(coordinates) - 1) / (limit - 1)
        picked = [coordinates[int(round(index * step))] for index in range(limit - 1)]
        picked.append(coordinates[-1])
    return [[round(longitude, 5), round(latitude, 5)] for longitude, latitude in picked]
