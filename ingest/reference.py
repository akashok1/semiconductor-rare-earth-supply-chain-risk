"""Reference data build: port coordinates, chokepoint coordinates, routing matrix.

Ports the coordinate resolution and crossing computation validated in
`analysis/searoute_spike.py` into a committed pipeline step. That spike asked
whether a computed sea route could be linked to PortWatch chokepoints at all;
this module answers that question for every origin/destination/chokepoint
combination and writes the result as data, not a script findings file.

Method (see analysis/searoute_spike.py for the fuller derivation): for each
origin/destination port pair, compute the shortest sea route with `searoute`,
then for every PortWatch chokepoint compute the true minimum distance from
the chokepoint to the route LINE (not just its vertices), reprojecting the
route into an azimuthal equidistant projection centered on the chokepoint so
that planar distance from the origin equals great-circle distance in meters.
A chokepoint "crosses" a route if that distance is at or under a stated
threshold, default 200km.

Origin and US destination ports are named as UN/LOCODE codes; their
coordinates are resolved live from a CSV published by
github.com/cristan/improved-un-locodes, which republishes the official
UNECE UN/LOCODE dataset and fills the coordinate gaps UN/LOCODE itself
leaves blank (Kaohsiung among them) from OpenStreetMap, recording the source
per row. Cached at data/raw/un_locode_improved_code_list.csv on first run.
Which port represents each country, and which US port represents each
coast, is an editorial choice made here and recorded in ORIGIN_PORTS and
US_DESTINATION_PORTS; the coordinate values themselves are not.

Writes three files to data/reference/:
  port_coordinates.csv      locode, port_name, country_iso3, latitude,
                             longitude, source, role (origin/us_destination)
  chokepoint_coordinates.csv portid, chokepoint_name, latitude, longitude,
                             source. All 28 PortWatch chokepoints, not
                             filtered to the ones any route crosses.
  routing_matrix.csv        one row per origin x destination x chokepoint
                             (15 x 2 x 28 = 840), including non-crossings.

Usage: .venv/bin/python -m ingest.reference
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pyproj
import requests
import searoute as sr
from shapely.geometry import LineString, Point

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"

CHOKEPOINTS_LAYER_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "PortWatch_chokepoints_database/FeatureServer/0/query"
)
UN_LOCODE_IMPROVED_URL = (
    "https://raw.githubusercontent.com/cristan/improved-un-locodes/main/"
    "data/code-list-improved.csv"
)

DEFAULT_THRESHOLD_KM = 200
EXPECTED_CHOKEPOINT_COUNT = 28
HORMUZ_NAME = "Strait of Hormuz"

# (UN/LOCODE country, UN/LOCODE location, port name, ISO3). Which port
# represents each country is an editorial choice; the coordinates are
# resolved live from UN/LOCODE, not hardcoded here.
ORIGIN_PORTS = [
    ("TW", "KHH", "Kaohsiung", "TWN"),
    ("MY", "PKG", "Port Klang", "MYS"),
    ("CN", "SGH", "Shanghai", "CHN"),
    ("KR", "PUS", "Busan", "KOR"),
    ("JP", "YOK", "Yokohama", "JPN"),
    ("VN", "SGN", "Ho Chi Minh City", "VNM"),
    ("TH", "LCH", "Laem Chabang", "THA"),
    ("PH", "BTG", "Batangas", "PHL"),
    ("SG", "SIN", "Singapore", "SGP"),
    ("DE", "HAM", "Hamburg", "DEU"),
    ("IE", "DFT", "Dublin", "IRL"),
    ("IL", "HFA", "Haifa", "ISR"),
    ("IN", "BOM", "Mumbai", "IND"),
    ("MX", "ZLO", "Manzanillo", "MEX"),
    ("CA", "WVR", "Vancouver", "CAN"),
]

# (UN/LOCODE country, UN/LOCODE location, port name, ISO3, coast label).
# Coast label matches the west_coast/east_coast/gulf naming already used in
# data/reference/mode_shares.csv and port_entry_shares.csv.
US_DESTINATION_PORTS = [
    ("US", "LAX", "Los Angeles", "USA", "west_coast"),
    ("US", "NYC", "New York", "USA", "east_coast"),
]


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
    """Chokepoint names and point geometry, live from PortWatch. All 28."""
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
    chokepoints = [
        {
            "portid": f["attributes"]["portid"],
            "portname": f["attributes"]["portname"],
            "lat": f["attributes"]["lat"],
            "lon": f["attributes"]["lon"],
        }
        for f in payload["features"]
    ]
    if len(chokepoints) != EXPECTED_CHOKEPOINT_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_CHOKEPOINT_COUNT} PortWatch chokepoints, got "
            f"{len(chokepoints)}. docs/07_assumptions_limitations.md assumes 28; "
            "check whether PortWatch has added or removed chokepoints."
        )
    return chokepoints


def _fetch_un_locode_text() -> str:
    cache_file = CACHE_DIR / "un_locode_improved_code_list.csv"
    if cache_file.exists():
        return cache_file.read_text()

    resp = requests.get(UN_LOCODE_IMPROVED_URL, timeout=60)
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text)
    return resp.text


def _classify_source(raw_source: str) -> str:
    """The improved-un-locodes CSV tags every row's coordinate origin in its
    Source column: the literal string "UN/LOCODE" for official coordinates,
    or an OpenStreetMap URL for gaps it filled (Kaohsiung among them)."""
    if raw_source.strip() == "UN/LOCODE":
        return "UN/LOCODE official"
    return "OSM-filled republication (improved-un-locodes)"


def resolve_ports() -> list[dict]:
    """Resolve ORIGIN_PORTS and US_DESTINATION_PORTS to coordinates via the
    live UN/LOCODE dataset. Returns rows matching port_coordinates.csv."""
    by_code = {
        (row["Country"], row["Location"]): row
        for row in csv.DictReader(io.StringIO(_fetch_un_locode_text()))
    }

    def resolve(country: str, location: str, name: str, iso3: str, role: str) -> dict:
        row = by_code.get((country, location))
        if row is None or not row.get("CoordinatesDecimal"):
            raise RuntimeError(
                f"No coordinates for {country}{location} ({name}) in the "
                "UN/LOCODE dataset. Pick a different port code for this origin."
            )
        lat_str, lon_str = row["CoordinatesDecimal"].split(",")
        return {
            "locode": f"{country}{location}",
            "port_name": name,
            "country_iso3": iso3,
            "latitude": float(lat_str),
            "longitude": float(lon_str),
            "source": _classify_source(row.get("Source", "")),
            "role": role,
        }

    ports = [
        resolve(country, location, name, iso3, "origin")
        for country, location, name, iso3 in ORIGIN_PORTS
    ]
    ports += [
        resolve(country, location, name, iso3, "us_destination")
        for country, location, name, iso3, _coast in US_DESTINATION_PORTS
    ]
    return ports


def _normalize_lon(lon: float) -> float:
    """searoute can return longitudes past 180 for antimeridian-crossing
    routes (e.g. 241.8 instead of -118.2); wrap back to [-180, 180] before
    handing coordinates to pyproj."""
    return ((lon + 180) % 360) - 180


def _build_aeqd_transformer(lat: float, lon: float) -> pyproj.Transformer:
    """Azimuthal equidistant projection centered on (lat, lon). One of these
    per chokepoint is reused across every route tested against it, rather
    than rebuilt per route: CRS/transformer construction is the expensive
    part, not transforming a handful of coordinates through it."""
    aeqd = pyproj.CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m")
    return pyproj.Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)


def _nearest_point_on_line_distance_km(
    transformer: pyproj.Transformer, route_coords: list[list[float]]
) -> float:
    """True minimum distance from the chokepoint (at the projection origin)
    to the route LINE, not to its nearest vertex. See module docstring."""
    projected = [
        transformer.transform(_normalize_lon(lon), lat) for lon, lat in route_coords
    ]
    line = LineString(projected)
    return line.distance(Point(0.0, 0.0)) / 1000.0


def build_routing_matrix(
    chokepoints: list[dict],
    ports: list[dict],
    threshold_km: float = DEFAULT_THRESHOLD_KM,
) -> list[dict]:
    """One row per origin x US destination x chokepoint. Every combination,
    crossings and non-crossings alike."""
    origins = [p for p in ports if p["role"] == "origin"]
    dest_coast = {
        f"{country}{location}": coast
        for country, location, _name, _iso3, coast in US_DESTINATION_PORTS
    }
    destinations = [p for p in ports if p["role"] == "us_destination"]

    transformers = {
        cp["portid"]: _build_aeqd_transformer(cp["lat"], cp["lon"]) for cp in chokepoints
    }

    rows = []
    for origin in origins:
        for dest in destinations:
            route = sr.searoute(
                [origin["longitude"], origin["latitude"]],
                [dest["longitude"], dest["latitude"]],
                units="km",
            )
            route_coords = route["geometry"]["coordinates"]

            for cp in chokepoints:
                min_distance_km = _nearest_point_on_line_distance_km(
                    transformers[cp["portid"]], route_coords
                )
                rows.append(
                    {
                        "origin_locode": origin["locode"],
                        "origin_country_iso3": origin["country_iso3"],
                        "destination_locode": dest["locode"],
                        "us_coast": dest_coast[dest["locode"]],
                        "portid": cp["portid"],
                        "chokepoint_name": cp["portname"],
                        "crosses": 1 if min_distance_km <= threshold_km else 0,
                        "min_distance_km": round(min_distance_km, 3),
                        "threshold_km": threshold_km,
                    }
                )
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_port_coordinates(ports: list[dict]) -> Path:
    path = REFERENCE_DIR / "port_coordinates.csv"
    _write_csv(
        path,
        ["locode", "port_name", "country_iso3", "latitude", "longitude", "source", "role"],
        ports,
    )
    return path


def write_chokepoint_coordinates(chokepoints: list[dict]) -> Path:
    path = REFERENCE_DIR / "chokepoint_coordinates.csv"
    rows = [
        {
            "portid": cp["portid"],
            "chokepoint_name": cp["portname"],
            "latitude": cp["lat"],
            "longitude": cp["lon"],
            "source": "IMF PortWatch chokepoints database (ArcGIS FeatureServer)",
        }
        for cp in chokepoints
    ]
    _write_csv(
        path,
        ["portid", "chokepoint_name", "latitude", "longitude", "source"],
        rows,
    )
    return path


def write_routing_matrix(rows: list[dict]) -> Path:
    path = REFERENCE_DIR / "routing_matrix.csv"
    _write_csv(
        path,
        [
            "origin_locode",
            "origin_country_iso3",
            "destination_locode",
            "us_coast",
            "portid",
            "chokepoint_name",
            "crosses",
            "min_distance_km",
            "threshold_km",
        ],
        rows,
    )
    return path


def _validate(rows: list[dict]) -> None:
    expected = len(ORIGIN_PORTS) * len(US_DESTINATION_PORTS) * EXPECTED_CHOKEPOINT_COUNT
    if len(rows) != expected:
        raise RuntimeError(
            f"routing_matrix has {len(rows)} rows, expected {expected} "
            f"({len(ORIGIN_PORTS)} origins x {len(US_DESTINATION_PORTS)} "
            f"destinations x {EXPECTED_CHOKEPOINT_COUNT} chokepoints)."
        )

    hormuz_crossings = sum(
        r["crosses"] for r in rows if r["chokepoint_name"] == HORMUZ_NAME
    )
    if hormuz_crossings != 0:
        raise RuntimeError(
            f"{HORMUZ_NAME} shows {hormuz_crossings} crossing(s) in the computed "
            "routing matrix, but docs/07_assumptions_limitations.md records zero "
            "of 30 tested routes crossing it. Investigate before committing this "
            "output: either the finding changed or the computation regressed."
        )


def main() -> None:
    print("Fetching PortWatch chokepoint geometry...")
    chokepoints = fetch_chokepoints()
    print(f"  {len(chokepoints)} chokepoints")

    print("Resolving port coordinates from UN/LOCODE...")
    ports = resolve_ports()
    print(f"  {len(ports)} ports")

    n_origins = len(ORIGIN_PORTS)
    n_dests = len(US_DESTINATION_PORTS)
    print(f"Computing {n_origins} x {n_dests} sea routes against {len(chokepoints)} chokepoints...")
    rows = build_routing_matrix(chokepoints, ports)
    print(f"  {len(rows)} routing_matrix rows")

    _validate(rows)
    print("Validated: 840 rows, Strait of Hormuz has 0 crossings.")

    port_path = write_port_coordinates(ports)
    chokepoint_path = write_chokepoint_coordinates(chokepoints)
    matrix_path = write_routing_matrix(rows)
    for path in (port_path, chokepoint_path, matrix_path):
        print(f"Wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
