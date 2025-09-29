#!/usr/bin/env python3
import argparse
import json
import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
from datetime import datetime


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
    """Try to parse datetime from a filename using multiple strategies."""
    # Strip extension
    name = re.sub(r"\.[^.]+$", "", filename)

    # Try direct formats
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(name, fmt)
        except ValueError:
            pass

    # Try scanning substrings of digits
    digit_chunks = re.findall(r"\d{6,14}", name)
    for chunk in digit_chunks:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(chunk, fmt)
            except ValueError:
                continue

    # Fallback
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

        item_id = dt.strftime("%Y-%m-%d")

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


def validate_geoparquet(path):
    """Validate GeoParquet for STAC-like schema."""
    try:
        gdf = gpd.read_parquet(path)
    except Exception as e:
        print(f"❌ Failed to read {path}: {e}")
        return False

    all_ok = True

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in gdf.columns:
            print(f"❌ Missing required column: {field}")
            all_ok = False

    # Row-level validation
    for idx, row in gdf.iterrows():
        # Assets must be dict with href + type
        assets = row.get("assets", {})
        if not isinstance(assets, dict):
            print(f"❌ Row {idx}: 'assets' is not a dict")
            all_ok = False
        else:
            for k, v in assets.items():
                if not isinstance(v, dict) or "href" not in v or "type" not in v:
                    print(f"❌ Row {idx}: Asset {k} missing href/type")
                    all_ok = False

        # Links must be list of dicts
        links = row.get("links", [])
        if not isinstance(links, list):
            print(f"❌ Row {idx}: 'links' is not a list")
            all_ok = False
        else:
            for l in links:
                if not isinstance(l, dict) or "rel" not in l or "href" not in l:
                    print(f"❌ Row {idx}: Invalid link structure")
                    all_ok = False

    if all_ok:
        print(f"✅ {path} is valid")
    else:
        print(f"⚠️ {path} has validation errors")

    return all_ok


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
