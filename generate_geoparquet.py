#!/usr/bin/env python3
import argparse
import json
import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
from datetime import datetime, timezone
import collections.abc


REQUIRED_FIELDS = ["id", "datetime", "geometry", "bbox", "assets", "links"]

import re
from datetime import datetime

# Common formats often found in filenames
DATE_FORMATS = [
    "%Y%m%d%H%M",  # e.g. 202501061230
    "%Y%m%d",      # e.g. 20250106
    "%Y-%m-%d",    # e.g. 2025-01-06
    "%Y%m%d_%H%M", # e.g. 20250106_1230
    "%Y-%m-%dT%H%M",  # e.g. 2025-01-06T1230
    "%Y-%m-%dT%H:%M", # e.g. 2025-01-06T12:30
    "%Y-%m-%dT%H:%M:%S", # e.g. 2025-01-06T12:30:45
]

def extract_datetime_from_filename(filename: str) -> datetime:
    """
    Extract datetime from filename, including hour and minute if present.
    Fallback to current UTC if no valid datetime is found.
    """
    # Remove file extension
    name = re.sub(r"\.[^.]+$", "", filename)

    # First try known patterns directly
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(name, fmt)
        except ValueError:
            continue

    # Scan for patterns like YYYYMMDD_HHMM in any part of the filename
    match = re.search(r"(\d{8})[_-](\d{4})", name)
    if match:
        date_part, time_part = match.groups()
        dt_str = date_part + time_part  # e.g., "201907021700"
        try:
            return datetime.strptime(dt_str, "%Y%m%d%H%M")
        except ValueError:
            pass

    # Fallback: scan for just 8-digit date
    match = re.search(r"\d{8}", name)
    if match:
        try:
            return datetime.strptime(match.group(), "%Y%m%d")
        except ValueError:
            pass

    # Last fallback
    return datetime.utcnow()

def load_file_list(args):
    """Load list of files from CLI args, CSV, or JSON."""
    if args.csv:
        df = pd.read_csv(args.csv)
        return df.to_dict(orient="records")
    elif args.json:
        with open(args.json, "r") as f:
            return json.load(f)
    elif args.files:
        return [{"path": f} for f in args.files]
    else:
        raise ValueError("No input provided (files, csv, or json required).")


def infer_asset_type(path: str) -> str:
    """Infer STAC asset type from file extension."""
    ext = os.path.splitext(path.lower())[1]
    if ext == ".fgb":
        return "application/vnd.flatgeobuf"
    elif ext in [".geojson", ".json"]:
        return "application/geo+json"
    elif ext in [".tif", ".tiff", ".cog"]:
        return "image/tiff"
    else:
        return "application/octet-stream"  # fallback


def create_stac_items(file_records, base_url, style_url, bbox=None, asset_type_override=None):
    """Create STAC-like items with geometry, assets, links."""
    items = []

    for i, rec in enumerate(file_records):
        file_path = rec["path"]
        file_name = os.path.basename(file_path)
        asset_href = f"{base_url.rstrip('/')}/{file_name}"

        dt = None
        if "date" in rec and rec["date"]:
            try:
                dt = pd.to_datetime(rec["date"], errors="coerce")
            except Exception:
                dt = None

        if dt is None or pd.isna(dt):
            dt = extract_datetime_from_filename(file_name)
        
        # Force to UTC (timezone aware)
        if dt.tzinfo is None:
            dt.replace(tzinfo=timezone.utc)
        else:
            dt.astimezone(timezone.utc)

        item_id = dt.strftime("%Y-%m-%dT%H%M%SZ")

        # Geometry
        if bbox:
            geom = box(*bbox)
        else:
            geom = box(-180, -90, 180, 90)

        # Infer type or override
        asset_type = asset_type_override or infer_asset_type(file_path)

        assets = {
            "asset_0": {
                "href": asset_href,
                "type": asset_type,
                "roles": ["data"]
            }
        }

        links = []
        if style_url:
            links.append({
                "rel": "style",
                "href": style_url,
                "type": "application/json",
                "asset:keys": list(assets.keys())
            })

        items.append({
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": item_id,
            "geometry": geom,
            "bbox": list(geom.bounds),
            "datetime": dt,
            "assets": assets,
            "links": links
        })

    return gpd.GeoDataFrame(items, geometry="geometry", crs="EPSG:4326")


def validate_geoparquet(path: str) -> bool:
    """
    Validate a STAC-like GeoParquet file.
    """
    gdf = pd.read_parquet(path)
    required_columns = ["id", "datetime", "geometry", "bbox", "assets", "links"]

    valid = True
    for col in required_columns:
        if col not in gdf.columns:
            print(f"❌ Missing required column: {col}")
            valid = False

    for idx, row in gdf.iterrows():
        # Validate assets
        assets = row.get("assets")
        if not isinstance(assets, dict):
            # Try coercion if possible
            if isinstance(assets, collections.abc.Mapping):
                assets = dict(assets)
            else:
                print(f"❌ Row {idx}: 'assets' is not a dict")
                valid = False

        # Validate links
        links = row.get("links")
        if not isinstance(links, list):
            # Try coercion if it's an iterable of dicts
            if isinstance(links, collections.abc.Iterable):
                try:
                    links = list(links)
                except Exception:
                    print(f"❌ Row {idx}: 'links' is not a list")
                    valid = False
            else:
                print(f"❌ Row {idx}: 'links' is not a list")
                valid = False

    if valid:
        print(f"✅ {path} passed validation!")
    else:
        print(f"⚠️ {path} has validation errors")

    return valid


def main():
    parser = argparse.ArgumentParser(description="Generate or validate STAC-like GeoParquet.")
    parser.add_argument("--style-url", help="URL of style.json to link in items")
    parser.add_argument("--base-url", help="Base public URL where files live")
    parser.add_argument("--csv", help="CSV file with input records")
    parser.add_argument("--json", help="JSON file with input records")
    parser.add_argument("files", nargs="*", help="List of input files")
    parser.add_argument("--bbox", nargs=4, type=float,
                        help="Optional bbox as minx miny maxx maxy")
    parser.add_argument("-o", "--output", default="items.parquet",
                        help="Output GeoParquet filename")
    parser.add_argument("--validate", help="Validate an existing GeoParquet file", metavar="FILE")
    parser.add_argument(
        "--asset-type",
        help="Optional override for asset type (applies to all inputs). "
            "Otherwise inferred from file extensions."
    )

    args = parser.parse_args()

    if args.validate:
        validate_geoparquet(args.validate)
    else:
        if not args.base_url:
            raise ValueError("--base-url is required unless --validate is used")
        file_records = load_file_list(args)
        gdf = create_stac_items(
            file_records,
            args.base_url,
            args.style_url,
            args.bbox,
            args.asset_type
        )
        gdf.to_parquet(args.output)
        print(f"✅ GeoParquet written to {args.output}")


if __name__ == "__main__":
    main()
