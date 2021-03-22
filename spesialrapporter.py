"""
En samling spesialrapporter som bruker nvdbapiv3 og nvdbgeotricks til å sette sammen kombinasjoner av datasett

Disse hjelpefunksjonene forutsetter fungerende installasjon av geopandas, shapely og en del andre ting som må 
installeres separat. Noen av disse bibliotekene kunne historisk av og til være plundrete å installere, evt 
ha versjonskonflikter seg i mellom, spesielt på windows. Slikt plunder hører historien til (stort sett)

Anbefalingen er like fullt å bruke (ana)conda installasjon i et eget "environment". Dette er god kodehygiene
og sikrer minimalt med kluss, samt ikke minst: Eventuelt kluss lar seg greit reparere ved å lage nytt "enviroment", 
uten at det påvirker hele python-installasjonen din. 
"""
import re
import pdb
from copy import deepcopy
import sqlite3

from shapely import wkt 
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime

import nvdbapiv3
from nvdbapiv3 import apiforbindelse
import nvdbgeotricks

def tunnelrapport( mittfilter=None  ):
    """
    Setter sammen tunnel, tunnelløp og en del fagdata

    Bruk nøkkelord mittfilter=dictionary med NVDB api LES filtermuligheter for å snevre inn søket 
        eks: mittfilter={ 'vegsystemreferanse' : 'Rv', fylke=30 } 

    returnerer TO dataframes, en med full rapport og en komprimert (per unike tunnelobjekt)
    """

    # Kopierer mittfilter for å unngå sideefekter 
    if mittfilter: 
        filteret = deepcopy( mittfilter )
    else: 
        filteret = {}

    # Henter tunnell og tunnelløp, spleiser dem sammen: 
    tun = nvdbapiv3.nvdbFagdata( 581 )
    tunlop = nvdbapiv3.nvdbFagdata( 67 )

    if mittfilter: 
        tun.filter( filteret )
        tunlop.filter( filteret )

    tunDf = pd.DataFrame( tun.to_records() )
    tunlopDf = pd.DataFrame( tunlop.to_records() )

    # Spleiser tunnel og tunnelløp basert på mor-datter relasjon
    mellomresultat1 = nvdbgeotricks.finnDatter( tunDf, tunlopDf, prefixMor='t581_', prefixDatter='t67_'  )

    # Må droppe relasjoner-kolonnen ettersom dette er en dictionary-struktur som ikke takles av sqlite3-
    mellomresultat1.drop( columns=['t581_relasjoner', 't67_relasjoner'], inplace=True )

    # Henter øvrige fagdata: 
    s105 = nvdbapiv3.nvdbFagdata( 105 ) # Fartsgrense
    s540 = nvdbapiv3.nvdbFagdata( 540 ) # Trafikkmengde

    if mittfilter: 
        s105.filter( filteret )
        s540.filter( filteret )

    # Legger til overlappfilter
    s105.filter( { 'overlapp' : '67' })
    s540.filter( { 'overlapp' : '67' })

    # lager dataaframes 
    df105 = pd.DataFrame( s105.to_records(relasjoner=False  ))
    df540 = pd.DataFrame( s540.to_records(relasjoner=False  ))

    mellomresultat1.reset_index( inplace=True )
    mellomresultat2 = nvdbgeotricks.finnoverlapp( mellomresultat1, df105, prefixA='t67_', prefixB='t105_')
    mellomresultat3 = nvdbgeotricks.finnoverlapp( mellomresultat2, df540, prefixA='t67_', prefixB='t540_')

    mellomresultat3.reset_index( )

    sletteliste = [ 'index', 't581_objekttype', 't581_versjon', 't581_startdato', 't581_veglenkeType', 't581_vegkategori', 
                    't581_veglenkesekvensid', 't581_detaljnivå', 't581_typeVeg', 
                    't581_fase', 't581_nummer', 't67_objekttype', 't67_versjon', 't67_startdato', 
                    't67_veglenkeType', 't67_vegkategori', 't67_fase', 't67_nummer', 't67_adskilte_lop', 't67_trafikantgruppe', 
                    't67_veglenkesekvensid', 't67_detaljnivå', 't67_typeVeg', 
                    't581_relativPosisjon', 't581_adskilte_lop', 't581_trafikantgruppe', 't105_objekttype', 
                    't105_nvdbId', 't105_versjon', 't105_startdato', 't105_Gyldig fra dato', 't105_veglenkesekvensid', 
                    't105_detaljnivå', 't105_typeVeg', 't105_kommune', 't105_fylke', 't105_vref', 't105_veglenkeType', 
                    't105_vegkategori', 't105_fase', 't105_nummer', 't105_startposisjon', 't105_sluttposisjon', 
                    't105_segmentlengde', 't105_adskilte_lop', 't105_trafikantgruppe', 't105_geometri', 't105_Vedtaksnummer', 
                    't105_Arkivnummer', 't540_objekttype', 't540_nvdbId', 't540_versjon', 't540_startdato', 
                    't540_Historisk_Ansvarlig ID', 't540_Grunnlag for ÅDT', 't540_veglenkesekvensid', 't540_detaljnivå', 
                    't540_typeVeg', 't540_kommune', 't540_fylke', 't540_vref', 't540_veglenkeType', 't540_vegkategori', 
                    't540_fase', 't540_nummer', 't540_startposisjon', 't540_sluttposisjon', 't540_segmentlengde', 
                    't540_adskilte_lop', 't540_trafikantgruppe', 't540_geometri', 't540_Historisk_ForholdÅDT', 
                    't540_Historisk_Tellepunkt, sekundært', 't540_Historisk_Koplingsår', 't540_Historisk_Mfaktor', 
                    't540_ÅDT, start', 't540_ÅDT, slutt', 't540_Historisk_Tellepunkt, primært', 
                    't540_Historisk_ForholdLange', 't540_Oppdatert fra' ]

    nysletteliste = []
    forkast = []
    for slett in sletteliste: 
        if slett in mellomresultat3.columns: 
            nysletteliste.append( slett )
        else: 
            forkast.append( slett )

    if len( forkast ) > 0: 
        print( 'Kan ikke slette disse kolonnene fra tunnelrapport:\n', forkast )

    if len( nysletteliste) > 0: 
        mellomresultat3.drop( columns=nysletteliste, inplace=True )

    komprimertKolonner = [ 't581_nvdbId', 't67_Høyde', 't67_Åpningsår', 't67_Lengde', 't67_Merknad', 
                            't67_Navn', 't67_Bredde', 't67_Tunnelprofil', 't67_Type tunnelløp', 
                            't67_Kategori', 't67_Ekstra belysning inngangssone', 't67_Areal tverrsnitt', 
                            't67_Rehabiliteringsår', 't67_Malte tunnelvegger', 't67_Prosjektreferanse', 
                            't67_Brutus_Id', 't105_Fartsgrense', 't540_År, gjelder for', 't540_ÅDT, total', 
                            't540_ÅDT, andel lange kjøretøy' ]
    komprimert = mellomresultat3.drop_duplicates( subset=komprimertKolonner ).copy()

    slett = ['t67_nvdbId', 't67_kommune', 't67_fylke', 't67_vref', 't67_startposisjon', 
                't67_sluttposisjon', 't67_segmentlengde', 't67_geometri']

    komprimert.drop( columns=slett, inplace=True )

    return (mellomresultat3, komprimert )


