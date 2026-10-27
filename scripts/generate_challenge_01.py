"""Generate fictional GeoCode Challenge 01 GIS data (EPSG:27700)."""
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box
OUT = Path(__file__).resolve().parent / "data/challenge-01/park_access_sample.gpkg"
OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists(): OUT.unlink()
x0,y0=328000,433000
zones=[]
for j in range(6):
    for i in range(6):
        zones.append({"zone_id":f"Z{j+1:02d}{i+1:02d}","population":140+((i*83+j*127+i*j*29)%460),"geometry":box(x0+i*400,y0+j*400,x0+(i+1)*400,y0+(j+1)*400)})
parks_data=[("P01","North Gardens",2.4,4.5,.65,.52),("P02","Central Common",3.1,2.6,.75,.8),("P03","West Meadow",.7,1.6,.55,.68),("P04","Eastern Park",4.7,.8,.65,.72),("P05","Riverside Green",1.,4.1,.5,.6)]
parks=[{"park_id":pid,"name":name,"type":"Public park","geometry":box(x0+x*400,y0+y*400,x0+(x+w)*400,y0+(y+h)*400)} for pid,name,x,y,w,h in parks_data]
gpd.GeoDataFrame(zones,crs="EPSG:27700").to_file(OUT,layer="population_areas",driver="GPKG")
gpd.GeoDataFrame(parks,crs="EPSG:27700").to_file(OUT,layer="parks",driver="GPKG",mode="a")
print(OUT,OUT.stat().st_size)
