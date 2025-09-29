# STAC-like GeoParquet Generator

This Python script helps you generate **STAC-like items** in a **GeoParquet** file from a list of geospatial files (`.fgb`, `.geojson`, `.tif`/`.cog`).

It supports:

* Automatic extraction of **datetime from filenames**.
* **Mandatory style link** for STAC Browser or web clients.
* Inferring **asset types** from file extensions, with an optional override.
* Optional **bounding box** for geometry.
* Validation of existing GeoParquet files to check structure and required fields.

---

## Features

* Input formats: FlatGeobuf (`.fgb`), GeoJSON (`.geojson`), Cloud Optimized GeoTIFF (`.tif`, `.tiff`, `.cog`)
* Auto-merge assets by day (optional)
* Asset key reindexing (`asset_0`, `asset_1`, …) to avoid nulls
* Validation of required fields: `id`, `datetime`, `geometry`, `bbox`, `assets`, `links`
* STAC-compatible structure

---

## Requirements

Python 3.11+ and the following libraries:

```txt
numpy==1.24.4
pandas==2.0.0
geopandas==1.0.1
shapely==2.0.7
pyarrow==12.0.0
```

Install in a clean environment:

```bash
python -m venv myenv
source myenv/bin/activate  # Windows: myenv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Usage

### Generate GeoParquet from file list

```bash
python generate_geoparquet.py \
  --style-url "https://raw.githubusercontent.com/gtif-cerulean/assets/main/style.json" \
  --base-url "https://your-bucket.example.com/daily" \
  file1.fgb file2.geojson file3.tif \
  -o items.parquet
```

> **Note:** `--style-url` needs to be provided in order for eodash to visulize the data

### Generate GeoParquet from CSV

CSV must contain at least a `path` column. Optionally, include `date`.

```bash
python generate_geoparquet.py \
  --style-url "https://raw.githubusercontent.com/gtif-cerulean/assets/main/style.json" \
  --base-url "https://your-bucket.example.com/daily" \
  --csv input_files.csv \
  -o items.parquet
```

### Generate GeoParquet from JSON

JSON should be a list of objects with a `path` key:

```bash
python generate_geoparquet.py \
  --style-url "https://raw.githubusercontent.com/gtif-cerulean/assets/main/style.json" \
  --base-url "https://your-bucket.example.com/daily" \
  --json input_files.json \
  -o items.parquet
```

### Optional: Specify bounding box

```bash
python generate_geoparquet.py \
  --bbox -10 40 10 60 \
  --style-url "https://raw.githubusercontent.com/gtif-cerulean/assets/main/style.json" \
  --base-url "https://your-bucket.example.com/daily" \
  file1.fgb file2.geojson
```

### Optional: Override asset type

```bash
python generate_geoparquet.py \
  --asset-type "image/tiff; application=geotiff; profile=cloud-optimized" \
  --style-url "https://raw.githubusercontent.com/gtif-cerulean/assets/main/style.json" \
  --base-url "https://your-bucket.example.com/daily" \
  daily_20250106.cog
```

---

## Validate Existing GeoParquet

Check if the GeoParquet file contains all required fields and correct structure:

```bash
python generate_geoparquet.py --validate items.parquet
```

Output will indicate missing columns or malformed assets/links.

---

## Date Extraction

The script attempts to parse datetime from filenames automatically. Supported formats include:

* `YYYYMMDD` (e.g., `20250106`)
* `YYYY-MM-DD` (e.g., `2025-01-06`)
* `YYYYMMDDHHMM` (e.g., `202501061230`)
* `YYYY-MM-DDTHHMM` or `YYYY-MM-DDTHH:MM:SS` (e.g., `2025-01-06T12:30:45`)

If no date is found, it falls back to **current UTC time**.

---

## Notes

* Each input file becomes a STAC item with `asset_0`. Multiple files per day can be merged manually or via workflow.
* Asset keys are reindexed to avoid `null` fields when saving to GeoParquet.
* **Style link are required** in order for eodash to visulize the assets correctly.

