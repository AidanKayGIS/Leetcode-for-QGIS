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


# Fictional basemap for offline QGIS learning (not actual streets)
from shapely.geometry import LineString, Point
landuse=[]
for j in range(6):
    for i in range(6):
        kind=['Residential','Residential','Mixed use','Residential','Commercial','Residential'][(i*3+j*5)%6]
        landuse.append({'feature_id':f'B{i+1:02d}{j+1:02d}','land_use':kind,'geometry':box(x0+i*400+38,y0+j*400+38,x0+(i+1)*400-38,y0+(j+1)*400-38)})
roads=[]
for i in range(7):
    x=x0+i*400
    roads.append({'road_id':f'NS{i+1:02d}','road_class':'Collector' if i in (2,4) else 'Local','geometry':LineString([(x,y0-100),(x,y0+2500)])})
for j in range(7):
    y=y0+j*400
    roads.append({'road_id':f'EW{j+1:02d}','road_class':'Collector' if j in (1,4) else 'Local','geometry':LineString([(x0-100,y),(x0+2500,y)])})
roads.append({'road_id':'R15','road_class':'Arterial','geometry':LineString([(327900,433300),(328600,433730),(329200,434000),(329720,434640),(330500,435100)])})
water=[{'water_id':'W01','name':'Example Brook','water_type':'Stream','geometry':LineString([(327900,434870),(328290,434720),(328720,434830),(329090,434490),(329530,434630),(329980,434350),(330500,434180)])}]
places=[('Civic Centre',328790,434150),('Community School',329560,433650),('Library',329350,434200),('Sports Ground',328420,433500),('Town Square',329170,434700)]
points=[{'place_id':f'POI{n:02d}','name':name,'place_type':'Landmark','geometry':Point(x,y)} for n,(name,x,y) in enumerate(places,1)]
for layer,features in [('basemap_landuse',landuse),('basemap_roads',roads),('basemap_waterways',water),('basemap_places',points)]:
    gpd.GeoDataFrame(features,crs='EPSG:27700').to_file(OUT,layer=layer,driver='GPKG',mode='a')
