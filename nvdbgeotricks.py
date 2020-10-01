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




def nvdb2gpkg( objekttyper, filnavn='datadump', mittfilter=None):
    """
    Lagrer NVDB vegnett og angitte objekttyper til geopackage

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
        if len( rec ) > 0: 
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
        else: 
            print( 'Ingen forekomster av', objtypenavn, 'for filter', mittfilter)        

    veg = nvdbapiv3.nvdbVegnett()
    if mittfilter: 
        veg.filter( mittfilter )
    print( 'Henter vegnett')
    rec = veg.to_records()
    mindf = pd.DataFrame( rec)
    mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
    mindf.drop( 'geometri', 1, inplace=True)
    minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
    minGdf.to_file( filnavn, layer='vegnett', driver="GPKG")  


def dumpkontraktsomr( ): 
    """
    Dumper et har (hardkodede) kontraktsområder 
    """

    komr = [ '9302 Haugesund 2020-2025', '9304 Bergen', '9305 Sunnfjord'  ]

    objliste = [    540, # Trafikkmengde
                    105, # Fartsgrense
                    810, # Vinterdriftsklasse
                    482, # trafikkregistreringsstasjon
                    153, # Værstasjon
                    64, # Ferjeleie
                    39, # Rasteplass 
                    48, # Fortau
                    199, # Trær
                    15, # Grasdekker
                    274, # Blomsterbeplanting
                    511, # Busker
                    300 , # Naturområde (ingen treff i Haugesund kontrakt)
                    517, # Artsrik vegkant
                    800, # Fremmede arter
                    67, # Tunnelløp
                    846, # Skredsikring, bremsekjegler 
                    850 # Skredsikring, forbygning
            ]

    for enkontrakt in komr: 

        filnavn = nvdbapiv3.esriSikkerTekst( enkontrakt )

        nvdb2gpkg( objliste, filnavn=filnavn, mittfilter={'kontraktsomrade' : enkontrakt })
