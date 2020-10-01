"""
En samling hjelpefunksjoner som bruker nvdbapiv3-funksjonene til å gjøre nyttige ting, f.eks. lagre geografiske datasett

Disse hjelpefunksjonene forutsetter fungerende installasjon av geopandas, shapely og en del andre ting som må 
installeres separat. Noen av disse bibliotekene kunne historisk av og til være plundrete å installere, evt 
ha versjonskonflikter seg i mellom, spesielt på windows. Slikt plunder hører historien til (stort sett)

Anbefalingen er like fullt å bruke (ana)conda installasjon i et eget "environment". Dette er god kodehygiene
og sikrer minimalt med kluss, samt ikke minst: Eventuelt kluss lar seg greit reparere ved å lage nytt "enviroment", 
uten at det påvirker hele python-installasjonen din. 
"""
import re
import pdb

from shapely import wkt 
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime

import nvdbapiv3
from apiforbindelse import apiforbindelse




def finnDuplikat( minliste): 
    """
    Finner duplikat i liste 
    """
    pass 


def nvdb2gpkg( objekttyper, filnavn='datadump', mittfilter=None):
    """
    Lagrer NVDB vegnett og angitte objekttyper til geopackage

    TODO: Føy på støtte for skjermede objekttyper og egenskapverdier
        (f.eks. legg på mulighet for å sende inn ferdig logget inn instans av apiforbindelse  )

    ARGUMENTS
        objekttyper: Liste med objekttyper du vil lagre 

    KEYWORDS
        mittfilter=None : Dictionary med filter til søkeobjekt i nvdbapiv3.py, for eksempel { 'kommune' : 5001 }
        Samme filter brukes på både vegnett og fagdata

    RETURNS 
        None 
    """

    if not '.gpkg' in filnavn: 
        filnavn = filnavn +  datetime.today().strftime('%Y-%m-%d') + '.gpkg'

    if not isinstance(objekttyper, list ): 
        objekttyper = [ objekttyper ]

    for enObjTypeId in objekttyper: 

        enObjTypeId = int( enObjTypeId )

        sok = nvdbapiv3.nvdbFagdata( enObjTypeId  )
        if mittfilter: 
            sok.filter( mittfilter )

        stat = sok.statistikk()
        objtypenavn = sok.objektTypeDef['navn']
        print( 'Henter', stat['antall'],  'forekomster av objekttype', sok.objektTypeId, objtypenavn )
        lagnavn = 'type' + str(enObjTypeId) + '_' + nvdbapiv3.esriSikkerTekst( objtypenavn.lower() ) 

        rec = sok.to_records( vegsegmenter=False, geometri=True )
        mindf = pd.DataFrame( rec )
        # Må trickse litt for å unngå navnekollisjon
        kolonner = list( mindf.columns )
        lowerkolonner = [ x.lower() for x in kolonner ]
        # Duplicate element indices in list 
        # Using list comprehension + list slicing 
        # https://www.geeksforgeeks.org/python-duplicate-element-indices-in-list/ 
        res = [idx for idx, val in enumerate(lowerkolonner) if val in lowerkolonner[:idx]] 
        for ii, dublett in enumerate( res):
            mindf.rename(columns={ mindf.columns[dublett] : kolonner[dublett] + '_' + str( ii+1 )  }, inplace=True )

        mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
        minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
        # må droppe kolonne vegsegmenter hvis du har vegsegmenter=False 
        if 'vegsegmenter' in minGdf.columns:
            minGdf.drop( 'vegsegmenter', 1, inplace=True)

        minGdf.drop( 'geometri', 1, inplace=True)
        minGdf.to_file( filnavn, layer=lagnavn, driver="GPKG")  
        

    veg = nvdbapiv3.nvdbVegnett()
    if mittfilter: 
        veg.filter( mittfilter )
    
    rec = veg.to_records()
    mindf = pd.DataFrame( rec)
    mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
    mindf.drop( 'geometri', 1, inplace=True)
    minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
    minGdf.to_file( filnavn, layer='vegnett', driver="GPKG")  
