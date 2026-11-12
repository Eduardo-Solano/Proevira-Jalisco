import math
from typing import List, Dict, Any


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia ortodrómica en kilómetros entre dos coordenadas
    geográficas usando la fórmula del semiverseno (Haversine).
    """
    R = 6371.0  # Radio medio de la Tierra en km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(R * c, 2)


def rank_nearest_units(
    origin_lat: float,
    origin_lon: float,
    units: List[Dict[str, Any]],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Calcula la distancia a cada unidad médica y devuelve las más cercanas ordenadas.
    """
    results = []
    for u in units:
        try:
            ulat = float(u["lat"])
            ulon = float(u["lon"])
            dist = haversine_distance(origin_lat, origin_lon, ulat, ulon)
            item = dict(u)
            item["distancia_km"] = dist
            results.append(item)
        except (ValueError, TypeError, KeyError):
            continue

    results.sort(key=lambda x: x["distancia_km"])
    return results[:limit]

