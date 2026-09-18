"""Searoute spike: can a computed sea route be linked to PortWatch chokepoints?

This is the other half of the routing-matrix problem named in PROJECT_BRIEF.md
section 6 ("Product-to-chokepoint routing"): Comtrade gives us origin
countries, PortWatch gives us chokepoint traffic, but nothing links a specific
shipment to a specific chokepoint. This spike tests whether `searoute` (a
shortest-sea-route library) can supply that link: compute a route between a
real origin and US destination port, then check which PortWatch chokepoints
that route passes near.

Method: for each origin/destination pair, compute the shortest sea route with
`searoute`, then for every PortWatch chokepoint compute the true minimum
distance from the chokepoint to the route LINE (not just its vertices). A
chokepoint "crosses" the route if that distance is <= 200km.

The line distance is computed with Shapely, but Shapely is planar: it has no
notion of the Earth's curvature, so calling .distance() directly on raw
lon/lat coordinates would return a value in degrees, and a degree means a
different physical distance depending on latitude (a degree of longitude
shrinks toward the poles; a degree of latitude does not). To get a real
distance in km, each route is reprojected into an azimuthal equidistant
projection centered exactly on the chokepoint being tested before the Shapely
distance call: in that projection the chokepoint sits at (0, 0), and planar
distance from (0, 0) equals true great-circle distance in meters, because
preserving distance-from-center is the defining property of that projection.

An earlier version of this script used nearest-vertex distance instead: the
minimum haversine distance from the chokepoint to any single vertex on the
route polyline, ignoring the segments between vertices. That's a coarser
proxy, since vertex spacing on long open-ocean segments can run into the
hundreds of km, so a route can pass close to a chokepoint on a segment
between two distant vertices without either vertex itself being within
range. Both distances are computed here so the findings can report which
crossings the vertex method would have missed.

Origin ports (ORIGIN_PORT_CODES below) are named as UN/LOCODE codes; their
coordinates are resolved live, not hardcoded, from a CSV published by
github.com/cristan/improved-un-locodes. That project republishes the
official UNECE UN/LOCODE dataset and fills the coordinate gaps UN/LOCODE
itself leaves blank (Kaohsiung among them) from OpenStreetMap, recording the
source per row. Cached at data/raw/un_locode_improved_code_list.csv on first
run. Which port represents each country is an editorial choice made here and
recorded in ORIGIN_PORT_CODES; the coordinate values themselves are not.

This is a spike: it does not touch dbt, Postgres, or the real routing matrix.
It only tells us whether the geometry technique is viable.

Usage: .venv/bin/python analysis/searoute_spike.py
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import pyproj
import requests
import searoute as sr
from shapely.geometry import LineString, Point

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw"
FINDINGS_PATH = REPO_ROOT / "analysis" / "searoute_spike_findings.md"

CHOKEPOINTS_LAYER_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "PortWatch_chokepoints_database/FeatureServer/0/query"
)
UN_LOCODE_IMPROVED_URL = (
    "https://raw.githubusercontent.com/cristan/improved-un-locodes/main/"
    "data/code-list-improved.csv"
)

PROXIMITY_THRESHOLD_KM = 200
EARTH_RADIUS_KM = 6371.0088

# (UN/LOCODE country, UN/LOCODE location, display label). The five original
# origins plus ten more covering the rest of the supplier tail seen in the
# Comtrade partner data and the Census land-border finding (Mexico, Canada).
# Coordinates are resolved live in fetch_origin_ports(), not listed here.
ORIGIN_PORT_CODES = [
    ("TW", "KHH", "Kaohsiung, TW"),
    ("MY", "PKG", "Port Klang, MY"),
    ("CN", "SGH", "Shanghai, CN"),
    ("KR", "PUS", "Busan, KR"),
    ("JP", "YOK", "Yokohama, JP"),
    ("VN", "SGN", "Ho Chi Minh City, VN"),
    ("TH", "LCH", "Laem Chabang, TH"),
    ("PH", "BTG", "Batangas, PH"),
    ("SG", "SIN", "Singapore, SG"),
    ("DE", "HAM", "Hamburg, DE"),
    ("IE", "DFT", "Dublin, IE"),
    ("IL", "HFA", "Haifa, IL"),
    ("IN", "BOM", "Mumbai, IN"),
    ("MX", "ZLO", "Manzanillo, MX"),
    ("CA", "WVR", "Vancouver, CA"),
]
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


def fetch_origin_ports() -> dict[str, tuple[float, float]]:
    """Resolve ORIGIN_PORT_CODES to (lon, lat) via the live UN/LOCODE dataset."""
    cache_file = CACHE_DIR / "un_locode_improved_code_list.csv"
    if cache_file.exists():
        text = cache_file.read_text()
    else:
        resp = requests.get(UN_LOCODE_IMPROVED_URL, timeout=60)
        resp.raise_for_status()
        text = resp.text
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text)

    by_code = {(row["Country"], row["Location"]): row for row in csv.DictReader(io.StringIO(text))}

    ports = {}
    for country, location, label in ORIGIN_PORT_CODES:
        row = by_code.get((country, location))
        if row is None or not row.get("CoordinatesDecimal"):
            raise RuntimeError(
                f"No coordinates for {country}{location} ({label}) in the "
                "UN/LOCODE dataset. Pick a different port code for this origin."
            )
        lat_str, lon_str = row["CoordinatesDecimal"].split(",")
        ports[label] = (float(lon_str), float(lat_str))
    return ports


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


def _normalize_lon(lon: float) -> float:
    """searoute can return longitudes past 180 for antimeridian-crossing
    routes (e.g. 241.8 instead of -118.2); wrap back to [-180, 180] before
    handing coordinates to pyproj."""
    return ((lon + 180) % 360) - 180


def build_aeqd_transformer(lat: float, lon: float) -> pyproj.Transformer:
    """Azimuthal equidistant projection centered on (lat, lon). One of these
    per chokepoint is reused across every route tested against it, rather
    than rebuilt per route: CRS/transformer construction is the expensive
    part, not transforming a handful of coordinates through it."""
    aeqd = pyproj.CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m")
    return pyproj.Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)


def nearest_point_on_line_distance_km(
    transformer: pyproj.Transformer, route_coords: list[list[float]]
) -> float:
    projected = [
        transformer.transform(_normalize_lon(lon), lat) for lon, lat in route_coords
    ]
    line = LineString(projected)
    return line.distance(Point(0.0, 0.0)) / 1000.0


def compute_routes(chokepoints: list[dict], origin_ports: dict) -> list[dict]:
    transformers = {
        cp["portid"]: build_aeqd_transformer(cp["lat"], cp["lon"]) for cp in chokepoints
    }

    results = []
    for origin_name, origin_lonlat in origin_ports.items():
        for dest_name, dest_lonlat in US_PORTS.items():
            route = sr.searoute(list(origin_lonlat), list(dest_lonlat), units="km")
            route_coords = route["geometry"]["coordinates"]
            route_km = route["properties"]["length"]

            crossed = []
            newly_found = []
            for cp in chokepoints:
                line_dist = nearest_point_on_line_distance_km(
                    transformers[cp["portid"]], route_coords
                )
                if line_dist <= PROXIMITY_THRESHOLD_KM:
                    crossed.append({"portname": cp["portname"], "distance_km": line_dist})
                    vertex_dist = nearest_vertex_distance_km(
                        cp["lat"], cp["lon"], route_coords
                    )
                    if vertex_dist > PROXIMITY_THRESHOLD_KM:
                        newly_found.append(
                            {
                                "portname": cp["portname"],
                                "line_distance_km": line_dist,
                                "vertex_distance_km": vertex_dist,
                            }
                        )
            crossed.sort(key=lambda c: c["distance_km"])

            results.append(
                {
                    "origin": origin_name,
                    "destination": dest_name,
                    "route_km": route_km,
                    "crossed": crossed,
                    "newly_found": newly_found,
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
    chokepoints: list[dict],
    routes: list[dict],
    crossing_summary: list[dict],
    origin_ports: dict,
) -> str:
    lines = []
    lines.append("# Searoute spike findings")
    lines.append("")
    lines.append(
        f"Generated by `analysis/searoute_spike.py`. {len(chokepoints)} chokepoints "
        "pulled live from the PortWatch `PortWatch_chokepoints_database` layer, "
        f"origin port coordinates resolved live from UN/LOCODE (cached under "
        f"`data/raw/`). Proximity threshold: {PROXIMITY_THRESHOLD_KM}km, true "
        "minimum distance from each chokepoint to the computed route line "
        "(nearest point on the line, not just its vertices; see the module "
        "docstring for the azimuthal-equidistant projection this uses to get "
        "an accurate km distance rather than raw degrees)."
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
    lines.append(f"{len(routes)} routes tested ({len(origin_ports)} origins x {len(US_PORTS)} US ports).")
    lines.append("")
    lines.append("| Chokepoint | Routes crossed |")
    lines.append("|---|---|")
    for row in crossing_summary:
        lines.append(f"| {row['portname']} | {row['routes_crossed']} / {len(routes)} |")
    lines.append("")

    lines.append("## Crossings the nearest-vertex method would have missed")
    lines.append("")
    all_newly_found = [
        (r["origin"], r["destination"], nf)
        for r in routes
        for nf in r["newly_found"]
    ]
    if all_newly_found:
        lines.append(
            f"{len(all_newly_found)} route/chokepoint pair(s) cross under nearest-point-on-line "
            f"but would not have registered under the old nearest-vertex method "
            f"(vertex distance over {PROXIMITY_THRESHOLD_KM}km, line distance under it):"
        )
        lines.append("")
        lines.append("| Origin | Destination | Chokepoint | Line distance (km) | Vertex distance (km) |")
        lines.append("|---|---|---|---|---|")
        for origin, dest, nf in all_newly_found:
            lines.append(
                f"| {origin} | {dest} | {nf['portname']} | {nf['line_distance_km']:.0f} | "
                f"{nf['vertex_distance_km']:.0f} |"
            )
    else:
        lines.append(
            "None. Every crossing found by the line-distance method was also "
            "found by the nearest-vertex method on this route set."
        )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    print("Fetching PortWatch chokepoint geometry...")
    chokepoints = fetch_chokepoints()
    print(f"  {len(chokepoints)} chokepoints")

    print("Resolving origin port coordinates from UN/LOCODE...")
    origin_ports = fetch_origin_ports()
    print(f"  {len(origin_ports)} origin ports")

    print(
        f"Computing {len(origin_ports)} x {len(US_PORTS)} = "
        f"{len(origin_ports) * len(US_PORTS)} sea routes..."
    )
    routes = compute_routes(chokepoints, origin_ports)
    for r in routes:
        print(
            f"  {r['origin']} -> {r['destination']}: {r['route_km']:,.0f}km, "
            f"{len(r['crossed'])} chokepoint(s) within {PROXIMITY_THRESHOLD_KM}km "
            f"({len(r['newly_found'])} new vs. nearest-vertex)"
        )

    crossing_summary = summarize_chokepoint_crossings(chokepoints, routes)

    report = render_findings(chokepoints, routes, crossing_summary, origin_ports)
    FINDINGS_PATH.write_text(report)
    print(f"Findings written to {FINDINGS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
