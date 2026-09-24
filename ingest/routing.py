"""Sea routes from every foreign container port to three US destination ports,
and each route's minimum distance to every PortWatch chokepoint.

Inputs, all local (this script makes no network call):
  - PortWatch ports database, the cached pages of data/raw/
    portwatch_ports_database_offset*.json, validated by
    ingest.portwatch.read_cached_features exactly as a cached portwatch rerun
    validates them.
  - PortWatch chokepoints database, data/raw/
    portwatch_chokepoints_geometry.json, validated by
    ingest.portwatch.validate_chokepoints_payload. Must hold 28 chokepoints.
  - data/reference/manual/us_destination_ports.csv: one PortWatch port per
    coast (west, east, gulf). Destination coordinates come from the ports
    database, not the CSV.

Origins are every port with vessel_count_container > 0 whose ISO3 is not USA
(1,253 ports in 174 countries in the current cache). Each origin is routed
to each destination with searoute (Eurostat marnet, local, default
restrictions, which exclude the Northwest Passage). searoute snaps both ends
to its network and returns the line between the snapped nodes; the port
itself is not appended. Per route this records:
  status          ok, or failed with a reason. A failed route is a row, not
                  a crash. Only invalid inputs raise.
  route_km        searoute's route length.
  origin_snap_km, dest_snap_km
                  great-circle distance from each port to the route's first
                  and last point, i.e. how far searoute moved the port to
                  reach its network. The snap leg is not part of the line.

For each ok route and each chokepoint, min_distance_km is the distance from
the chokepoint to the nearest point on the route LINE, not its nearest
vertex: the route is projected into an azimuthal equidistant projection
centred on the chokepoint, where planar distance from the origin equals
great-circle distance, and shapely measures the line's distance to (0, 0).
searoute returns longitudes past 180 on antimeridian routes (241.8 for
-118.2); these are wrapped to [-180, 180] before projecting. Method ported
from the legacy ingest/reference.py.

No thresholds and no crosses flag: crossing at 50/100/200/300km is computed
in dbt. No port weights either: share_country_maritime_export weighting is
dbt's job. This script only does the geometry.

Outputs of a full run, both written to a temp file then moved into place,
"\\n" line endings, rows sorted by origin_portid (numeric), coast order
west/east/gulf, then chokepoint (numeric):
  data/reference/generated/routes.csv
      origin_portid, origin_iso3, dest_coast, dest_portid, status, reason,
      route_km, origin_snap_km, dest_snap_km
  data/reference/generated/routing_matrix.csv
      origin_portid, dest_coast, dest_portid, chokepoint_id,
      chokepoint_name, min_distance_km   (ok routes only)

--sample N --seed S routes N randomly chosen origins to every destination,
prints timing and a summary, and writes nothing.

Usage: .venv/bin/python -m ingest.routing [--sample N --seed S]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pyproj
import searoute as sr
from shapely.geometry import LineString, Point

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.portwatch import (  # noqa: E402
    CHOKEPOINTS_CACHE_FILE,
    PORTS_CACHE_PREFIX,
    read_cached_features,
    validate_chokepoints_payload,
)

REFERENCE_DIR = REPO_ROOT / "data" / "reference"
US_DESTINATIONS_PATH = REFERENCE_DIR / "manual" / "us_destination_ports.csv"
ROUTES_PATH = REFERENCE_DIR / "generated" / "routes.csv"
ROUTING_MATRIX_PATH = REFERENCE_DIR / "generated" / "routing_matrix.csv"

EXPECTED_CHOKEPOINT_COUNT = 28
COASTS = ("west", "east", "gulf")
US_ISO3 = "USA"
EARTH_RADIUS_KM = 6371.0088
SNAP_FLAG_KM = 100  # summary lists every ok route snapped further than this

ROUTES_HEADER = (
    "origin_portid", "origin_iso3", "dest_coast", "dest_portid", "status",
    "reason", "route_km", "origin_snap_km", "dest_snap_km",
)
MATRIX_HEADER = (
    "origin_portid", "dest_coast", "dest_portid", "chokepoint_id",
    "chokepoint_name", "min_distance_km",
)


class RoutingInputError(RuntimeError):
    """Raised when an input is missing, malformed or inconsistent."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _id_number(portid: str) -> int:
    """Numeric suffix of a PortWatch id ('port664' -> 664, 'chokepoint12'
    -> 12), for a stable natural sort order."""
    digits = portid.lstrip("abcdefghijklmnopqrstuvwxyz")
    if not digits.isdigit():
        raise RoutingInputError(f"Unexpected PortWatch id {portid!r}.")
    return int(digits)


def _check_coords(label: str, lat, lon) -> tuple[float, float]:
    if lat is None or lon is None:
        raise RoutingInputError(f"{label}: missing coordinates.")
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise RoutingInputError(f"{label}: coordinates out of range ({lat}, {lon}).")
    return lat, lon


def load_ports() -> dict[str, dict]:
    """Every PortWatch port, keyed by portid."""
    ports: dict[str, dict] = {}
    for feature in read_cached_features(PORTS_CACHE_PREFIX):
        a = feature["attributes"]
        portid = a["portid"]
        if portid in ports:
            raise RoutingInputError(f"Duplicate portid {portid} in the ports database.")
        lat, lon = _check_coords(portid, a["lat"], a["lon"])
        ports[portid] = {
            "portid": portid,
            "portname": a["portname"],
            "iso3": a["ISO3"],
            "lat": lat,
            "lon": lon,
            "vessel_count_container": a["vessel_count_container"],
        }
    return ports


def select_origins(ports: dict[str, dict]) -> list[dict]:
    """Ports with container traffic outside the US, in portid order."""
    origins = []
    for p in ports.values():
        if p["vessel_count_container"] is None:
            raise RoutingInputError(f"{p['portid']}: vessel_count_container is null.")
        if p["vessel_count_container"] > 0 and p["iso3"] != US_ISO3:
            if not p["iso3"]:
                raise RoutingInputError(f"{p['portid']}: container port with no ISO3.")
            origins.append(p)
    return sorted(origins, key=lambda p: _id_number(p["portid"]))


def load_chokepoints() -> list[dict]:
    """The 28 PortWatch chokepoints, in chokepoint id order."""
    if not CHOKEPOINTS_CACHE_FILE.exists():
        raise RoutingInputError(
            f"{CHOKEPOINTS_CACHE_FILE.name} is not cached. Run "
            "`python -m ingest.portwatch` first."
        )
    payload = json.loads(CHOKEPOINTS_CACHE_FILE.read_text())
    validate_chokepoints_payload(payload)
    chokepoints = []
    for feature in payload["features"]:
        a = feature["attributes"]
        lat, lon = _check_coords(a["portid"], a["lat"], a["lon"])
        chokepoints.append({"id": a["portid"], "name": a["portname"], "lat": lat, "lon": lon})
    if len(chokepoints) != EXPECTED_CHOKEPOINT_COUNT:
        raise RoutingInputError(
            f"Expected {EXPECTED_CHOKEPOINT_COUNT} chokepoints, found {len(chokepoints)}."
        )
    if len({c["id"] for c in chokepoints}) != len(chokepoints):
        raise RoutingInputError("Duplicate chokepoint ids.")
    return sorted(chokepoints, key=lambda c: _id_number(c["id"]))


def load_destinations(ports: dict[str, dict]) -> list[dict]:
    """One US port per coast from the manual CSV, in COASTS order, with
    coordinates from the ports database."""
    with US_DESTINATIONS_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        expected = ["coast", "portid", "portname", "census_port_code", "reason"]
        if reader.fieldnames != expected:
            raise RoutingInputError(
                f"{US_DESTINATIONS_PATH.name}: header {reader.fieldnames}, expected {expected}."
            )
        rows = list(reader)

    by_coast = {}
    for row in rows:
        coast, portid = row["coast"], row["portid"]
        if coast not in COASTS:
            raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: unknown coast {coast!r}.")
        if coast in by_coast:
            raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: coast {coast} listed twice.")
        if not row["reason"].strip():
            raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: {coast} has no reason.")
        port = ports.get(portid)
        if port is None:
            raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: {portid} not in the ports database.")
        if port["iso3"] != US_ISO3:
            raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: {portid} is not a US port.")
        by_coast[coast] = {**port, "coast": coast}

    missing = [c for c in COASTS if c not in by_coast]
    if missing:
        raise RoutingInputError(f"{US_DESTINATIONS_PATH.name}: no port for coast(s) {missing}.")
    return [by_coast[c] for c in COASTS]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _normalize_lon(lon):
    """Wrap longitudes past 180 (searoute, antimeridian routes) back to
    [-180, 180]. Works on scalars and numpy arrays."""
    return ((lon + 180) % 360) - 180


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance on a sphere of mean Earth radius."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(_normalize_lon(lon2 - lon1))
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def build_transformers(chokepoints: list[dict]) -> dict[str, pyproj.Transformer]:
    """One azimuthal equidistant transformer per chokepoint, built once and
    reused for every route: construction is the expensive part."""
    return {
        c["id"]: pyproj.Transformer.from_crs(
            "EPSG:4326",
            pyproj.CRS.from_proj4(f"+proj=aeqd +lat_0={c['lat']} +lon_0={c['lon']} +units=m"),
            always_xy=True,
        )
        for c in chokepoints
    }


def min_distance_km(transformer: pyproj.Transformer, lons: np.ndarray, lats: np.ndarray) -> float:
    """Distance from the chokepoint (the projection origin) to the nearest
    point on the route line."""
    x, y = transformer.transform(lons, lats)
    return LineString(np.column_stack([x, y])).distance(Point(0.0, 0.0)) / 1000.0


def route_one(origin: dict, dest: dict) -> tuple[dict, list[list[float]] | None]:
    """One searoute call. Returns the routes.csv row and the route
    coordinates (None if failed). Never raises on a routing failure."""
    row = {
        "origin_portid": origin["portid"],
        "origin_iso3": origin["iso3"],
        "dest_coast": dest["coast"],
        "dest_portid": dest["portid"],
        "status": "failed",
        "reason": "",
        "route_km": "",
        "origin_snap_km": "",
        "dest_snap_km": "",
    }
    try:
        route = sr.searoute(
            [origin["lon"], origin["lat"]], [dest["lon"], dest["lat"]], units="km"
        )
        coords = route["geometry"]["coordinates"]
        length = route["properties"]["length"]
    except Exception as exc:  # searoute raises assorted types on unroutable input
        row["reason"] = f"searoute {type(exc).__name__}: {str(exc)[:200]}"
        return row, None

    if len(coords) < 2:
        row["reason"] = f"route has {len(coords)} point(s)"
        return row, None
    if not (isinstance(length, (int, float)) and math.isfinite(length)):
        row["reason"] = f"route length {length!r} is not a finite number"
        return row, None

    (first_lon, first_lat), (last_lon, last_lat) = coords[0][:2], coords[-1][:2]
    row.update(
        status="ok",
        route_km=round(length, 3),
        origin_snap_km=round(great_circle_km(origin["lat"], origin["lon"], first_lat, first_lon), 3),
        dest_snap_km=round(great_circle_km(dest["lat"], dest["lon"], last_lat, last_lon), 3),
    )
    return row, coords


def compute(
    origins: list[dict],
    destinations: list[dict],
    chokepoints: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Route every origin to every destination and measure every ok route
    against every chokepoint. Rows come out in the documented sort order
    because origins, destinations and chokepoints arrive sorted."""
    transformers = build_transformers(chokepoints)
    routes, matrix = [], []
    for origin in origins:
        for dest in destinations:
            row, coords = route_one(origin, dest)
            routes.append(row)
            if coords is None:
                continue
            arr = np.asarray(coords, dtype=float)[:, :2]
            lons, lats = _normalize_lon(arr[:, 0]), arr[:, 1]
            for c in chokepoints:
                matrix.append(
                    {
                        "origin_portid": origin["portid"],
                        "dest_coast": dest["coast"],
                        "dest_portid": dest["portid"],
                        "chokepoint_id": c["id"],
                        "chokepoint_name": c["name"],
                        "min_distance_km": round(min_distance_km(transformers[c["id"]], lons, lats), 3),
                    }
                )
    return routes, matrix


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def _write_csv(path: Path, header: tuple[str, ...], rows: list[dict]) -> None:
    """Write via a temp file in the same directory, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".tmp_{path.name}")
    try:
        with temp.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _validate_outputs(routes, matrix, n_origins, n_dests, n_chokepoints) -> None:
    if len(routes) != n_origins * n_dests:
        raise RuntimeError(f"routes has {len(routes)} rows, expected {n_origins * n_dests}.")
    n_ok = sum(r["status"] == "ok" for r in routes)
    if len(matrix) != n_ok * n_chokepoints:
        raise RuntimeError(
            f"routing_matrix has {len(matrix)} rows, expected {n_ok} ok routes x {n_chokepoints}."
        )


def summarize(routes: list[dict], matrix: list[dict], elapsed: float, n_origins_total: int, n_dests: int) -> None:
    ok = [r for r in routes if r["status"] == "ok"]
    failed = [r for r in routes if r["status"] != "ok"]
    per_route = elapsed / len(routes) if routes else float("nan")
    print(f"Routes: {len(routes)} ({len(ok)} ok, {len(failed)} failed), "
          f"{len(matrix)} routing_matrix rows")
    print(f"Elapsed {elapsed:.1f}s, {per_route * 1000:.1f} ms per route (incl. 28 chokepoint distances)")
    full = n_origins_total * n_dests
    print(f"Projected full run: {full} routes, ~{full * per_route / 60:.1f} min")
    for r in failed:
        print(f"  FAILED {r['origin_portid']} ({r['origin_iso3']}) -> {r['dest_coast']}: {r['reason']}")

    for key in ("origin_snap_km", "dest_snap_km", "route_km"):
        vals = sorted(r[key] for r in ok)
        if vals:
            q = statistics.quantiles(vals, n=20, method="inclusive") if len(vals) > 1 else vals * 19
            print(f"{key}: min {vals[0]:.1f}, median {statistics.median(vals):.1f}, "
                  f"p90 {q[17]:.1f}, p95 {q[18]:.1f}, max {vals[-1]:.1f}")

    for key in ("origin_snap_km", "dest_snap_km"):
        far = [r for r in ok if r[key] > SNAP_FLAG_KM]
        print(f"{key} over {SNAP_FLAG_KM}km: {len(far)} route(s)")
        for r in far:
            print(f"  {r['origin_portid']} ({r['origin_iso3']}) -> {r['dest_coast']}: {r[key]:.1f}km")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="Route N random origins; write nothing.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for --sample.")
    args = parser.parse_args()

    ports = load_ports()
    origins = select_origins(ports)
    destinations = load_destinations(ports)
    chokepoints = load_chokepoints()
    print(f"{len(origins)} origin ports in {len({o['iso3'] for o in origins})} countries, "
          f"{len(destinations)} US destinations, {len(chokepoints)} chokepoints")

    if args.sample is not None:
        if not 0 < args.sample <= len(origins):
            raise RoutingInputError(f"--sample must be between 1 and {len(origins)}.")
        chosen = random.Random(args.seed).sample(origins, args.sample)
        run_origins = sorted(chosen, key=lambda p: _id_number(p["portid"]))
        print(f"Sample mode: {len(run_origins)} origins, seed {args.seed}. Nothing is written.")
    else:
        run_origins = origins

    start = time.perf_counter()
    routes, matrix = compute(run_origins, destinations, chokepoints)
    elapsed = time.perf_counter() - start
    _validate_outputs(routes, matrix, len(run_origins), len(destinations), len(chokepoints))
    summarize(routes, matrix, elapsed, len(origins), len(destinations))

    if args.sample is not None:
        return

    _write_csv(ROUTES_PATH, ROUTES_HEADER, routes)
    _write_csv(ROUTING_MATRIX_PATH, MATRIX_HEADER, matrix)
    for path in (ROUTES_PATH, ROUTING_MATRIX_PATH):
        print(f"Wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
