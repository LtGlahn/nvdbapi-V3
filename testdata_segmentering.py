"""
Testdata for vår kommende segmenteringsrutine 

Fiktiv 1000m lang strekning med X i intervallet [263000, 264000] og konstant Y = 7050000 og Z= 100
LINESTRING Z( 263000 7050000 100, 264000 7050000 100) 
Bruker 5m mellom koordinatpunktene
"""

import numpy as np 
from shapely import wkt
from shapely.geometry import Point, LineString
import pandas as pd
import geopandas as gpd 
import segmentering

def lagvref( frapos, tilpos, vrefRot='Ef6s1d1', geomlengde = 1000): 
    """
    Lager syntetisk vegsystemreferanse ut fra lineære posisjoner
    """

    return f"{vrefRot}m{int( round( geomlengde * frapos ))}-{int(round( geomlengde * tilpos ))}"

myGeomStartX = 263000
myGeomEndX   = 264000
myGeomDx     = 5
myGeomY      = 7050000
myGeomZ      = 100

myGeomCoords  = [ (x, myGeomY, myGeomZ) for x in list( range( myGeomStartX, myGeomEndX+1, myGeomDx))  ]
myGeom = LineString( myGeomCoords )
myGeomLFAC = 1 / myGeom.length # For en 1000m lang geometri så tilsvarer 1m langs linja et 0.001 inkrement i lineær referanse
myGeomLinearRef = [round( x, 8) for x in  np.linspace( 0, 1, num=len(myGeomCoords)) ] # 
GLF = myGeomLinearRef

# Forkortelser
vid = 'veglenkesekvensid'
fra = 'startposisjon'
til = 'sluttposisjon'

# To vegnettsbiter, hver på 500 m
v1 = 100 
veg = gpd.GeoDataFrame( [ { 'vref' : lagvref(0, GLF[v1]),   vid : 1000, fra : GLF[0],  til : GLF[100], 'geometry' : LineString( myGeomCoords[0:v1+1] )},      
                          { 'vref' : lagvref( GLF[v1], 1),  vid : 1000, fra : GLF[v1], til : GLF[-1], 'geometry'  : LineString( myGeomCoords[v1:] ) }    ], 
                          geometry='geometry', crs=5973 )

# To fartsgrense-biter, ny verdi ved meter 200
f1 = 40
fart = gpd.GeoDataFrame( [{ 'Fartsgrense' : 80, 'vref' : lagvref(0, GLF[f1]),  vid : 1000, fra : GLF[0],  til : GLF[f1], 'geometry' : LineString( myGeomCoords[0:f1+1] )},      
                          { 'Fartsgrense' : 60,'vref' : lagvref( GLF[f1], 1),  vid : 1000, fra : GLF[f1], til : GLF[-1], 'geometry'  : LineString( myGeomCoords[f1:] ) }    ], 
                          geometry='geometry', crs=5973 )

# Objekt som er littegrann forskjøvet (nedenfor toleranse på 10cm ) ift fartsgrensene 
dx = 0.01
bru = gpd.GeoDataFrame( [ { 'Bru' : 1, 'vref' : lagvref( GLF[f1], GLF[100]), fra:GLF[f1]-myGeomLFAC*dx, til:GLF[100]+myGeomLFAC*dx, 
                        'geometry' : LineString( [(myGeomCoords[f1][0]-dx, myGeomY, myGeomZ ), (myGeomCoords[100][0]+dx, myGeomY, myGeomZ )]), vid : 1000  }  ]  )


# Latterlig kort objekt < toleranse på 10cm, midt inne på fartsgrense-strekning
stikk = gpd.GeoDataFrame( [ { 'Stikk' : 'Ja', 'vref' : lagvref( GLF[175], GLF[175]), fra:GLF[175]-myGeomLFAC*dx, til:GLF[175]+myGeomLFAC*dx, 
        'geometry' : LineString( [(myGeomCoords[175][0]-dx, myGeomY, myGeomZ ), (myGeomCoords[175][0]+dx, myGeomY, myGeomZ )]), vid : 1000  }  ]  )


# rekkverk, to biter som delvis overlapper hverandre
r1a = 20
r1b = 120
r2a = 50
r2b = 110 
rekk = gpd.GeoDataFrame( [ { 'vref' : lagvref( GLF[r1a], GLF[r1b] ),  'nvdbId' : 1, 'objekttype' : 5, 'Bruksområde' : 'Vann', 
            vid : 1000, fra : GLF[r1a],  til : GLF[r1b], 'geometry' : LineString( myGeomCoords[r1a:r1b+1] )},      
                         { 'vref' : lagvref( GLF[r2a], GLF[r2b]),  'nvdbId' : 1, 'objekttype' : 5, 'Bruksområde' : 'Midtdeler',
            vid : 1000, fra : GLF[r2a], til : GLF[r2b], 'geometry'  : LineString( myGeomCoords[r2a:r2b+1] ) }    ], 
                          geometry='geometry', crs=5973 )

# Test av lengdefilter - snåle korte biter helt i enden av datasettet
dx = 0.01 # 1 cm 
l1start = myGeomLFAC * dx 
l1slutt = l1start + myGeomLFAC * dx 
l2slutt = 1 - myGeomLFAC * dx 
l2start = l2slutt - myGeomLFAC * dx

rareLinjer = gpd.GeoDataFrame( 
    [  { 'objekttype' : -1, 'navn' : 'Snål bit 1', 'vref' : lagvref( l1start, l1slutt), vid : 1000, fra : l1start, til : l1slutt, 'geometry' : LineString( [ (myGeomStartX +  l1start/myGeomLFAC, myGeomY, myGeomZ), 
                                                                                                                                          (myGeomStartX +  l1slutt/myGeomLFAC, myGeomY, myGeomZ) ]) },
       { 'objekttype' : -1, 'navn' : 'Snål bit 2', 'vref' : lagvref( l2start, l2slutt), vid : 1000, fra : l2start, til : l2slutt, 'geometry' : LineString( [ (myGeomStartX +  l2start/myGeomLFAC, myGeomY, myGeomZ), 
                                                                                                                                          (myGeomStartX +  l2slutt/myGeomLFAC, myGeomY, myGeomZ) ]) }])
rareLinjer2 = gpd.GeoDataFrame( [                                                                                                                                          
       { 'objekttype' : -3, 'Merknad' : 'Snål bit 3', 'vref' : lagvref( 0, l1start), vid : 1000, fra : 0, til : l1start, 'geometry' : LineString( [ (myGeomStartX, myGeomY, myGeomZ), 
                                                                                                                                 (myGeomStartX +  dx, myGeomY, myGeomZ) ]) },
       { 'objekttype' : -3,'Merknad' : 'Snål bit 4', 'vref' : lagvref( l2slutt, 1), vid : 1000, fra : l2slutt, til : 1, 'geometry' : LineString( [ (myGeomStartX +  l2slutt/myGeomLFAC, myGeomY, myGeomZ), 
                                                                                                                                  myGeomCoords[-1] ]) }  ]  )

data1 = segmentering.segmenter( veg, [rareLinjer, fart, rekk, rareLinjer2 ] )

data2 = segmentering.segmenter( veg, [fart, rekk], agg={5 : {'Bruksområde' : { 'navn' :  'Bruksområde rekkverk', 'agg' : 'unique' }}}, minsteLengde=60 )