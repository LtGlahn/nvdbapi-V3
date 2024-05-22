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
from copy import deepcopy
import json
import string
# from xmlrpc.client import Boolean 

from shapely import wkt 
from shapely.geometry import Point, LineString
from shapely.ops import transform 
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime
import numpy as np
import pyproj 

import nvdbapiv3
from nvdbapiv3 import apiforbindelse


def nvdbsok2GDF( sokeobjekt, **kwargs ): 
    """
    Konverterer et NVDB søkeobjekt til geodataframe 

    Eventuelle nøkkelord-argumenter sendes til funksjonen sokeobjekt.to_records( )
    """
    mydf = pd.DataFrame( sokeobjekt.to_records( **kwargs ))
    mydf['geometry'] = mydf['geometri'].apply( wkt.loads )
    myGDF = gpd.GeoDataFrame( mydf, geometry='geometry', crs=5973)
    return myGDF

def finnDatter( morDf, datterDf, prefixMor=None, prefixDatter=None, ignorerDatterPrefix=False   ): 
    """
    Finner relasjoner mellom vegobjekter i (geo)dataframe 
    
    Returnerer ny dataframe hvor alle elementer i datterDf er påført informasjon fra mor-objektet hentet fra morDf 

    For å unngå navnekollisjon er standardoppførselen å føye forstavelsen kolonnenavn <vegobjektTypeId>_ til 
    alle kolonnenavn i datterdf. Denne oppførselen reguleres med nøkkelordene addprefix_datter og prefix. 

    Når du har en verdikjede med flere koblinger etter hverandre (evt med funksjonen finnoverlapp) er det  risiko 
    for navnekollisjon og navneforvirring. Hvis ikke du overstyrer med argumentet prefiksMor så beholder vi kolonnenavn
    fra morDf, men endrer alle kolonnenavnene i datterDf med forstavelsen "<objektTypeID>_", for eksempel "67_". 
    Forstavelse for datterDf kan også overstyres med nøkkelord prefixDatter. Merk at hvis morDf eller datterDf allerede er 
    "omdøpt" med dette prefikset så føyes det ikke til enda en gang (men brukes for å identifisere riktige kolonner) 
    Se også dokumentasjon for funksjonen finnoverlapp.  

    I noen sammenhenger er det riktig å behandle hvert vegsegment til et objekt separat, andre ganger ønsker man kun 
    en rad per objekt Id. Funksjonen finnDatter kan ikke avgjøre hva som er riktig for deg, men gir ut det den får inn. 
    Dvs hvis ID2 er datterobjekt til ID1 så vil du få returnert en rad med kombinasjonen ID1->ID2 for hver kombinasjon av 
    vegsegmenter for objektene ID1, ID2. Dvs hvis ID1 har to vegsegmenter og Id2 har tre så får du seks rader i resultatene. 
    Du må selv filtrere vekk de kombinasjonene du ikke vil ha, eller filtrere 
    vekk duplikater fra inputdata. I så fall er anbefalingen å filtrere på Nvdb Id. 

    ARGUMENTS: 
        morDf, datterDf: Pandas dataframe eller geopandas geodataframe. 

    KEYWORDS: 
        Her er nøkkelord som regulerer hvordan vi døper om kolonner i datterDf (og evt morDf) for å minimere navnekollisjon. 
        Standardoppførselen er å  beholde alle navn i morDf, men døpe vi om alle kolonnenavn i datterDf med "t<objektTypeID>_" som prefiks. 
        Merk at vi ikke endrer kolonnenavn som allerede inneholder det vi ellers ville brukt som prefiks for å døpe dem om. 

        prefixMor=None eller tekststreng. Brukes hvis det er ønskelig å døpe om alle kolonnenavn i morDf med dette som prefix   

        prefixDatter=None eller tekststreng. Angis hvis du vil bruke noe annet enn "t<objektTypeID>_" som prefiks når du gir nye navn til 
                                             kolonner i datterDf. 
                                            
        ignorerDatterPrefix: Endrer IKKE kolonnenavn i datterDf. 
    RETURNS
        dataFrame eller Geodataframe (samme som morDf)
    """

    # Lager kopier, så vi ikke får kjipe sideeffekter av orginaldatasettet 
    mDf = morDf.copy()
    dDf = datterDf.copy()

    idKey = 'nvdbId'
    if prefixMor: 
        # Sjekker om prefixet er i bruk allerede:
        if len( [ x for x in list( mDf.columns ) if prefixMor in x ]  ) == 0: 
            mDf = mDf.add_prefix( prefixMor )
        idKey = prefixMor + 'nvdbId'

    if prefixDatter and not ignorerDatterPrefix: 
        # Sjekker om prefikset er i bruk allerede
        if len( [ x for x in list( dDf.columns ) if prefixDatter in x ]  ) == 0: 
            dDf = dDf.add_prefix( prefixDatter )

        relKey       = prefixDatter + 'relasjoner'
        datterIdKey  = prefixDatter + 'nvdbId'
 
    else: 
        temp = [x for x in list( dDf.columns ) if 'objekttype' in x ]
        assert len(temp) == 1, f"finnDatter: Lette etter en kolonne kalt objekttype i datterDf, fant {len(temp)} stk: {temp} "
        temp2 = list( dDf[temp[0]].unique() )
        assert len(temp2) == 1, f"finnDatter: Lette etter unik objekttype i datterDf kolonne {temp[0]}, fant {len(temp2)} stk: {temp2} "

        if ignorerDatterPrefix: 
            relKey      = 'relasjoner' 
            datterIdKey = 'nvdbId'

        else: 
            relKey          = 't' + str( temp2[0] ) + '_relasjoner'
            datterIdKey     = 't' + str( temp2[0] ) + '_nvdbId'
            dDf = dDf.add_prefix( 't' + str( temp2[0] ) + '_' )

    assert len( [x for x in list( mDf.columns ) if idKey        in x ] ) == 1, f"Fant ikke unik kolonne {idKey} i mor-datasett, prefixMor={prefixMor} "
    assert len( [x for x in list( dDf.columns ) if relKey       in x ] ) == 1, f"Fant ikke unik kolonne {relKey} i datter-datasett, prefixDatter={prefixDatter} "
    assert len( [x for x in list( dDf.columns ) if datterIdKey  in x ] ) == 1, f"Fant ikke unik kolonne {datterIdKey} i datter-datasett, prefixDatter={prefixDatter} "

    returdata = []
    for ii, row in dDf.iterrows(): 

        row_resultat = []
        if relKey in row and 'foreldre' in row[relKey]: 
            morIdListe = []
            morObjektTypeId = []
            for mortype in row[relKey]['foreldre']: 
                morIdListe.extend( mortype['vegobjekter'] )
                morObjektTypeId.append( mortype['type'])

            morDict = []
            for morId in morIdListe: 
                tempDf = mDf[ mDf[idKey] == morId ]
                for jj, morRow in tempDf.iterrows(): 
                    morDict = morRow.to_dict()
                    datterDict = row.to_dict()
                    blanding = { **morDict, **datterDict }                    
                    row_resultat.append( deepcopy( blanding ) )

            if len( row_resultat ) > 1: 
                print( f"Flere mødre { morIdListe } funnet for datterobjekt {row[datterIdKey]}" )
            elif len( morIdListe) > 1 and len( row_resultat) == 1: 
                print( f"Flere mødre angitt for datterobjekt {row[datterIdKey]}, men fant heldigvis kun ett treff i morDf" )

            returdata.extend( row_resultat )

    returDf = pd.DataFrame( returdata )

    return returDf 

def records2gpkg( minliste, filnavn, lagnavn ): 
    """
    Tar en liste med records (dictionaries) a la dem vi får fra nvdbapiv3.to_records() og skriver til geopackage

    Forutsetning: Alle records har et "geometri"-element med WKT-streng og inneholder ingen lister. 
    Vi tester for en del kjente snublefeller mhp disse forutsetningene, men ikke alle. 
    """
    if len( minliste ) == 0: 
        raise ValueError( 'nvdbgeotrics.records2gpkg: Tom liste som inngangsverdi, funker dårlig')

    mindf = pd.DataFrame( minliste )
    # Må trickse litt for å unngå navnekollisjon
    kolonner = list( mindf.columns )
    lowerkolonner = [ x.lower() for x in kolonner ]
    # Duplicate element indices in list 
    # Using list comprehension + list slicing 
    # https://www.geeksforgeeks.org/python-duplicate-element-indices-in-list/ 
    res = [idx for idx, val in enumerate(lowerkolonner) if val in lowerkolonner[:idx]] 
    for ii, dublett in enumerate( res):
        mindf.rename(columns={ mindf.columns[dublett] : kolonner[dublett] + '_' + str( ii+1 )  }, inplace=True )

    if isinstance( mindf.iloc[0].geometri, dict ): 
        mindf['geometri'] = mindf['geometri'].apply( lambda x : x['wkt'] )

    mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
    minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
    # må droppe kolonne vegsegmenter hvis data er hentet med vegsegmenter=False 
    if 'vegsegmenter' in minGdf.columns:
        minGdf.drop( columns='vegsegmenter', inplace=True)

    minGdf.drop( columns='geometri', inplace=True)
    minGdf.to_file( filnavn, layer=lagnavn, driver="GPKG")  

def nvdb2gpkg( objekttyper, filnavn='datadump', mittfilter=None, vegnett=True, vegsegmenter=False, geometri=True, forb=None):
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
        vegsegmenter=True, geometri=False. Ett enkelt objekt blir da repetert for hvert vegsegment som det er 
        tilknyttet (stedfestet til). 
        
        Standardverdiene vegsegmenter=False, geometri=True er valgt ut fra antagelsen om at du ønsker 
        en rad per objekt, uten duplisering. 

        forb=None eller en instans av nvdbapiv3.apiforbindelse(). Dette objektet håndterer innlogging i NVDB api LES, som er 
                    påkrevd hvis du ønsker å lese skjermede objekttyper. Eksempel
    
    EKSEMPEL
        Lagre skjermede data for 903 Bruksklasse, spesialtransport, uoffisiell og  905 Bruksklasse, normaltransport uoffisiell sammen 
        med vegnettsdata på E6 i Oslo kommune
        
        import nvdbapiv3
        import nvdbgeotricks  
        forb = nvdbapiv3.apiforbindelse()
        forb.login( username=DITTNVDBBRUKERNAVN )
        nvdbgeotricks.nvdb2gpkg( [903, 905], mittfilter={'vegsystemreferanse' : 'Ev6', 'kommune' : 301}, forb=forb )

    RETURNS 
        None 
    """

    if not '.gpkg' in filnavn: 
        filnavn = filnavn + '_' + datetime.today().strftime('%Y-%m-%d') + '.gpkg'

    if not isinstance(objekttyper, list ): 
        objekttyper = [ objekttyper ]
        
    if not forb: 
        forb = nvdbapiv3.apiforbindelse()

    for enObjTypeId in objekttyper: 

        enObjTypeId = int( enObjTypeId )

        sok = nvdbapiv3.nvdbFagdata( enObjTypeId  )
        sok.forbindelse = forb 
        if mittfilter: 
            sok.filter( mittfilter )

        stat = sok.statistikk()
        objtypenavn = sok.objektTypeDef['navn']
        print( 'Henter', stat['antall'],  'forekomster av objekttype', sok.objektTypeId, objtypenavn )
        lagnavn = 'type' + str(enObjTypeId) + '_' + nvdbapiv3.esriSikkerTekst( objtypenavn.lower() ) 

        rec = sok.to_records( vegsegmenter=vegsegmenter, geometri=geometri )

        # Lagringsrutine skilt ut med funksjonen records2gpkg, IKKE TESTET (men bør gå greit) 
        if len( rec ) > 0: 
            records2gpkg( rec, filnavn, lagnavn )
        else: 
            print( 'Ingen forekomster av', objtypenavn, 'for filter', mittfilter)        

    if vegnett: 
        veg = nvdbapiv3.nvdbVegnett()
        veg.forbindelse = forb 
        if mittfilter: 
            junk = mittfilter.pop( 'egenskap', None)
            junk = mittfilter.pop( 'overlapp', None)
            veg.filter( mittfilter )
        print( 'Henter vegnett')
        rec = veg.to_records()
        mindf = pd.DataFrame( rec)
        mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
        mindf.drop( columns='geometri', inplace=True)
        minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
        minGdf.to_file( filnavn, layer='vegnett', driver="GPKG")  


def dumpkontraktsomr( komr = [] ): 
    """
    Dumper et har (hardkodede) kontraktsområder 
    """
    if not komr: 

        komr = [ '9302 Haugesund 2020-2025', '9304 Bergen', '9305 Sunnfjord'  ]
        komr = [ '9253 Agder elektro og veglys 2021-2024']


    if isinstance( komr, str): 
        komr = [ komr ]

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
        mindf.drop( columns=['geometri', 'kontraktsområder', 'riksvegruter', 'href', 'metadata',  
                                'kortform', 'veglenkenummer', 'segmentnummer', 'startnode', 'sluttnode',  
                                'referanse', 'målemetode', 'måledato'], inplace=True) 
        minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 ) 
        return minGdf
    else: 
        return None 

def posisjon( params, forb=None ): 
    """
    Henter data fra /posisjon endepunktet til LES https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/swagger-ui/index.html#/Vegnett/get_posisjon
    
    ARGUMENTS:
        params : dictionary med søkeparametre. 
                Må minimum inneholde koordinatpar { 'ost' : X, 'nord' : Y } eller { 'lon' : X, 'lat' : Y }
                Se  dokumentasjon 
                https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/swagger-ui/index.html#/Vegnett/get_posisjon        

    KEYWORDS: 
        forb : None eller en instans av nvdbapiv3.apiforbindelse()

    RETURNS: 
        None (hvis søket feiler) eller Geopandas GeoDataFrame med søketreffene, transformert til en flat tabell
    """

    if forb is None: 
        forb = nvdbapiv3.apiforbindelse()

    r = forb.les( '/posisjon', params=params )
    print( r.url )
    if r.ok: 
        data = r.json()
        srid = 5973 
        if isinstance( data, list): 
            returdata = []
            for punkt in data: 
                feat = { 'avstand' : punkt['avstand'], 'kommune' : punkt['kommune'] }
                if 'vegsystemreferanse' in punkt and 'kortform' in punkt['vegsystemreferanse']: 
                    feat['vref'] = punkt['vegsystemreferanse']['kortform']

                if 'veglenkesekvens' in punkt: 
                    feat['veglenkesekvensid']   = punkt['veglenkesekvens']['veglenkesekvensid']
                    feat['relativPosisjon']     = punkt['veglenkesekvens']['relativPosisjon']
                    feat['veglenkepos']         = punkt['veglenkesekvens']['kortform']


                feat['geometry'] = wkt.loads( punkt['geometri']['wkt'])
                if punkt['geometri']['srid'] != 5973: 
                    srid = feat['geometri']['srid']
                
                returdata.append( feat )
            
            returdata = pd.DataFrame( returdata ) 
            returdata = gpd.GeoDataFrame( returdata, geometry='geometry', crs=srid )

            return returdata
        
        else: 
            print( f"Null søketreff på /posisjon med parametre {params}")

    else: 
        print( f"Feilmelding /posisjon HTTP {r.status_code} {r.text[0:1000]}")
    
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

def kostraVeglengde( minDataFrame  ): 
    """
    Teller utstrekning langs vegnett etter KOSTRA-metoden

    Inputdata er en pandas dataframe eller geopandas geodataframe med segmentert vegnett,
    hentet direkte fra NVDB api LES - endepunktet /vegnett/veglenkesekvenser/segmentert

    Returnerer heltall med lengde, i meter
    """
    assert 'columns' in dir( minDataFrame ), "Tror ikke inputdata er gyldig (geo)dataframe"
    assert 'adskilte_lop' in minDataFrame.columns, "Ser ikke ut til at inputdata beskriver segmentert vegnett?" 
    assert 'typeVeg' in minDataFrame.columns, "Ser ikke ut til at inputdata beskriver segmentert vegnett?" 
    assert 'trafikantgruppe' in minDataFrame.columns, "Ser ikke ut til at inputdata beskriver segmentert vegnett?" 


    # Ignorerer konnekteringslenker (og evt andre topolognivå enn det øverste)
    # Vegnett skal også filtrere vekk sideanlegg, type veg osv, mens fagdata stort sett 
    # ikke skal ha slike filter
    # IGNORERER FAGDATA i første omgang, de skal stort sett telles rubb og rake uansett (?)
    # FAGDATA: Har egenskapsverdi 'veglenkeType' 
    # if 'veglenkeType' in minDataFrame.colums: 
    #     mydf = minDataFrame[ minDataFrame['veglenkeType'] == 'HOVED'].copy()
    # Mens for vegnettsdata heter vegtype rett og slett "type"
    # elif 'type' in minDataFrame.columns: 
    if 'type' in minDataFrame.columns: 
        mydf = minDataFrame[ minDataFrame['type'] == 'HOVED'].copy()
    else: 
        raise ValueError( 'Mangler informasjon om veglenketype i datasett' )

    # Kun trafikantgruppe = K 
    mydf = mydf[ mydf['trafikantgruppe'] == 'K' ]

    # Type veglenke ihtt KOSTRA-spresifikasjon 
    kostraVegtyper = [ 'Kanalisert veg','Enkel bilveg','Rampe','Rundkjøring','Gatetun' ] 
    mydf = mydf[ mydf['typeVeg'].isin( kostraVegtyper )]

    # Filtrerer vekk sideanlegg, som vi finner ved å se etter strengen SD ( SideanleggsDel ) i vegsystemreferansen
    mydf = mydf[ ~mydf['vref'].str.contains( 'SD')]

    # Filtrerer vekk Adskilte løp = Mot 
    mydf = mydf[ mydf['adskilte_lop'].isin( ['Med', 'Nei'] )]

    return mydf['lengde'].sum()



def skrivexcel( filnavn, dataFrameListe, sheet_nameListe=[], indexListe=[], slettgeometri=True ):
    """
    Skriver liste med dataFrame til excel, med kolonnebredde=lengste element i header eller datainnhold

    Skipper kolonner med navn "geometri" eller "geometry" 

    ARGUMENTS
        filnavn : Navn på excel-fil 

        dataFrameListe : Liste med dataframe, eller en enkelt dataFrame / geodataframe 

    KEYWORDS
        sheet_nameListe : [] Liste med navn på fanene i exel-arket. Hvis tom liste brukes Fane1, Fane2...

        indexListe : [] Angir om index skal med som første kolonne(r), liste med True eller False. Default: Uten index. 

        slettgeometri : True . Sletter geometrikolonner 
    """

    # Håndterer en enkelt dataframe => putter i liste med ett element

    if not isinstance( dataFrameListe, list ): 
        dataFrameListe = [ dataFrameListe ]

    writer = pd.ExcelWriter( filnavn, engine='xlsxwriter')


    for (idx, endf ) in enumerate( dataFrameListe): 

        # Sikrer at vi ikke har sideeffekter på orginal dataframe
        mydf = endf.copy()

        if slettgeometri: 
            sletteliste = ['geometri', 'geometry']
            for slettkol in sletteliste: 
                if slettkol in mydf: 
                    mydf.drop( columns=slettkol, inplace=True )
        else: 
            sletteliste = []

        # Navn på blad (ark, sheet_name) i excel-fila
        if sheet_nameListe and isinstance( sheet_nameListe, list) and idx+1 <= len( sheet_nameListe): 
            arknavn = sheet_nameListe[idx]
        else: 
            arknavn = 'Ark' + str( idx+1 )

        # Skal vi ha med indeks? 
        if indexListe and isinstance( indexListe, list) and len( indexListe) <= idx+1: 
            brukindex = indexListe[idx]
        else: 
            brukindex = False 

        mydf.to_excel(writer, sheet_name=arknavn, index=brukindex)


        # Auto-adjust columns' width. 
        # Fra https://towardsdatascience.com/how-to-auto-adjust-the-width-of-excel-columns-with-pandas-excelwriter-60cee36e175e
        for column in mydf:
            if str(column ) not in sletteliste: 
                column_width = max(mydf[column].astype(str).map(len).max(), len(column)) + 3
                col_idx = mydf.columns.get_loc(column)
                writer.sheets[arknavn].set_column(col_idx, col_idx, column_width)

    writer.close( )
    print( f"skrev {len( dataFrameListe )} faner til {filnavn} ")

def swapXY( mygeom):
    """
    Bytter akserekkefølge på shapely-objekt, f.eks fra (lat,lon) => (lon, lat)

    Den akademiske definisjonen på EPSG:4326 følger geografiske fagtradisjon og definerer 
    at akserekkefølgen er (lat, lon). NVDB api er tro mot denne definisjonen. Mange utviklere 
    (og matematikere) er fastlåst i sitt tankesett om at X alltid kommer foran Y når objekter  
    skal plasseres i et koordinatsystem, uavhengig av hva EPSG-definisjonen skulle mene om akserekkefølgen.

    Mange (men ikke alle) kartprogrammer forventer derfor akserekkefølgen (lon,lat) på inngangsdata.  

    Denne funksjonen forsøker å bøte på problemet ved å tilby lettvint ombytting av akserekkefølgen, uavhengig 
    av geometritype (punkt, linje, flate...) og uavhengig av om objektet er 2D eller 3D. 

    Funksjonen bruker shapely-bibiloteket, som må finnes på systemet. 
    """ 
    if mygeom.has_z:
        mygeom = transform(lambda x, y,z: (y, x, z), mygeom)
    else: 
        mygeom = transform(lambda x, y: (y, x), mygeom)
    return mygeom 

def nvdbsok2geojson( sokeobjekt, filnavn, mittfilter=None, srid=4326, **kwargs ): 
    """
    Tar et NVDB søkeobjekt og lagrer som geojson med (lon,lat [,Z] ) koordinater - merk rekkefølgen. 

    Søkeobjektet blir modifisert med 'srid' : 4326. Eventuelle andre filtre er uberørt. Du kan 
    også føye til filtre med nøkkelordet mittfilter=dict, eksempel mittfilter={'kommune':5001}

    Funksjonen bruker bibliotekene shapely, pandas og geopandas, som må være installert på systemet. 

    ARGUMENTS
        sokeobjekt : NVDB søkeobjekt fra nvdbapiv3.nvdbFagdata( <NVDB objektType.ID>) eller nvdbapiv3.nvdbVegnett()

        filnavn: str, navn på geojson-fila. 

    KEYWORDS 
        mittfilter: None eller dictionary med de egenskapene du skal fitrere på

        srid: 4326 (alternativt kan du bruke 5973 hvis du synes det er en god idé med UTM 33 koordinater i geojson)

        Alle andre nøkkelord sendes videre til .to_records() - funksjonen, se docstring for denne samt 
        dokumentasjon på https://github.com/LtGlahn/nvdbapi-V3#torecords 

        .to_records() har en del valg på hva som skal være kilde for geometri (vegnett vs egengeometri, hvis den finnes). 
        Default er at geometri hentes fra vegnettet og at du får en forekomst per vegsegment hvis objektet har en 
        utstrekning over mer enn ett vegsegment. 
        Bruk kombinasjonen ` vegsegmenter=False, geometri=True  ` hvis du ønsker det motsatte (dvs såkalt "egengeometri")

    RETURNS 
        None 
    """

    sokeobjekt.filter( {'srid' : srid })

    if srid == 4326 or srid  == 5973:
        pass
    elif isinstance( srid, str):
        if srid.lower() == 'utm33':
            srid = 5973 
        elif srid.lower( ) == 'wgs84': 
            srid = 4326 
        else:
            raise ValueError( f"Ugyldig verdi for srid={srid} må enten være 5973, 4326, 'wgs84' eller 'utm33' ")            
    else:
        raise ValueError( f"Ugyldig verdi for srid={srid} må enten være 5973, 4326, 'wgs84' eller 'utm33' ")

    if not isinstance( filnavn, str): 
        raise ValueError( f"Filnavn må være av type str, ikke type {type(filnavn)} ")

    mydf = pd.DataFrame( sokeobjekt.to_records( **kwargs ))
    mydf['geometry'] = mydf['geometri'].apply( wkt.loads )
    if srid == 4326: 
        mydf['geometry'] = mydf['geometry'].apply( swapXY )
    myGdf = gpd.GeoDataFrame( mydf, geometry='geometry', crs=srid )

    # Geopandas kan ikke  lagre datatypen lister, aner ikke hvorfor
    # Så elementene vegsegmenter og relasjoner må fjernes, hvis de finnes 
    kanskjeslett = set(  ['vegsegmenter', 'relasjoner'] )
    slettdisse = kanskjeslett.intersection( list( myGdf.columns ))
    if  len( slettdisse ) > 0: 
        myGdf.drop( columns=list(slettdisse), inplace=True )

    myGdf.to_file( filnavn, driver='GeoJSON')

