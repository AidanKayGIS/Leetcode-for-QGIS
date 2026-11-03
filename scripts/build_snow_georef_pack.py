#!/usr/bin/env python3
"""Build the John Snow GeoCode training GeoPackage and georeferencing ZIP.

Source: Robin Wilson's updated SnowGIS_v2.zip archive (2012),
https://blog.rtwilson.com/updated-snow-gis-data/
Historical scan: John Snow (1855), public domain, Wikimedia Commons.
"""
import shutil
import sqlite3
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from osgeo import gdal, ogr

gdal.UseExceptions()
ogr.UseExceptions()
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/challenge-01"
OUT.mkdir(parents=True, exist_ok=True)
GPKG = OUT / "snow_cholera_georeferencing.gpkg"
ZIP = OUT / "snow_cholera_georeferencing.zip"
DATA_URL = "https://www.rtwilson.com/downloads/SnowGIS_v2.zip"
MAP_URL = "https://upload.wikimedia.org/wikipedia/commons/2/27/Snow-cholera-map-1.jpg"

def fetch(url, target):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 GeoCode-QGIS/1.0"})
    with urlopen(req, timeout=180) as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    if target.stat().st_size < 1024:
        raise RuntimeError(f"Downloaded file too small: {url}")

def cmd(*args):
    print("RUN", " ".join(map(str,args)), flush=True)
    subprocess.run([str(a) for a in args], check=True)

def main():
    for p in (GPKG, ZIP):
        p.unlink(missing_ok=True)
    with TemporaryDirectory() as d:
        tmp = Path(d)
        archive = tmp / "snowgis-source.zip"
        fetch(DATA_URL, archive)
        with ZipFile(archive) as z:
            z.extractall(tmp / "src")
        src = tmp / "src"
        files = list(src.rglob("*"))
        print("Source file names:", [p.name for p in files if p.is_file()])
        def find_file(stem, ext):
            matches = [p for p in files if p.is_file() and p.stem.lower() == stem.lower() and p.suffix.lower() == ext]
            if not matches:
                raise RuntimeError(f"Missing required publisher file {stem}{ext}")
            return matches[0]
        deaths = find_file("Cholera_Deaths", ".shp")
        pumps = find_file("Pumps", ".shp")
        osm = find_file("OSMap_Grayscale", ".tif")
        # Publisher-provided death and pump geometries are in EPSG:27700.
        for i,(path,name) in enumerate(((deaths,"cholera_deaths"),(pumps,"water_pumps"))):
            args = ["ogr2ogr", "-f", "GPKG", str(GPKG), str(path), "-nln", name, "-t_srs", "EPSG:27700", "-lco", "SPATIAL_INDEX=YES"]
            if i: args.insert(1,"-update")
            cmd(*args)
        # Include other vector layers from the historical package where present.
        for name in ("polys", "CholeraPolygons"):
            matching = [p for p in files if p.is_file() and p.stem.lower()==name.lower() and p.suffix.lower()==".shp"]
            if matching:
                cmd("ogr2ogr","-update","-f","GPKG",str(GPKG),str(matching[0]),"-nln","historical_blocks","-t_srs","EPSG:27700")
                break

        # A real tiled GeoPackage raster, not a web-tile link that requires internet.
        raster = gdal.Open(str(osm))
        if raster is None or raster.RasterCount == 0:
            raise RuntimeError("Publisher OS raster could not be opened")
        if not raster.GetProjection():
            raise RuntimeError("Publisher OS raster is missing georeferencing")
        print("OS raster size", raster.RasterXSize, raster.RasterYSize)
        scale = min(1.0, 1900/max(raster.RasterXSize,raster.RasterYSize))
        opts = gdal.TranslateOptions(format="GPKG",
            width=max(1,round(scale*raster.RasterXSize)),
            height=max(1,round(scale*raster.RasterYSize)),
            creationOptions=["APPEND_SUBDATASET=YES","RASTER_TABLE=soho_basemap","TILE_FORMAT=JPEG","QUALITY=82"])
        gdal.Translate(str(GPKG),raster,options=opts)
        raster = None

        original = tmp / "snow-original.jpg"
        fetch(MAP_URL,original)
        raw = tmp / "john_snow_1855_unreferenced.jpg"
        with Image.open(original) as image:
            image = image.convert("RGB")
            image.thumbnail((2600,2600))
            image.save(raw,format="JPEG",quality=88,optimize=True)
        # Store an image BLOB as an extra non-spatial table. QGIS needs the loose
        # JPG in the ZIP for its georeferencing task, not a prewarped layer.
        with sqlite3.connect(GPKG) as db:
            db.execute("CREATE TABLE challenge_assets (name TEXT PRIMARY KEY, media_type TEXT, source_url TEXT, description TEXT, image BLOB)")
            db.execute("INSERT INTO challenge_assets VALUES (?,?,?,?,?)",
                (raw.name,"image/jpeg",MAP_URL,
                "John Snow's original map scan: deliberately UNREFERENCED. Extract ZIP JPG to use QGIS Georeferencer.",
                sqlite3.Binary(raw.read_bytes())))
            db.execute("CREATE TABLE geocode_attribution (layer_name TEXT, source TEXT, notes TEXT)")
            db.executemany("INSERT INTO geocode_attribution VALUES (?,?,?)", [
                ("cholera_deaths / water_pumps", "Robin Wilson, SnowGIS_v2", DATA_URL),
                ("soho_basemap", "OSMap_Grayscale.tif in Robin Wilson, SnowGIS_v2",
                "Contains Ordnance Survey data © Crown copyright and database right 2013."),
                ("challenge_assets historical map", "John Snow (1855), public domain",MAP_URL)
            ])
            contents = db.execute("SELECT table_name, data_type FROM gpkg_contents").fetchall()
            print("GeoPackage layers:", contents)
            assert any(n=="soho_basemap" and typ=="tiles" for n,typ in contents), contents
            assert any(n=="cholera_deaths" for n,_ in contents)
            assert any(n=="water_pumps" for n,_ in contents)

        vector = ogr.Open(str(GPKG))
        for name in ("cholera_deaths","water_pumps"):
            lyr = vector.GetLayerByName(name)
            if lyr is None or lyr.GetFeatureCount() < 5:
                raise RuntimeError("Incomplete dataset layer: "+name)
            print(name,"features",lyr.GetFeatureCount())
        vector = None
        readme = """GeoCode 01: John Snow's Ghost Map (1854) — QGIS Training Pack

snow_cholera_georeferencing.gpkg:
- cholera_deaths — historical death locations (counts must be used as weights)
- water_pumps — digitised pump locations
- soho_basemap — modern Ordnance Survey grayscale reference raster
- challenge_assets — original image embedded as an SQLite BLOB
- geocode_attribution — data provenance

john_snow_1855_unreferenced.jpg:
- UNREFERENCED scan of John Snow's historical map.
- Do not try to georeference the already-referenced modern raster.

Instructions:
1. Add the .gpkg to QGIS and load cholera_deaths, water_pumps and the soho_basemap raster.
2. Set project CRS to EPSG:27700 (British National Grid).
3. Open the separate unreferenced JPG in QGIS Georeferencer.
4. Identify at least six clear junctions that remain recognisable today.
5. Select Polynomial 1 (affine) transformation as a starting point.
6. Use EPSG:27700, run the transformation and save an output GeoTIFF.
7. Review GCP residuals, alignment and streets changed since 1854.

Data: Robin Wilson (2012) https://www.rtwilson.com/downloads/SnowGIS_v2.zip
Modern basemap: Ordnance Survey data © Crown copyright and database right 2013.
Historical map: John Snow (1855), public domain, via Wikimedia Commons.
"""
        with ZipFile(ZIP, "w", ZIP_DEFLATED, compresslevel=6) as z:
            z.write(GPKG,GPKG.name)
            z.write(raw,raw.name)
            z.writestr("README.txt",readme)
        with ZipFile(ZIP) as z:
            bad = z.testzip()
            if bad: raise RuntimeError("ZIP integrity check failed: "+bad)
        print("SUCCESS", GPKG.stat().st_size, ZIP.stat().st_size, flush=True)

if __name__ == "__main__":
    main()
