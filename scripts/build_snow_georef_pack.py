#!/usr/bin/env python3
"""Build GeoCode's John Snow georeferencing challenge pack from publicly published sources.
Executed on GitHub Actions; not a substitute for checking source data attribution.
"""
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED
from tempfile import TemporaryDirectory
import os, shutil, sqlite3, subprocess, json

from osgeo import gdal, ogr
from PIL import Image

gdal.UseExceptions()
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/challenge-01"
DEST.mkdir(parents=True, exist_ok=True)
GPKG = DEST / "snow_cholera_georeferencing.gpkg"
PACK = DEST / "snow_cholera_georeferencing.zip"
SOURCE = "https://johnsnow.rtwilson.com/data/SnowGIS_GPKG.zip"
MAP = "https://upload.wikimedia.org/wikipedia/commons/2/27/Snow-cholera-map-1.jpg"

def download(url, path):
    req = Request(url, headers={"User-Agent": "GeoCode-QGIS-open-education/1.0 (+https://github.com/AidanKayGIS/Leetcode-for-QGIS)"})
    with urlopen(req, timeout=180) as r, open(path, "wb") as o:
        shutil.copyfileobj(r, o)
    if path.stat().st_size < 1000: raise RuntimeError("Unexpectedly small downloaded file: " + str(path))

def run(*args):
    print("+", " ".join(str(x) for x in args), flush=True)
    subprocess.run([str(x) for x in args], check=True)

def source_vector_layers(src):
    ds = ogr.Open(str(src))
    if ds is None: return []
    names = [ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount())]
    ds = None
    return names

def append_raster(source, table):
    ds = gdal.Open(str(source))
    if ds is None: raise RuntimeError("Could not read raster " + str(source))
    if ds.RasterCount == 0 and ds.GetSubDatasets():
        sub = ds.GetSubDatasets()
        # Prefer an explicitly named OS/street basemap, where present.
        chosen = next((s[0] for s in sub if any(k in (s[0]+s[1]).lower() for k in ("os", "street", "basemap"))), sub[0][0])
        ds = gdal.Open(chosen)
    if ds is None or ds.RasterCount == 0: raise RuntimeError("No raster bands " + str(source))
    opts = ["RASTER_TABLE=" + table, "APPEND_SUBDATASET=YES", "TILE_FORMAT=JPEG", "QUALITY=80"]
    out = gdal.Translate(str(GPKG), ds, format="GPKG", creationOptions=opts, width=min(1600, ds.RasterXSize), resampleAlg="bilinear")
    if out is None: raise RuntimeError("GDAL raster append failed")
    out = None
    ds = None

def main():
  if GPKG.exists(): GPKG.unlink()
  if PACK.exists(): PACK.unlink()
  with TemporaryDirectory() as temp:
    t = Path(temp)
    zpath = t / "source.zip"
    download(SOURCE, zpath)
    with ZipFile(zpath) as z: z.extractall(t / "source")
    files = [p for p in (t/"source").rglob("*") if p.is_file()]
    print("Source archive files:", [str(p.relative_to(t/"source")) for p in files])
    gpkg_sources = [p for p in files if p.suffix.lower()==".gpkg"]
    if not gpkg_sources: raise RuntimeError("Publisher's ZIP did not contain a GeoPackage")
    src = gpkg_sources[0]
    layers = source_vector_layers(src)
    print("Vector layers", layers)
    if not layers: raise RuntimeError("No vector layers in publisher GeoPackage")
    for i, name in enumerate(layers):
        cmd=["ogr2ogr", "-f", "GPKG", str(GPKG), str(src), name, "-nln", name, "-lco", "SPATIAL_INDEX=YES"]
        if i: cmd.insert(1, "-update")
        run(*cmd)
    # Prefer street rasters in the archive; if only embedded in the source GPKG, use that.
    rasters = [p for p in files if p.suffix.lower() in (".tif", ".tiff")]
    street = next((p for p in rasters if any(w in p.name.lower() for w in ("street", "osmap", "os_", "basemap", "modern"))), None)
    if street:
        append_raster(street,"soho_basemap")
        source_basemap=str(street.relative_to(t/"source"))
    else:
        source_raster=gdal.Open(str(src))
        if source_raster and (source_raster.RasterCount or source_raster.GetSubDatasets()):
            append_raster(src,"soho_basemap")
            source_basemap="publisher GeoPackage raster"
        else:
            raise RuntimeError("No publisher basemap raster found; refusing to label unrelated layers as a basemap")
    jpg = t/"john_snow_1855_unreferenced.jpg"
    try:
        original=t/"snow_source.jpg"
        download(MAP, original)
        with Image.open(original) as im:
            im.convert("RGB").thumbnail((2400,2400))
            im=Image.open(original).convert("RGB")
            im.thumbnail((2400,2400))
            im.save(jpg, quality=90, optimize=True)
        image_origin=MAP
    except Exception as ex:
        print("Original image download failed; using non-georeferenced pixels from publisher historical raster:",ex)
        candidate=next((p for p in rasters if any(w in p.name.lower() for w in ("snowmap","snow_map","historic","cholera_map"))),None)
        if candidate is None: raise RuntimeError("Missing raw historical map image")
        with Image.open(candidate) as im:
            im=im.convert("RGB"); im.thumbnail((2400,2400)); im.save(jpg,quality=90,optimize=True)
        image_origin=str(candidate.relative_to(t/"source"))
    # An image embedded as a SQLite BLOB is an asset within the GPKG, deliberately
    # NOT a georeferenced raster layer. Georeferencer operates on the loose JPG in ZIP.
    con=sqlite3.connect(GPKG)
    con.execute("CREATE TABLE challenge_assets (name TEXT PRIMARY KEY, media_type TEXT NOT NULL, description TEXT NOT NULL, source_url TEXT NOT NULL, image BLOB NOT NULL)")
    con.execute("INSERT INTO challenge_assets VALUES (?,?,?,?,?)",(
        jpg.name, "image/jpeg",
        "John Snow historical map scan — NO georeferencing. Extract from archive to align in QGIS.",
        image_origin, sqlite3.Binary(jpg.read_bytes())))
    con.execute("CREATE TABLE geocode_attribution (resource TEXT, source TEXT, note TEXT)")
    con.executemany("INSERT INTO geocode_attribution VALUES (?,?,?)", [
        ("Historic features","Robin Wilson, John Snow Cholera Data",SOURCE),
        ("Street basemap","Ordnance Survey OpenData raster supplied by Robin Wilson","Contains OS data © Crown copyright and database right; attribution from publisher archive. Raster source: "+source_basemap),
        ("Original John Snow image","John Snow (1855), via Wikimedia Commons","Public domain; image is intentionally not georeferenced: "+image_origin)
    ])
    con.commit(); con.close()
    readme="""# GeoCode 01 — The Ghost Map: georeferencing pack

Files:
- snow_cholera_georeferencing.gpkg — cholera points, pumps, published reference features, and an Ordnance Survey street basemap as a GPKG raster subdataset (`soho_basemap`). A copy of the unreferenced image is also stored in a SQLite table `challenge_assets`.
- john_snow_1855_unreferenced.jpg — the original historical map image with NO spatial reference. Use this in the QGIS Georeferencer.

## Exercise
1. Drag the GeoPackage into QGIS and choose the feature layers plus the `soho_basemap` raster subdataset.
2. Set project CRS to EPSG:27700 (British National Grid).
3. Open Layer → Georeferencer (or Raster → Georeferencer, depending on QGIS version) and load the **loose JPG**.
4. Add >=6 well-distributed ground control points at street intersections identifiable in BOTH the historic image and the provided basemap. Watch for renamed or realigned streets since 1854.
5. Choose an affine/Polynomial 1 transformation as a starting point, target EPSG:27700, resample and save a *new* GeoTIFF.
6. Review residuals, map alignment and uncertainty. Overlay deaths and pumps on the output; do not use their locations as the sole georeferencing control.
7. Continue with nearest-pump and Voronoi analysis.

The historical image is intentionally **not** georeferenced. The ZIP includes the standalone JPG for QGIS; the bytes are additionally embedded in the GeoPackage's `challenge_assets` SQLite table for archival convenience. The BLOB cannot be opened directly by the Georeferencer.

Attribution: digitised dataset Robin Wilson (https://johnsnow.rtwilson.com/); historical map John Snow (1855), public domain via Wikimedia Commons; street reference Ordnance Survey OpenData included in Wilson's dataset, contains OS data © Crown copyright and database right. The modern street basemap is NOT a map of 1854.
"""
    (t/"README.md").write_text(readme)
    with ZipFile(PACK,"w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        z.write(GPKG,GPKG.name)
        z.write(jpg,jpg.name)
        z.write(t/"README.md","README.md")
    with sqlite3.connect(GPKG) as con:
        print("GPKG contents",con.execute("SELECT table_name,data_type FROM gpkg_contents").fetchall())
    print("Created",GPKG,GPKG.stat().st_size,"bytes; pack",PACK,PACK.stat().st_size,"bytes")

if __name__=="__main__": main()
