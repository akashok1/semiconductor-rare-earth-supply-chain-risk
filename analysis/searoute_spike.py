"""Searoute spike: can a computed sea route be linked to PortWatch chokepoints?

This is the other half of the routing-matrix problem named in PROJECT_BRIEF.md
section 6 ("Product-to-chokepoint routing"): Comtrade gives us origin
countries, PortWatch gives us chokepoint traffic, but nothing links a specific
shipment to a specific chokepoint. This spike tests whether `searoute` (a
shortest-sea-route library) can supply that link -- compute a route between a
real origin and US destination port, then check which PortWatch chokepoints
that route passes near.

Method: for each origin/destination pair, compute the shortest sea route with
`searoute`, then for every PortWatch chokepoint compute the haversine distance
from the chokepoint to the NEAREST VERTEX on the route polyline. A chokepoint
"crosses" the route if that nearest-vertex distance is <= 200km. This is a
coarse proxy -- vertex spacing on long open-ocean segments can be hundreds of
km, so a route can pass close to a chokepoint between two vertices without
either vertex itself being within 200km. See the caveat in the findings file.

This is a spike: it does not touch dbt, Postgres, or the real routing matrix.
It only tells us whether the geometry technique is viable.

Usage: .venv/bin/python analysis/searoute_spike.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import requests
import searoute as sr

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw"
FINDINGS_PATH = REPO_ROOT / "analysis" / "searoute_spike_findings.md"

CHOKEPOINTS_LAYER_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "PortWatch_chokepoints_database/FeatureServer/0/query"
)

PROXIMITY_THRESHOLD_KM = 200
EARTH_RADIUS_KM = 6371.0088

# [lon, lat] -- searoute's coordinate order. Port-area coordinates from
# general geographic knowledge, not pulled from a ports database; precision
# to a few km is well inside the 200km proximity threshold used below.
ORIGIN_PORTS = {
    "Kaohsiung, TW": (120.2810, 22.6120),
    "Port Klang, MY": (101.3900, 3.0000),
    "Shanghai, CN": (121.5000, 31.2200),
    "Busan, KR": (129.0756, 35.1040),
    "Yokohama, JP": (139.6486, 35.4437),
}
US_PORTS = {
    "Los Angeles, US": (-118.2620, 33.7288),
    "New York, US": (-74.0300, 40.6700),
}


def _fetch_json(cache_name: str, url: str, params: dict) -> dict:
    """GET url, caching the raw JSON response under data/raw/cache_name."""
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, indent=2))
    return payload


def fetch_chokepoints() -> list[dict]:
    """Chokepoint names and point geometry, live from PortWatch. Not hardcoded."""
    payload = _fetch_json(
        "portwatch_chokepoints_geometry.json",
        CHOKEPOINTS_LAYER_URL,
        params={
            "where": "1=1",
            "outFields": "portid,portname,lat,lon",
            "outSR": 4326,
            "f": "json",
        },
    )
    chokepoints = []
    for feature in payload["features"]:
        attrs = feature["attributes"]
        chokepoints.append(
            {
                "portid": attrs["portid"],
                "portname": attrs["portname"],
                "lat": attrs["lat"],
                "lon": attrs["lon"],
            }
        )
    return chokepoints


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_vertex_distance_km(
    chokepoint_lat: float, chokepoint_lon: float, route_coords: list[list[float]]
) -> float:
    return min(
        haversine_km(chokepoint_lat, chokepoint_lon, vlat, vlon)
        for vlon, vlat in route_coords
    )


def compute_routes(chokepoints: list[dict]) -> list[dict]:
    results = []
    for origin_name, origin_lonlat in ORIGIN_PORTS.items():
        for dest_name, dest_lonlat in US_PORTS.items():
            route = sr.searoute(list(origin_lonlat), list(dest_lonlat), units="km")
            route_coords = route["geometry"]["coordinates"]
            route_km = route["properties"]["length"]

            crossed = []
            for cp in chokepoints:
                dist = nearest_vertex_distance_km(cp["lat"], cp["lon"], route_coords)
                if dist <= PROXIMITY_THRESHOLD_KM:
                    crossed.append({"portname": cp["portname"], "distance_km": dist})
            crossed.sort(key=lambda c: c["distance_km"])

            results.append(
                {
                    "origin": origin_name,
                    "destination": dest_name,
                    "route_km": route_km,
                    "crossed": crossed,
                }
            )
    return results


def summarize_chokepoint_crossings(
    chokepoints: list[dict], routes: list[dict]
) -> list[dict]:
    counts = {cp["portname"]: 0 for cp in chokepoints}
    for route in routes:
        for c in route["crossed"]:
            counts[c["portname"]] += 1
    return sorted(
        ({"portname": name, "routes_crossed": n} for name, n in counts.items()),
        key=lambda r: (-r["routes_crossed"], r["portname"]),
    )


def render_findings(
    chokepoints: list[dict], routes: list[dict], crossing_summary: list[dict]
) -> str:
    lines = []
    lines.append("# Searoute spike findings")
    lines.append("")
    lines.append(
        f"Generated by `analysis/searoute_spike.py`. {len(chokepoints)} chokepoints "
        "pulled live from the PortWatch `PortWatch_chokepoints_database` layer "
        f"(cached under `data/raw/`). Proximity threshold: {PROXIMITY_THRESHOLD_KM}km, "
        "haversine distance from each chokepoint to the nearest vertex on the "
        "computed route."
    )
    lines.append("")
    lines.append(
        "**Caveat:** \"nearest vertex\" is coarser than \"nearest point on the "
        "route line.\" Vertex spacing on long open-ocean segments can run into "
        "the hundreds of km, so a route can pass close to a chokepoint without "
        "any single vertex landing inside the threshold. A miss here is not "
        "proof the route doesn't pass near that chokepoint."
    )
    lines.append("")

    lines.append("## Routes")
    lines.append("")
    lines.append("| Origin | Destination | Route distance (km) | Chokepoints crossed (distance) |")
    lines.append("|---|---|---|---|")
    for r in routes:
        if r["crossed"]:
            crossed_str = "; ".join(
                f"{c['portname']} ({c['distance_km']:.0f}km)" for c in r["crossed"]
            )
        else:
            crossed_str = "none within threshold"
        lines.append(
            f"| {r['origin']} | {r['destination']} | {r['route_km']:,.0f} | {crossed_str} |"
        )
    lines.append("")

    lines.append("## Chokepoint crossing counts, across all tested routes")
    lines.append("")
    lines.append(f"{len(routes)} routes tested ({len(ORIGIN_PORTS)} origins x {len(US_PORTS)} US ports).")
    lines.append("")
    lines.append("| Chokepoint | Routes crossed |")
    lines.append("|---|---|")
    for row in crossing_summary:
        lines.append(f"| {row['portname']} | {row['routes_crossed']} / {len(routes)} |")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    print("Fetching PortWatch chokepoint geometry...")
    chokepoints = fetch_chokepoints()
    print(f"  {len(chokepoints)} chokepoints")

    print(
        f"Computing {len(ORIGIN_PORTS)} x {len(US_PORTS)} = "
        f"{len(ORIGIN_PORTS) * len(US_PORTS)} sea routes..."
    )
    routes = compute_routes(chokepoints)
    for r in routes:
        print(
            f"  {r['origin']} -> {r['destination']}: {r['route_km']:,.0f}km, "
            f"{len(r['crossed'])} chokepoint(s) within {PROXIMITY_THRESHOLD_KM}km"
        )

    crossing_summary = summarize_chokepoint_crossings(chokepoints, routes)

    report = render_findings(chokepoints, routes, crossing_summary)
    FINDINGS_PATH.write_text(report)
    print(f"Findings written to {FINDINGS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
