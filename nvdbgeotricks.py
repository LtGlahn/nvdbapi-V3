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




def nvdb2gpkg( objekttyper, filnavn='datadump', mittfilter=None, vegnett=True, vegsegmenter=False, geometri=True):
    """
    Lagrer NVDB vegnett og angitte objekttyper til geopackage

    ARGUMENTS
        objekttyper: Liste med objekttyper du vil lagre 

    KEYWORDS
        mittfilter=None : Dictionary med filter til søkeobjekt i nvdbapiv3.py, for eksempel { 'kommune' : 5001 }
        Samme filter brukes på både vegnett og fagdata

        vegnett=True : Bool, default=True. Angir om vi skal ta med data om vegnett eller ikke

        vegsegmenter=False : Bool, default=False. Angir om vi skal repetere objektet delt inn etter vegsegementer

        geometri=True : Bool, default=True. Angir om vi skal hente geometri fra egengeometri (hvis det finnes)

        Hvis du ønsker å presentere vegobjekt ut fra objektets stedfesting langs veg så bruker du kombinasjonen 
        vegsegmenter=True, geometri=False 



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

        rec = sok.to_records( vegsegmenter=vegsegmenter, geometri=geometri )
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

    if vegnett: 
        veg = nvdbapiv3.nvdbVegnett()
        if mittfilter: 
            junk = mittfilter.pop( 'egenskap', None)
            junk = mittfilter.pop( 'overlapp', None)
            veg.filter( mittfilter )
        print( 'Henter vegnett')
        rec = veg.to_records()
        mindf = pd.DataFrame( rec)
        mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
        mindf.drop( 'geometri', 1, inplace=True)
        minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
        minGdf.to_file( filnavn, layer='vegnett', driver="GPKG")  


def dumpkontraktsomr( komr = [] ): 
    """
    Dumper et har (hardkodede) kontraktsområder 
    """
    if not komr: 

        komr = [ '9302 Haugesund 2020-2025', '9304 Bergen', '9305 Sunnfjord'  ]
        komr = [ '9253 Agder elektro og veglys 2021-2024']



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

    objliste = []

    for enkontrakt in komr: 

        filnavn = nvdbapiv3.esriSikkerTekst( enkontrakt )

        nvdb2gpkg( objliste, filnavn=filnavn, mittfilter={'kontraktsomrade' : enkontrakt })


def firefeltrapport( mittfilter={}): 
    """
    Finner alle firefeltsveger i Norge, evt innafor angitt søkekriterie 

    Bruker søkeobjektet nvdbapiv3.nvdbVegnett fra biblioteket https://github.com/LtGlahn/nvdbapi-V3

    ARGUMENTS
        None 

    KEYWORDS:
        mittfilter: Dictionary med søkefilter 

    RETURNS
        geodataframe med resultatet
    """

    v = nvdbapiv3.nvdbVegnett()

    # Legger til filter på kun fase = V (eksistende veg), såfremt det ikke kommer i konflikt med anna filter
    if not 'vegsystemreferanse' in mittfilter.keys(): 
        mittfilter['vegsystemreferanse'] = 'Ev,Rv,Fv,Kv,Sv,Pv'

    if not 'kryssystem' in mittfilter.keys():
        mittfilter['kryssystem'] = 'false' 

    if not 'sideanlegg' in mittfilter.keys():
        mittfilter['sideanlegg'] = 'false' 

    v.filter( mittfilter )
    
    # Kun kjørende, og kun øverste topologinivå, og ikke adskiltelop=MOT
    v.filter( { 'trafikantgruppe' : 'K', 'detaljniva' : 'VT,VTKB', 'adskiltelop' : 'med,nei' } )

    data = []
    vegsegment = v.nesteForekomst()
    while vegsegment: 

        if sjekkfelt( vegsegment, felttype='firefelt'):
            vegsegment['feltoversikt']  = ','.join( vegsegment['feltoversikt'] )
            vegsegment['geometri']      = vegsegment['geometri']['wkt']
            vegsegment['vref']          = vegsegment['vegsystemreferanse']['kortform']
            vegsegment['vegnr']         = vegsegment['vref'].split()[0]
            vegsegment['vegkategori']   = vegsegment['vref'][0]
            vegsegment['adskilte løp']  = vegsegment['vegsystemreferanse']['strekning']['adskilte_løp']

            data.append( vegsegment )

        vegsegment = v.nesteForekomst()

    if len( data ) > 1: 
        mindf = pd.DataFrame( data )
        mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
        mindf.drop( 'geometri', 1, inplace=True)
        mindf.drop( 'kontraktsområder', 1, inplace=True)
        mindf.drop( 'riksvegruter', 1, inplace=True) 
        mindf.drop( 'href', 1, inplace=True) 
        mindf.drop( 'metadata', 1, inplace=True) 
        mindf.drop( 'kortform', 1, inplace=True) 
        mindf.drop( 'veglenkenummer', 1, inplace=True) 
        mindf.drop( 'segmentnummer', 1, inplace=True) 
        mindf.drop( 'startnode', 1, inplace=True) 
        mindf.drop( 'sluttnode', 1, inplace=True) 
        mindf.drop( 'referanse', 1, inplace=True) 
        mindf.drop( 'målemetode', 1, inplace=True) 
        mindf.drop( 'måledato', 1, inplace=True) 
        minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 ) 
        return minGdf
    else: 
        return None 


def sjekkfelt( vegsegment, felttype='firefelt' ): 
    """
    Sjekker hva slags felt som finnes på et vegsegment

    ARGUMENTS: 
        vegsegment - dicionary med data om en bit av vegnettet hentet fra https://nvdbapiles-v3.atlas.vegvesen.no/vegnett/veglenkesekvenser/segmentert/ 

    KEYWORDS: 
        felttype - hva slags felttype som skal sjekkes. Mulige verdier: 
            firefelt (default). Antar at firefeltsveg betyr at kjørefeltnummer 1-4 er brukt og er enten vanlig kj.felt, kollektivfelt eller reversibelt felt 

                     (flere varianter kommer når de trengs)

    RETURNS
        boolean - True hvis kjørefeltene er av riktig type 
    """
    svar = False
    vr = 'vegsystemreferanse'
    sr = 'strekning'

    if felttype == 'firefelt': 
        if 'feltoversikt' in vegsegment.keys() and 'detaljnivå' in vegsegment.keys() and 'Vegtrase' in vegsegment['detaljnivå']: 
            kjfelt = set( filtrerfeltoversikt( vegsegment['feltoversikt'], mittfilter=['vanlig', 'K', 'R']) )
            if vr in vegsegment.keys(): 

                if sr in vegsegment[vr] and 'adskilte_løp' in vegsegment[vr][sr]: 
                    if vegsegment[vr][sr]['adskilte_løp'] == 'Nei' and kjfelt.issuperset( { 1, 2, 3, 4}): 
                        svar = True
                    # Siste klausul her har f.eks. forekommet på Fv5724, envegskjørt tunnel ved Oldenvatnet. 
                    elif vegsegment[vr][sr]['adskilte_løp'] == 'Med' and len( kjfelt ) >= 2 and not kjfelt.issuperset( {1, 2} ): 
                        svar = True 


        return svar 
    else: 
        raise NotImplementedError('Sjekkfelt: Sjekk for felt av type: ' + felttype + 'er ikke implementert (ennå)' )
        

def filtrerfeltoversikt( feltoversikt, mittfilter=['vanlig', 'K', 'R' ]):
    """
    Returnerer liste med kjørefeltnummer filtrert på hva slags feltkode vi evt har

    ARGUMENTS
        feltoversikt - Liste med feltkoder for et vegsegment. 

    KEYWORDS
        mittfilter=['vanlig', 'K', 'R' ] - Liste med koder for hva slags felt vi skal telle med. Sjekk håndbok v830 
            Nasjonalt vegreferansesystem https://www.vegvesen.no/_attachment/61505 for mulige verdier, kortversjon: 
                'vanlig' - Helt vanlig kjørefelt, kjørefeltnumemr er angitt som heltall uten noen bokstaver. 
                'K'      - kollektivfelt
                'R'      - reversibelt felt
                'S'      - Sykkelfelt
                'H'      - Svingefelt mot høyre
                'V'      - Svingefelt mot venstre
                'B'      - Ekstra felt for bompengeinnkreving 
    RETURNS
        Liste med kjørefeltnummer hvor kun kjørefelt som  angitt med mittfilter-nøkkelord er inkludert 
    """
    data = [ ]
    for felt in feltoversikt: 
        feltbokstav = re.findall( '[A-Za-z]', felt)
        if feltbokstav: 
            feltbokstav = feltbokstav[0]
        else: 
            feltbokstav = 'vanlig'
        
        if feltbokstav in mittfilter: 
            feltnummer = int( re.split( '[A-Z]', felt)[0] ) 
            data.append( feltnummer )

    return data 
        
