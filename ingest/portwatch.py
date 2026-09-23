"""IMF PortWatch ingest: chokepoint geometry, daily chokepoint transits, the
ports database, and the disruptions database, all from the ArcGIS
FeatureServer (no key). URLs and service names come from ingest/config.py;
no URL is defined here.

Four pulls:
  1. Chokepoints database -> data/raw/portwatch_chokepoints_geometry.json.
     Single fetch, not paginated.
  2. Daily chokepoint transits -> data/raw/portwatch_full_offset{N}.json.
     Paginated, page size 1000, ordered portid ASC, date ASC.
  3. Ports database -> data/raw/portwatch_ports_database_offset{N}.json.
     Paginated, page size 1000, ordered ObjectId ASC.
  4. Disruptions database -> data/raw/portwatch_disruptions_offset{N}.json.
     Paginated, page size 1000, ordered ObjectId ASC, geometry included.

Every pull requests outFields=* -- no field allowlist is maintained here.

Both paginated pulls share the same pagination and durability contract:
  - A fresh pull first calls returnCountOnly=true to learn the expected row
    count, then walks pages from offset 0, stopping at the first page under
    1000 rows. The rows actually fetched must equal the returnCountOnly
    total, or this raises. A hard page cap guards against an infinite loop
    if the source never returns a short page.
  - Pages are written into data/raw/.tmp_<prefix>/ as they're fetched, never
    directly into data/raw/. Only once the fetched total matches the
    returnCountOnly count are the pages moved into data/raw/ (replacing any
    pages already cached there for that prefix) and the temp dir removed.
    Any failure along the way -- a bad response, a count mismatch, the page
    cap -- deletes the temp dir before raising. Nothing partial ever lands
    in data/raw/.
  - A cached rerun (page 0 already on disk, and --refresh not given for
    this pull) makes no network calls at all. It still validates that
    cached offsets are contiguous multiples of 1000 from 0 and that the
    last cached page holds under 1000 rows -- if not, the cache may be an
    interrupted fresh pull, and this raises rather than silently trusting a
    partial cache.
  - Any response that is non-200, or whose JSON body carries an "error" key
    (ArcGIS returns errors inside HTTP 200 bodies), raises before anything
    is written to disk.

Every network call is counted, including the returnCountOnly probe, and the
count is reported per pull.

--refresh <chokepoints|transits|ports|disruptions|all> ignores the cache
for the named pull(s), fetches fresh into the temp dir/file, and replaces
the cached files only once the fetch validates. A failed --refresh leaves
the existing cache untouched. Without --refresh, a pull with a valid cache
makes zero calls.

Usage: .venv/bin/python -m ingest.portwatch [--refresh {chokepoints,transits,ports,disruptions,all}]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import (  # noqa: E402
    PORTWATCH_ARCGIS_BASE,
    PORTWATCH_CHOKEPOINTS_SERVICE,
    PORTWATCH_DAILY_TRANSITS_SERVICE,
    PORTWATCH_DISRUPTIONS_SERVICE,
    PORTWATCH_PORTS_SERVICE,
)

CACHE_DIR = REPO_ROOT / "data" / "raw"
PAGE_SIZE = 1000
MAX_PAGES = 500  # hard cap; largest known pull (daily transits) is 79 pages


class PortwatchError(RuntimeError):
    """Raised on a non-200 response, an ArcGIS error body, a page-count
    mismatch against returnCountOnly, a non-contiguous cache, or the hard
    page cap being hit."""


def _service_url(service: str, layer: int = 0) -> str:
    return f"{PORTWATCH_ARCGIS_BASE}/{service}/FeatureServer/{layer}/query"


def _get_json(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=120)
    if resp.status_code != 200:
        raise PortwatchError(f"{url} returned HTTP {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    if "error" in payload:
        raise PortwatchError(f"{url} returned an ArcGIS error body: {payload['error']}")
    return payload


# ---------------------------------------------------------------------------
# 1. Chokepoints database (single fetch, not paginated)
# ---------------------------------------------------------------------------


def fetch_chokepoints(force: bool = False) -> tuple[Path, int]:
    """Chokepoint point geometry. Returns (cache_file, api_calls)."""
    cache_file = CACHE_DIR / "portwatch_chokepoints_geometry.json"
    if not force and cache_file.exists():
        return cache_file, 0

    payload = _get_json(
        _service_url(PORTWATCH_CHOKEPOINTS_SERVICE),
        {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "json"},
    )
    if payload.get("exceededTransferLimit"):
        raise PortwatchError(
            "Chokepoints database query returned exceededTransferLimit=true "
            "-- the single-fetch assumption (one page covers every "
            "chokepoint) no longer holds. This pull needs pagination before "
            "it can be trusted."
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CACHE_DIR / ".tmp_portwatch_chokepoints_geometry.json"
    try:
        temp_file.write_text(json.dumps(payload, indent=2))
        temp_file.replace(cache_file)
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise
    return cache_file, 1


# ---------------------------------------------------------------------------
# Paginated pulls (daily transits, ports database, disruptions database)
# ---------------------------------------------------------------------------


def _offset_of(path: Path) -> int:
    return int(path.stem.rsplit("offset", 1)[1])


def _cached_pages(cache_prefix: str) -> list[Path]:
    return sorted(CACHE_DIR.glob(f"{cache_prefix}_offset*.json"), key=_offset_of)


def _validate_cached_pages(cache_prefix: str, pages: list[Path]) -> int:
    """No network. Offsets must be contiguous multiples of PAGE_SIZE from 0,
    and the last page must hold fewer than PAGE_SIZE rows. Returns the total
    row count."""
    total = 0
    last_n = 0
    for i, path in enumerate(pages):
        expected_offset = i * PAGE_SIZE
        if _offset_of(path) != expected_offset:
            raise PortwatchError(
                f"{cache_prefix}: cached pages are not contiguous from 0 "
                f"(expected offset {expected_offset}, found {path.name})."
            )
        n = len(json.loads(path.read_text()).get("features", []))
        if i < len(pages) - 1 and n < PAGE_SIZE:
            raise PortwatchError(
                f"{cache_prefix}: {path.name} holds {n} row(s) (< {PAGE_SIZE}) "
                "but is not the last cached page. Cache may be an interrupted "
                "fresh pull -- delete it and rerun."
            )
        total += n
        last_n = n
    if last_n >= PAGE_SIZE:
        raise PortwatchError(
            f"{cache_prefix}: last cached page {pages[-1].name} holds "
            f"{last_n} row(s) (>= {PAGE_SIZE}), so more pages may exist. "
            "Delete the cache and rerun to pull fresh."
        )
    return total


def _fetch_fresh_pages(cache_prefix: str, url: str, base_params: dict) -> tuple[Path, list[str], int]:
    """Fetch every page into data/raw/.tmp_<cache_prefix>/, validating the
    total against returnCountOnly. Returns (temp_dir, page filenames,
    api_calls) on success, with the temp dir left populated for the caller
    to commit. On any failure the temp dir is deleted before re-raising --
    nothing partial is left behind."""
    temp_dir = CACHE_DIR / f".tmp_{cache_prefix}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    api_calls = 0
    try:
        count_payload = _get_json(url, {**base_params, "returnCountOnly": "true"})
        api_calls += 1
        expected_total = count_payload["count"]

        written: list[str] = []
        fetched_total = 0
        pages_fetched = 0
        offset = 0
        while True:
            if pages_fetched >= MAX_PAGES:
                raise PortwatchError(
                    f"{cache_prefix}: hit the hard page cap of {MAX_PAGES} "
                    f"pages without finishing pagination (fetched "
                    f"{fetched_total} of {expected_total} expected row(s))."
                )
            payload = _get_json(
                url, {**base_params, "resultOffset": offset, "resultRecordCount": PAGE_SIZE}
            )
            api_calls += 1
            pages_fetched += 1
            n = len(payload.get("features", []))
            fetched_total += n

            name = f"{cache_prefix}_offset{offset}.json"
            (temp_dir / name).write_text(json.dumps(payload, indent=2))
            written.append(name)

            if n < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        if fetched_total != expected_total:
            raise PortwatchError(
                f"{cache_prefix}: fetched {fetched_total} row(s) across "
                f"{len(written)} page(s), but returnCountOnly reported "
                f"{expected_total}. Investigate before trusting this cache."
            )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return temp_dir, written, api_calls


def _commit_pages(cache_prefix: str, temp_dir: Path, written: list[str]) -> list[Path]:
    """Move validated pages from the temp dir into data/raw/, replacing any
    pages already cached there for this prefix (including stale extra pages
    from a prior pull that had more of them), then remove the temp dir."""
    old_pages = _cached_pages(cache_prefix)
    new_names = set(written)

    final_paths = []
    for name in written:
        dst = CACHE_DIR / name
        (temp_dir / name).replace(dst)
        final_paths.append(dst)

    for old in old_pages:
        if old.name not in new_names:
            old.unlink()

    temp_dir.rmdir()
    return final_paths


def _paginated_pull(
    cache_prefix: str, url: str, base_params: dict, force: bool = False
) -> tuple[list[Path], int]:
    if not force:
        existing = _cached_pages(cache_prefix)
        if existing:
            _validate_cached_pages(cache_prefix, existing)
            return existing, 0

    temp_dir, written, api_calls = _fetch_fresh_pages(cache_prefix, url, base_params)
    final_paths = _commit_pages(cache_prefix, temp_dir, written)
    return final_paths, api_calls


# ---------------------------------------------------------------------------
# 2. Daily chokepoint transits
# ---------------------------------------------------------------------------


def fetch_daily_transits(force: bool = False) -> tuple[list[Path], int]:
    return _paginated_pull(
        "portwatch_full",
        _service_url(PORTWATCH_DAILY_TRANSITS_SERVICE),
        {"where": "1=1", "outFields": "*", "orderByFields": "portid ASC,date ASC", "f": "json"},
        force=force,
    )


# ---------------------------------------------------------------------------
# 3. Ports database
# ---------------------------------------------------------------------------


def fetch_ports_database(force: bool = False) -> tuple[list[Path], int]:
    return _paginated_pull(
        "portwatch_ports_database",
        _service_url(PORTWATCH_PORTS_SERVICE),
        {
            "where": "1=1",
            "outFields": "*",
            "outSR": 4326,
            "orderByFields": "ObjectId ASC",
            "f": "json",
        },
        force=force,
    )


# ---------------------------------------------------------------------------
# 4. Disruptions database
# ---------------------------------------------------------------------------


def fetch_disruptions(force: bool = False) -> tuple[list[Path], int]:
    return _paginated_pull(
        "portwatch_disruptions",
        _service_url(PORTWATCH_DISRUPTIONS_SERVICE),
        {
            "where": "1=1",
            "outFields": "*",
            "outSR": 4326,
            "orderByFields": "ObjectId ASC",
            "f": "json",
        },
        force=force,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        choices=["chokepoints", "transits", "ports", "disruptions", "all"],
        help="Ignore the cache for this pull, fetch fresh, and replace the "
        "cached files only once the fetch validates.",
    )
    args = parser.parse_args()

    def refresh(name: str) -> bool:
        return args.refresh in (name, "all")

    print("1. Chokepoints database...")
    chokepoints_file, calls = fetch_chokepoints(force=refresh("chokepoints"))
    print(f"  {chokepoints_file.relative_to(REPO_ROOT)}: {calls} API call(s)")

    print("2. Daily chokepoint transits...")
    transit_files, calls = fetch_daily_transits(force=refresh("transits"))
    print(f"  {len(transit_files)} page(s): {calls} API call(s)")

    print("3. Ports database...")
    port_files, calls = fetch_ports_database(force=refresh("ports"))
    print(f"  {len(port_files)} page(s): {calls} API call(s)")

    print("4. Disruptions database...")
    disruption_files, calls = fetch_disruptions(force=refresh("disruptions"))
    print(f"  {len(disruption_files)} page(s): {calls} API call(s)")

    print("Done.")


if __name__ == "__main__":
    main()
