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

from shapely import wkt 
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime

import nvdbapiv3
from nvdbapiv3 import apiforbindelse

def finnoverlapp( dfA, dfB, prefixB=None ): 
    """
    Finner overlapp mellom to (geo)pandas (geo)dataframes med veglenkeposisjoner. 
    
    For å minimere navnekollisjon gir vi et prefiks til alle kolonnenanv i Dataframe B basert på objekttypen 
    (prefikset kan overstyres med nøkkelord prefixB )

    Returverdien er en (geo)dataframe med alle vegsegmenter som overlapper. Ett vegobjekt har gjerne flere vegsegmenter. 
    Hvis man ønsker en rad per vegobjekt-kombinasjon må man filtrere dette i etterkant. Det mest lettvinte er da å fjerne 
    duplikater basert på Nvdb ID (vegobjekt id). 

    ARGUMENTS
        dfA, dfB - Pandas dataframe eller Geopandas geodataframe, eller kombinasjon. Returverdi blir identisk med dfA. 

    KEYWORDS
        prefixB=None Valgfri tekststreng med det prefikset som skal føyes til navn i dfB 

    RETURNS
        Pandas DataFrame, eller Geopandas Geodataframe, avhengig av hva dfA er for slag. 

    TODO: MVP
    TODO: Håndtere valgfri kombinasjon av punkt- og linjestedfesting 
    TODO: Inputdata er Vegnett + vegnett eller vegobjekter + vegnett ? (Trengs dette?)   
    """

    raise NotImplementedError( "Har ikke fått laget denne ennå, sjekk om noen dager")



def finnDatter( morDf, datterDf, addprefix_datter=True, prefix=None, nvdbIdKolonne=None, relasjonsKolonne=None   ): 
    """
    Finner relasjoner mellom vegobjekter i (geo)dataframe 
    
    Returnerer ny dataframe hvor alle elementer i datterDf er påført informasjon fra mor-objektet hentet fra morDf 

    For å unngå navnekollisjon er standardoppførselen å føye forstavelsen kolonnenavn <vegobjektTypeId>_ til 
    alle kolonnenavn i datterdf. Denne oppførselen reguleres med nøkkelordene addprefix_datter og prefix. 

    ARGUMENTS: 
        morDf, datterDf: Pandas dataframe eller geopandas geodataframe. 

    KEYWORDS: 
        addprefix_datter=True | False. Skal vi føye til prefiks på kolonnenavnene i datterDf? 

        prefix=None eller tekstreng. Spesifiserer tekststreng for datterobjektenes prefix. Hvis None så 
        avleder vi prefiks ut fra objekttypen i datterDf 

        nvdbIdKolonne: Tekststreng med kolonnenavn for nvdbId i morDf. Hvis ikke angitt bruker vi kolonnen nvdbID eller
                        eller et kolonnenavn der 'nvdbId' inngår som del av navnet

        relasjonskolonne: Tekststreng med kolonnenanv for relasjon-dictionary i datterDf. Hvis ikke angitt finner vi et 
                        kolonnenavn der 'relasjoner' inngår som del av navnet. 

    RETURNS
        dataFrame eller Geodataframe (samme som morDf)
    """

    if addprefix_datter and not prefix: 
        if not 'objekttype' in datterDf.columns: 
            print( 'finnDatter: Fant ikke objekttype blant kolonnenavn, angi prefiks manuelt')
        else: 
            objektType = list( datterDf['objekttype'].unique() ) 
            if len( objektType ) > 1: 
                print( f"finnDatter: Flere objekttyper i datterDf, vrient å døpe om da... bruker første forekomst {str(objektType[0]) + '_'} ")
            datterPrefix = str( objektType[0]) + '_'

    # Finner rett kolonnenavn for morDf 
    idKey = 'nvdbId'
    if nvdbIdKolonne: 
        idKey = nvdbIdKolonne

    if idKey not in morDf.keys():
        idKandidater = [ x for x in list( morDf.index ) if 'nvdbid' in x.lower()  ]
        assert len( idKandidater ) == 1,  f"Fant ingen NvdbId - kolonne blant kolonnenavn for morDf"
        idKey = idKandidater[0]

    # Lager kopier, så vi ikke får kjipe sideeffekter av orginaldatasettet 
    mDf = morDf.drop_duplicates( subset=idKey ).copy()
    dDf = datterDf.copy()


    if addprefix_datter: 
        dDf = dDf.add_prefix( datterPrefix )

    # Finner rett kolonnenavn for relasjoner i datterDf: 
    relKey = 'relasjoner'
    if relasjonsKolonne: 
        relKey = relasjonsKolonne

    if relKey not in dDf.keys(): 
        idKandidater = [ x for x in list( dDf.columns ) if 'relasjon' in x.lower()  ]
        assert len( idKandidater ) == 1,  f"Fant ingen relasjon - kolonne blant kolonnenavn for datterDf"
        relKey = idKandidater[0]


    # Rett navn NVDB ID datterobjekt
    idKandidater = [ x for x in list( dDf.columns ) if 'nvdbid' in x.lower()  ]
    assert len( idKandidater ) == 1,  f"Fant ingen unik NvdbId - kolonne blant kolonnenavn for datterDf"
    datterIdKey = idKandidater[0]     

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
                print( f"Flere mødre angitt for datterobjekt {row[datterIdKey]}, men fant kun ett treff i morDf" )

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

    mindf['geometry'] = mindf['geometri'].apply( wkt.loads )
    minGdf = gpd.GeoDataFrame( mindf, geometry='geometry', crs=5973 )       
    # må droppe kolonne vegsegmenter hvis data er hentet med vegsegmenter=False 
    if 'vegsegmenter' in minGdf.columns:
        minGdf.drop( 'vegsegmenter', 1, inplace=True)

    minGdf.drop( 'geometri', 1, inplace=True)
    minGdf.to_file( filnavn, layer=lagnavn, driver="GPKG")  



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
        vegsegmenter=True, geometri=False. Ett enkelt objekt blir da repetert for hvert vegsegment som det er 
        tilknyttet (stedfestet til). 
        
        Standardverdiene vegsegmenter=False, geometri=True er valgt ut fra antagelsen om at du ønsker 
        en rad per objekt, uten duplisering. 

    RETURNS 
        None 
    """

    if not '.gpkg' in filnavn: 
        filnavn = filnavn + '_' + datetime.today().strftime('%Y-%m-%d') + '.gpkg'

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

        # Lagringsrutine skilt ut med funksjonen records2gpkg, IKKE TESTET (men bør gå greit) 
        if len( rec ) > 0: 
            records2gpkg( rec, filnavn, lagnavn )
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
        
