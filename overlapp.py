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
import sqlite3
import json
import string
from sys import prefix
from xmlrpc.client import Boolean 
from numbers import Number


from shapely import wkt 
from shapely.geometry import Point, LineString
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime
import numpy as np
import pyproj 

import nvdbapiv3
from nvdbapiv3 import apiforbindelse

def finnoverlapp( dfA, dfB, prefixA=None, prefixB=None, join='inner', klippgeometri=True,  klippvegsystemreferanse=True, debug=False, crs=5973 ): 
    """
    Finner overlapp langs vegnettet mellom to (geo)pandas (geo)dataframes med veglenkeposisjoner av typen linje (fra-til)
    
    For å minimere navnekollisjon gir vi et prefiks til alle kolonnenanv i Dataframe B basert på objekttypen 
    (prefiks for begge dataframes kan overstyres med nøkkelord prefixA, prefixB )

    Returverdien er en (geo)dataframe med alle vegsegmenter som overlapper. 
    
    Merk at ett vegobjekt gjerne har gjerne flere vegsegmenter. Hvis man ønsker en rad per vegobjekt må man selv 
    kombinere objektets vegsegmenter til en sammenhengende linje. 

    Hvis du har en verdikjede hvor du ønsker å kombinere mange dataett (for eksempel mange ulike objekttyper) så 
    må du selv ta ansvar for å unngå navnekollisjon og forvirring. Vi har tre metoder: 

        1) Definer hvilken objekttype som alltid blir dfA i koblingene. Kolonnenavnene i dfA endres ikke i 
        resultatdatasettet, og kan derfor "gjenbrukes" når resultatdatasettet kobles med dataframes for andre 
        objekttyper. For eksempel dersom du kobler tunnelløp med fartsgrense og trafikkmengde kan du gjøre noe slikt: 

        resultat1 = finnoverlapp( dfTunnellop, dfFartsgrenser  ) 
        resultat2 = finnoverlapp( resultat1, dfTrafikkmengde )


        resultat1 har da tunnelløp koblet med fartsgrenser (med forstavelsen t105_), dvs kolonnen med fartsgrenseverdier heter 
        t105_Fartsgrense. 
        resultat2 har da resultat1 (tunnelløp pluss fartsmengde) kombinert med trafikkmengde (med forstavelsen t540_ ). 
        Fartsgrenseverdiene i resultat2 har da forstavelsen t540_t105, dvs kolonnen med fartsgrenseverdier heter t540_t105_Fartsgrense. 

        2) Ta eksplisitt kontroll over prefiks med nøkkelordene prefixA, prefixB. Merk at prefiks kun føyes til kolonnenavn 
        dersom det ikke finnes fra før, så vi inngår prefiks av typen t67_t67_ 

        3) Fjern "overflødige" kolonner fra mellomliggende resultater, gjerne kombinert med tricks 2) 
        
    ARGUMENTS
        dfA, dfB - Pandas dataframe eller Geopandas geodataframe, eller kombinasjon. Returverdi blir samme type som dfA. 

        Merk at geodataframe må gjøres om til dataframe for at SQL-implementasjonen skal fungere. Så man kan få en mer effektiv verdikjede ved å 
        konvertere til geodataframe etterpå. 

    KEYWORDS
        prefixA=None Valgfri tekststreng med det prefikset som skal føyes til navn i dfA, eller det prefikset som 
                     er brukt fordi dfA er resultatet fra en tidligere kobling 

        prefixB=None Valgfri tekststreng med det prefikset som skal føyes til navn i dfB. Hvis ikke angitt så komponerer vi 
                     prefiks ut fra objektTypeID, for eksempel "t67_" for 67 Tunnelløp. 

        join = 'INNER' eller 'LEFT' join er støttet.  

        klippgeometri = False (default) | True. Klipper geometri slik at den får riktig utstrekning ihht overlapp på veglenkeposisjoner.

        klippvegsystemreferanse = True (default) | False. Endrer eller oppretter kolonnen "vegsystemreferanse" slik at meterverdiene får riktig overlapp-utstrekning 
                                                    (ved å ta maksimum og minimumsverdi av fra- og tilmeter for de to dataframene)

        debug = False (default) | True . Printer ut mer detaljer om hva som skjer underveis

        crs = 5973 Koordinatsystem, default=EPSG:5973. For NVDB data vil det være innmari snålt å bruke noe annet. Hvis dfA er en GeoDataFrame
                    så henter vi crs-verdi fra dfA (hvis den finnes). 

                    Lat/lon bør konverteres til UTM koordinater. Dette biblioteket forutsetter at det gir mening å behandle koordinater som 
                    kartesiske størrelser. Hvilket funker fint på UTM, er trolig littegrann haltende men kanskje greit nok for Google Merkator, men 
                    katastrofe for lat/lon på norske breddegrader (lat/lon kan trolig funke sånn noenlunde nær ekvator). 
                    
    RETURNS
        Pandas DataFrame, eller Geopandas Geodataframe, avhengig av hva dfA er for slag. 

    TODO: Inputdata er Vegnett + vegnett eller vegobjekter + vegnett ? (Trengs dette?)   

    TODO: Left join NESTEN OK, tror vi? 

    TODO: Default oppførsel: Endrer verdier på de retu

    TODO: Med Left join på plass - bør vi refaktorere "innerjoin" geometrihåndtering? 

    TODO: Datasett med punkt (midlertidig deaktivert mens vi jobber med left join)

    """

    # Sjekker at vi har gyldige data
    assert isinstance(dfA, pd.core.frame.DataFrame) or isinstance( dfA, gpd.geodataframe.GeoDataFrame), f"Argument dfA må være av type pandas eller geopandas (Geo)DataFrame"
    assert isinstance(dfB, pd.core.frame.DataFrame) or isinstance( dfB, gpd.geodataframe.GeoDataFrame), f"Argument dfB må være av type pandas eller geopandas (Geo)DataFrame"
    jointypes = ['LEFT', 'INNER']
    assert isinstance( join, str), f"Join type må være tekststreng med en av verdiene {jointypes} "
    join = join.upper()
    assert join in jointypes, f"Ukjent join type {join}, må være en av tekstveridene {jointypes}"

    # Lager kopier, så vi ikke gir kjipe sideeffekter på orginaldata utafor funksjonen 
    dfA = dfA.copy()
    dfB = dfB.copy()

    col_vlinkA  = 'veglenkesekvensid'   
    col_startA  = 'startposisjon'   
    col_sluttA  = 'sluttposisjon'
    col_relposA = 'relativPosisjon'
    col_geomA   = 'geometry'
    col_stedfestingA = 'stedfesting'
    col_ferdig_vegsystemreferanse = 'vegsystemreferanse'    # Den ferdig klippede vegsystemreferansen 
    col_backup_fraposisjon        = 'SLETT_orginal_startposisjon'  # Tar vare på orginaldata for LEFT JOIN
    col_backup_tilposisjon        = 'SLETT_orginal_sluttposisjon'  # Tar vare på orginaldata for LEFT JOIN
    col_backup_geometri           = 'SLETT_orginal_geometri'

    if prefixA: 
        # Tester om prefikset er i bruk
        if len( [ x for x in list( dfA.columns ) if prefixA in x ]  ) == 0: 
            dfA = dfA.add_prefix( prefixA )

        col_vlinkA  = prefixA + col_vlinkA
        col_startA  = prefixA + col_startA
        col_sluttA  = prefixA + col_sluttA
        col_relposA = prefixA + col_relposA 
        col_geomA   = prefixA + col_geomA 
        col_stedfestingA = prefixA + col_stedfestingA

    # Gjetter på prefix B om den ikke finnes. 
    if not prefixB: 
        temp = [x for x in list( dfB.columns ) if 'objekttype' in x ]
        assert len(temp) == 1, f"finnoverlapp: Lette etter en kolonne kalt objekttype i dfB, fant {len(temp)} stk: {temp} "
        temp2 = list( dfB[temp[0]].unique() )
        assert len(temp2) == 1, f"finnoverlapp: Lette etter unik objekttype i dfB kolonne {temp[0]}, fant {len(temp2)} stk: {temp2} "
        prefixB = 't' + str( temp2[0] )  + '_'

    # Tester om prefikset allerede er i bruk: 
    if len( [ x for x in list( dfB.columns ) if prefixB in x ]  ) == 0: 
        dfB = dfB.add_prefix( prefixB )

    col_vlinkB  = prefixB + 'veglenkesekvensid' 
    col_startB  = prefixB + 'startposisjon' 
    col_sluttB  = prefixB + 'sluttposisjon'
    col_relposB = prefixB + 'relativPosisjon'
    col_geomB   = prefixB + 'geometry'
    col_stedfestingB = prefixB + 'stedfesting'

    # For noen datasett, f.eks fra QGIS, så må vi brette ut stedfestingsinformasjon
    if not col_vlinkA in dfA.columns and col_stedfestingA in dfA.columns and '-' in dfA.iloc[0][col_stedfestingA]: 
        tmp = dfA[col_stedfestingA].apply( splittstedfesting ) 
        dfA[col_startA] = tmp[0]
        dfA[col_sluttA] = tmp[1]
        dfA[col_vlinkA] = tmp[2]
    if not col_vlinkB in dfB.columns and col_stedfestingB in dfB.columns and '-' in dfB.iloc[0][col_stedfestingB]: 
        tmp = dfB[col_stedfestingB].apply( splittstedfesting )
        dfB[col_startB] = tmp[0]
        dfB[col_sluttB] = tmp[1]
        dfB[col_vlinkB] = tmp[2]

    if crs != 5973: 
        print( f"Advarsel - CRS={crs} avviker fra 5973, som er det vi vanligvis bruker. Sikker på at det er riktig?")

    # Må gjøre om GeoDataFrame => DataFrame
    # Returnerer GeodataFrame hvis dfA er GDF
    returner_GeoDataFrame = False 
    if isinstance( dfA, gpd.geodataframe.GeoDataFrame): 
        if isinstance( dfA.crs, pyproj.crs.crs.CRS) and dfA.crs != crs:
            print( f"Endrer angitt CRS={crs} => {dfA.crs} hentet fra første GeoDataFrame-argument dfA") 
            crs = dfA.crs 
        dfA = pd.DataFrame(dfA)
        returner_GeoDataFrame = True  

    if isinstance( dfB, gpd.geodataframe.GeoDataFrame): 
        dfB = pd.DataFrame(dfB)

    # Må gjøre om shapely-objekter til Well Known Text, ellers klager sql'en vår 
    if isinstance( dfA.iloc[0][col_geomA], LineString) or isinstance( dfA.iloc[0][col_geomA], Point): 
        dfA[col_geomA] = dfA[col_geomA].apply( lambda x : x.wkt )
    if isinstance( dfB.iloc[0][col_geomB], LineString) or isinstance( dfB.iloc[0][col_geomB], Point): 
        dfB[col_geomB] = dfB[col_geomB].apply( lambda x : x.wkt )

    # Har vi dictionary? Det liker ikke sql'en vår, gjør om til string 
    for col in dfA.columns: 
        if isinstance( dfA.iloc[0][col], dict ): 
            dfA[col] = dfA[col].apply( lambda x : json.dumps( x, ensure_ascii=False, indent=4 ))
            print( f"Datasett A: Gjør om kolonne {col} fra dictionary til JSON tekst" )

    for col in dfB.columns: 
        if isinstance( dfB.iloc[0][col], dict ): 
            dfB[col] = dfB[col].apply( lambda x : json.dumps( x, ensure_ascii=False, indent=4 ))
            print( f"Datasett B: Gjør om kolonne {col} fra dictionary til JSON tekst" )


    # Kvalitetssjekk på at vi har det som trengs: 
    assert col_vlinkA in dfA.columns, f"finnoverlapp: Fant ikke kolonne {col_vlinkA} i dfA {dfA.columns} "
    assert col_vlinkB in dfB.columns, f"finnoverlapp: Fant ikke kolonne {col_vlinkB} i dfB {dfB.columns} "

    typeA = ''
    typeB = ''
    if col_startA in dfA.columns and col_sluttA in dfA.columns: 
        typeA = 'LINJE'
    elif col_relposA in dfA.columns: 
        typeA = 'PUNKT'
        col_startA = col_relposA
        col_sluttA = col_relposA
    else: 
        raise ValueError( f"Finner ikke kolonner for veglenkeposisjon: {col_startA, col_sluttA} eller {col_relposA} i dfA")

    if col_startB in dfB.columns and col_sluttB in dfB.columns: 
        typeB = 'LINJE'
    elif col_relposB in dfB.columns: 
        typeB = 'PUNKT'
        col_startB = col_relposB
        col_sluttB = col_relposB
    else: 
        raise ValueError( f"Finner ikke kolonner for veglenkeposisjon: {col_startB, col_sluttB} eller {col_relposB} i dfB ")

    assert ( typeA == 'LINJE' and typeB == 'LINJE' ), f"Håndtering av punktobjekt midlertidig deaktivert, må ha strekningsobjekt som inngangsdata"

    # Logikk for overlapp. 
    # Vi må ALLTID finne INNER join, den trengs for å lage LEFT join   
    # Det som er trøblete er å finne 1:1 forhold mellom veglenkeposisjoner, geometri og vegsystemreferanser. Dette ble først løst for INNER join. 
    # 
    # Løsningen for LEFT join består av 
    #    1). De radene i dfA som IKKE inngå overhodet i INNER-join datasettet
    #    2). Finne de bitene av vegnettet fra dfA der biter er "klippet vekk" i INNER-join datasettet, og konstruere disse bitene
    #    3). Slå sammen datasett fra trinn 1) + trinn 2) med INNER-join datasettet
    #   
    # Trinn 2) kompliseres av at hvis f.eks to rekkverk overlapper hverandre i dfB så vil samme vegnett ha to representasjoner i INNER-join datasettet. 
    # For å finne motsatsen kan vi ikke analysere hver rad i resultatdatasettet: Vi må betrakte hver rad i orginaldatasettet dfA, finne **samlet utstrekning** i 
    # "innerjoin"-datasettet og så finne det som er "til overs".  Dette er jobben til funksjonen `antioverlapp`.` At vi tar høyde for mulig intern overlapp i dfB 
    # er grunnen til at denne funksjonen er såpass komplisert. 
    # 
    # Lager først indeks-kolonne i dfA, denne brukes til å finne trinn 1). Slettes etterpå
    temp_indexdfA_SLETT = 'SLETTMEG_arbeidsindeks_outer_join'
    dfA[temp_indexdfA_SLETT] = dfA.index

    # og tar vare på de orginale veglenkeposisjonene i dfA
    dfA[col_backup_fraposisjon] = dfA[col_startA]
    dfA[col_backup_tilposisjon] = dfA[col_sluttA]
    dfA[col_backup_geometri]    = dfA[col_geomA]

    qry = ( f"select * from A\n"
            f"INNER JOIN B ON\n"
            f"A.{col_vlinkA} = B.{col_vlinkB} and\n"
            f"A.{col_startA} < B.{col_sluttB} and\n"
            f"A.{col_sluttA} > B.{col_startB} "
        )

    if debug: 
        print( "Join-spørring:\n", qry )

    conn = sqlite3.connect( ':memory:')
    dfA.to_sql( 'A', conn, index=False )
    dfB.to_sql( 'B', conn, index=False )
    inner_joined = pd.read_sql_query( qry, conn )

    if klippgeometri: 
        if col_geomA in inner_joined.columns and col_geomB in inner_joined.columns: 

            tmp = inner_joined.apply( lambda x : finnoverlappgeometri( x[col_geomA], x[col_geomB], x[col_startA], x[col_sluttA], x[col_startB], x[col_sluttB], debug=debug  ) , axis=1) 
            inner_joined['geometry']      = tmp.apply( lambda x : x[0] )
            inner_joined['startposisjon'] = tmp.apply( lambda x : x[1] )
            inner_joined['sluttposisjon'] = tmp.apply( lambda x : x[2] )
            inner_joined['segmentlengde'] = inner_joined['geometry'].apply( lambda x: x.length )

    if klippvegsystemreferanse: 
        # Må finne vegsystemreferanse-kolonner
        kanKlippe = True  
        if not prefixA: 
            prefixA = ''

        if prefixA + 'vref' in dfA.columns: 
            col_vrefA = prefixA + 'vref'
        elif prefixA + 'vegsystemreferanse' in dfA.columns: 
            col_vrefA = prefixA + 'vegsystemreferanse'
        else: 
            kanKlippe = False 
            print( 'Fant ikke kolonner for vegreferanser i datasett A')

        if prefixB + 'vref' in dfB.columns: 
            col_vrefB = prefixB + 'vref'
        elif prefixA + 'vegsystemreferanse' in dfB.columns: 
            col_vrefB = prefixB + 'vegsystemreferanse'
        else: 
            kanKlippe = False 
            print( 'Fant ikke kolonner for vegreferanser i datasett B')

        if kanKlippe: 
            inner_joined[col_ferdig_vegsystemreferanse] = inner_joined.apply( lambda x : vegsystemreferanseoverlapp( x[col_vrefA], x[col_vrefB]  ), axis=1 )

    if returner_GeoDataFrame: 
        if isinstance( inner_joined.iloc[0]['geometry'], str): 
            inner_joined['geometry'] = inner_joined['geometry'].apply( wkt.loads )
        inner_joined = gpd.GeoDataFrame( inner_joined, geometry='geometry', crs=crs )

    if join == 'INNER':
        # inner_joined.drop( columns=[temp_indexdfA_SLETT, col_backup_fraposisjon, col_backup_tilposisjon, col_backup_geometri], inplace=True )
        return inner_joined 
    elif join == 'LEFT':
        returdata = [ inner_joined ] # Liste med dataFrames som skal returneres
        outer_ytterst = dfA[  ~dfA[temp_indexdfA_SLETT].isin( list( inner_joined[temp_indexdfA_SLETT].unique() )) ].copy()
        if len( outer_ytterst ) > 0: 

            # Vegsystemreferanse
            if klippvegsystemreferanse and kanKlippe: 
                outer_ytterst[col_ferdig_vegsystemreferanse] = outer_ytterst[col_vrefA]

            returdata.append( outer_ytterst ) # Dette er de radene i dFa med veglenkesekvenser  som overhodet ikke finnes i dfB
            
        # Så det komplekse: Finne de bitene av vegnettet som delvis er klippet (forminsket) i innerjoin-datasettet. 
        # Finner først de delene av innerjoin-datasettet med delvis overlapp
        delvisOverlapp =  inner_joined[ ( inner_joined[col_startA] != inner_joined[col_backup_fraposisjon] ) | \
                                        ( inner_joined[col_sluttA] != inner_joined[col_backup_tilposisjon] ) ]

        # Itererer per rad i ORGINAL-datasettet (dfA), det er her indeksen temp_indexdfA_SLETT kommer inn 
        # Nye og orginale veglenkeposisjoner legges i lister med tuple=(fra,til)
        delvisOverlappRader = list( delvisOverlapp[temp_indexdfA_SLETT].unique() )
        antioverlapp_liste = [] # Liste med dictionaries 
        for ii in delvisOverlappRader: 
            orginal = dfA[ dfA[temp_indexdfA_SLETT] == ii].iloc[0].to_dict()
            df = delvisOverlapp[ delvisOverlapp[temp_indexdfA_SLETT] == ii]
            nyeVposListe = []
            for junk, row in df.iterrows(): 
                nyeVposListe.append( ( row[col_startA], row[col_sluttA] ) )
            aa = antioverlapp(  [( orginal[col_backup_fraposisjon], orginal[col_backup_tilposisjon] ) ], nyeVposListe, debug=debug )
            if debug: 
                print( f"Orginal=({orginal[col_startA]},{orginal[col_sluttA]}), overlapp={nyeVposListe} => Antioverlapp: {aa}")
            for nyeVposisjoner in aa: 
                nyttSeg = deepcopy( orginal )
                orginalVposisjoner = (orginal[col_startA], orginal[col_sluttA])
                nyttSeg[col_geomA]                      = klippgeometriVeglenkepos( orginal[col_geomA], orginalVposisjoner, nyeVposisjoner, debug=debug  )
                nyttSeg[col_ferdig_vegsystemreferanse]  = estimerVegreferanse(      orginal[col_vrefA], orginalVposisjoner, nyeVposisjoner )
                nyttSeg[col_startA] = nyeVposisjoner[0]
                nyttSeg[col_sluttA] = nyeVposisjoner[1]
                antioverlapp_liste.append( nyttSeg )

        if len( antioverlapp_liste ) > 0: 
            returdata.append(  pd.DataFrame( antioverlapp_liste ) )

        retval = pd.concat( returdata, axis=0, ignore_index=True )
        # retval.drop( columns=[temp_indexdfA_SLETT, col_backup_fraposisjon, col_backup_tilposisjon, col_backup_geometri], inplace=True )
        # SJEKK OM VI SKAL RETURNERE GEODATAFRAME!
        return retval 

    else: 
        raise ValueError(f"Ukjent join type {join}, og tro meg - THIS REALLY SHOLD NOT HAPPEN, vi sjekket for {join} in {jointypes} ved oppstart!" )

def klippgeometriVeglenkepos( mygeom, orginalpos, nyepos, debug=False ): 
    """
    Klipper en geometri basert på dimmensjonsløse veglenkeposisjoner. Den nye geometrien matcher posisjonene i nyepos. 

    Returnerer tom geometri hvis veglenkeposisjonene ikke overlapper. 
    Returnerer orginalgeometri hvis de nye posisjonene har større utstrekning enn orginalposisjoner.
    Returnerer evt bare den biten som er innafor orginalgeometri hvis enten start eller slutt er utafor orginalposisjoner

    ARGUMENTS
        mygeom      : Shapely geometriobjekt eller Well Known Text (WKT)-streng 

        orginalpos  : tuple med fra-til veglenkeposisjoner for orginalgeometri

        nyepos      : tuple med nye fra-til veglenkeposisjoner for den nye geometrien. 
                           Nystart bør være >= orginal start, og ny slutt <= orginal start. 

    KEYWORDS 
        N/A 

    RETURNS 
        Samme som mygeom (Shapely geometriobjekt eller Well Known Tekst - string)
    """

    returnWKT = False 
    if isinstance( mygeom, str):
        mygeom = wkt.loads( mygeom )
        returnWKT = True 

    nygeom = deepcopy( mygeom )

    assert isinstance( orginalpos, tuple) and isinstance( nyepos, tuple), "Input argument orginalpos og nyepos må være tuple"
    assert orginalpos[1] >= orginalpos[0] and nyepos[1] >= nyepos[0], "Input argument orginalpos og nyepos må ha veglenkeposisjoner i stigende rekkefølge"
    # assert nyepos[0] >= orginalpos[0] and nyepos[1] <= orginalpos[1], "Start/slutt veglenkeposisjon-verdiene i nyepos må overlappe med dem i orginalpos"

    # # Har vi overlapp mellom gamle og nye veglenkeposisjoner? 
    # if orginalpos[0] < nyepos[1] and orginalpos[1] > nyepos[0]: 
    #     pass # Vi har overlapp
    # else: # Tom geometri 
    #     return LineString( )

    # # Har vi fullstendig overlapp, dvs nyepos starter før og slutter etter orginaldataene?
    # if nyepos[0] < orginalpos[0] and nyepos[1] > orginalpos[0]: 
    #     nygeom = mygeom 
    # elif 

    # Lengden orginalgeometri med skaleringsfaktor
    # lengde i meter (y) som funksjon av veglenkeposisjon (x): 
    #       f(x) = ax 
    # der a = lengde orginalgeometri / (orginal sluttposisjon-orginal startposisjon)
    orginal_lengde = nygeom.length
    LFAC = orginal_lengde / (orginalpos[1]-orginalpos[0])
    orginal_startmeter = LFAC * orginalpos[0]

    # Starter vi helt i begynnelsen på orginalgeometrien? Eller et stykke inn?
    # hvis JA så klipper vi det til etterpå 
    ny_reellmeterStart = 0          #  Målt i reell lengde på geometri 
    ny_reellmeterSlutt = None 
    if nyepos[0] > orginalpos[0]: 
        ny_reellmeterStart  = LFAC * nyepos[0] - orginal_startmeter 
    if nyepos[1] < orginalpos[0]: 
        ny_reellmeterSlutt = LFAC * nyepos[1] - orginal_startmeter

    if ny_reellmeterSlutt: 
        nygeom = shapelycut( nygeom, ny_reellmeterSlutt )[0]
    if ny_reellmeterStart > 0: 
        nygeom = shapelycut( nygeom, ny_reellmeterStart)[1]

    if debug: 
        print( f"Geometrilengde={orginal_lengde}, startMeter={orginal_startmeter}, orginalpos={orginalpos}, nyepos={nyepos}  " )
        print( f"  => klipper ut biten m{ny_reellmeterStart}-{ny_reellmeterSlutt} ")

    if returnWKT: 
        return nygeom.wkt
    else: 
        return nygeom


def estimerVegreferanse( vegsystemreferanse:str, orginalpos:tuple, nyepos:tuple, debug=True):
    """
    Regner ut meterverdier og returnerer ny vegreferanse som matcher de nye veglenkeposisjonene

    ARGUMENTS
        vegsystemreferanse : Tekststreng med vegsystemreferanse

        orginalpos: Tuple med veglenkeposisjoner (fra,til) som matcher vegsystemreferansen

        nyepos: Tuple med de nye veglenkeposisjonene som vi skal regne ut 

    KEYWORDS: 
        N/A 

    RETURNS
        vegsystemreferanse - tekststreng som matcher de nye posisjonene
    """

    assert isinstance( orginalpos, tuple) and isinstance( nyepos, tuple), "Argument orginalpos og nyepos må være tuple"
    assert orginalpos[1] >= orginalpos[0] and nyepos[1] >= nyepos[0], "Input argument orginalpos og nyepos må ha veglenkeposisjoner i stigende rekkefølge"
    assert nyepos[0] >= orginalpos[0] and nyepos[1] <= orginalpos[1], "Start/slutt veglenkeposisjon-verdiene i nyepos må overlappe med dem i orginalpos"

    (vegrefRot, fraM, tilM) = splittvegsystemreferanse( vegsystemreferanse )
    # Finner lineær funksjon mellom veglenkeposisjon og meterverdier 
    # meterverdi y = f(x) = a * x + C 
    # der a = (tilMeter - fraMeter)/(tilpos - frapos)
    #     C = fraMeter 

    A = (tilM-fraM)/(orginalpos[1]-orginalpos[0])
    C = fraM 
    nyFraM = A * nyepos[0] + C
    nyTilM = A * nyepos[1] + C

    meterTekst = 'M'
    if 'm' in vegsystemreferanse: 
        meterTekst = 'm'

    nyvegref = vegrefRot + meterTekst + str( int( nyFraM)) + '-' + str( int( nyTilM ) )
    return nyvegref


def joinvegsystemreferanser( vegsystemreferanser:list ):
    """
    Slår sammen en liste med vegsystemreferanser til en (muligens) kortere liste, basert på om meterverdier overlapper eller er tilstøtende
    Eks joinvegsystemreferanser( [ 'KV1244 S2D1 m787-826', 'KV1244 S2D1 m826-926' ]) => [ 'KV1244 S2D1 m787-926' ]
    """

    data = []
    for vref in vegsystemreferanser: 
        data.append( splittvegsystemreferanse( vref)  )

    mydf = pd.DataFrame( data, columns=['vrefrot','fra', 'til'])
    mydf.sort_values( by=['vrefrot', 'fra', 'til'], inplace=True )

    nyevref = []
    tempVref = {}

    for ix, row in mydf.iterrows(): 

        if tempVref == {}: # Start på iterasjonen, eller forrige runde mislyktes
            tempVref = { 'vrefrot' : row['vrefrot'], 'fra' : row['fra'], 'til' : row['til'] } 
        else: 
            if tempVref['vrefrot'].lower() == row['vrefrot'].lower() and tempVref['fra'] <= row['til'] and tempVref['til'] >= row['fra']: 
                tempVref['fra'] = min( row['fra'], tempVref['fra'])
                tempVref['til'] = max( row['til'], tempVref['til'])
            else: 
                nyevref.append( f"{tempVref['vrefrot']}m{tempVref['fra']}-{tempVref['til']}" )
                tempVref = {}

    # Må føye til det aller siste elementet. Dette er enten vrefRot (hvis det var suksess å sammeligne aller siste raden med
    # foregående verdier). Hvis den aller siste sammenligningen feilet så bruker vi dataene fra aller den aller siste raden (==row): 
    if tempVref == {}: 
        tempVref =  { 'vrefrot' : row['vrefrot'], 'fra' : row['fra'], 'til' : row['til'] } 
    nyevref.append(f"{tempVref['vrefrot']}m{tempVref['fra']}-{tempVref['til']}" )
        
    return nyevref

def splittvegsystemreferanse( vegsystemreferanse:string ): 
    """
    Deler en vegsystemreferanse opp i fra-meter, tilmeter og resten. 

    ARGUMENTS: 
        vegsystemreferanse  - tekst string

    KEYWORDS: 
        N/A

    RETURNS
        (vegsystemreferanserot, frameter, tilmeter) : Tuple med elementene vegsystemreferanserot (tekst string), frameter (int) og tilmeter (int)

    Eksempel: 
        ('EV6 K S78D1 ', 0, 674 ) = splittvegsystemreferanse( 'EV6 K S78D1 m0-674' )
        ('EV6 K S78D1 m454 SD1 ', 0, 112 ) = splittvegsystemreferanse( 'EV6 K S78D1 m454 SD1 m0-112' )
        ('EV6 K S78D1 m454 SD1 ', 14, 14 ) = splittvegsystemreferanse( 'EV6 K S78D1 m454 SD1 m14' )

    TODO: Kommer vi noensinne til å møte meterverdier med høyere presisjon enn nærmeste meter? 

    """
    vrefrot = ''
    frameter = None 
    tilmeter = None 

    assert isinstance( vegsystemreferanse, str), "Funksjonen splittvegsystemreferanse må ha tekststreng som input"

    # Store eller små bokstaver? 
    if 'M' in vegsystemreferanse: 
        skrivstorM = True 
        vegsystemreferanse = vegsystemreferanse.replace( 'M', 'm' )
    else: 
        skrivstorM = False 

    try: 

        if '-' in vegsystemreferanse: #                Strekning med fra- og til
            splitt1 = vegsystemreferanse.split( '-' )
            tilmeter = int( splitt1[-1]) 
            splitt2 = splitt1[0].split( 'm')
            frameter = int( splitt2[-1])
        else:                         #                Punkt på formen EV6 K S78D1 m99
            splitt2 = vegsystemreferanse.split( 'm' )
            frameter = int( splitt2[-1] )
            tilmeter = int( splitt2[-1] )

        vrefrot = ''.join( splitt2[0:-1])

    except (IndexError, ValueError) as err: 
        print( f'nvdbgeotricks.splittvegsystemreferanse: Klarer ikke finne fra-til meterverdier ut fra teksten "{vegsystemreferanse}" ' )

    if skrivstorM: 
        vrefrot = vrefrot.translate( 'm', 'M')

    return (vrefrot, frameter, tilmeter )

def vegsystemreferanseoverlapp( vref1:string, vref2:string ): 
    """
    Finner felles overlapp (hvis det finnes) for to vegsystemreferanesr 

    ARGUMENTS
        vref1, vref2 : Tekst, De to vegsystemreferansene med (potensiell) overlapp 

    KEYWORDS: 
        N/A

    RETURNS
        overlappvref : Tekst, 

    EKSEMPEL: 
        'EV6 K S78D1 m99-300' = vegsystemreferanseoverlapp( 'EV6 K S78D1 m0-300', 'EV6 K S78D1 m99-674' ) 
    """

    (vrefrot1, fra1, til1) = splittvegsystemreferanse( vref1 ) 
    (vrefrot2, fra2, til2) = splittvegsystemreferanse( vref2 ) 

    if fra1 <= til2 and fra2 <= til1 and vrefrot1.lower().strip() == vrefrot2.lower().strip(): 
        return vrefrot1 + 'm' + str(  max( fra1, fra2) ) + '-' + str( min( til1, til2 ))

    else: 
        print( f'nvdbgeotricks.vegsystemreferanseoverlapp: Ikke overlapp mellom vegsystemreferansene {vref1} og {vref2} ')  
        # from IPython import embed; embed() # DEBUG

    return ''


def splittstedfesting( mystring):
    """
    Splitter en stedfesting-streng på formen 0-1@1158097 i tre tall, dvs (0, 1, 1158097)

    ARGUMENTS: 
        mystring = Tekststreng på formen 0.0-1.0@1158097 

    KEYWORDS: 
        N/A
    
    RETURNS
        Tuple med (fraposisjon, tilposisjon, veglenkesekvensid)  

        Returnerer (None, None, None) hvis feiler 
    """

    frapos, tilpos, vlenkid = None, None, None  
    try: 
        splitt1 = mystring.split( '@')
        splitt2 = splitt1[0].split( '-')
        frapos = float( splitt2[0] )
        tilpos = float( splitt2[1] )
        vlenkid = int( splitt1[1] ) 
    except (IndexError, ValueError): 
        print( f"splittstedfesting feiler på tekst {mystring}")

    return pd.Series( [frapos, tilpos, vlenkid]) 


def vegreferanselengder( vegref ): 
    """
    Finner lengder basert på meterverdi av vegreferanse

    Takler helt fint dette med kryssdeler og sideanlegg, men forutsetter at vegsystemreferansen er formulert med 
    start- og sluttmeter, dvs du må ha m<start>-<slutt> bakerst i strengen, eksempel "FV44 S7D1 m6297-6305" 

    Hvis du har flere vegsystemreferanser kan du skille dem fra hverandre med komma, eksempel "FV4302 S1D1 m40-44,FV4302 S1D1 m300 KS1 m40-41"

    Gir ingen feilmelding hvis tolking av input-tekst feiler
    
    ARGUMENTS
        vegref : String, tekststreng som inneholder kommaseparert liste med vegsystemreferanser

    KEYWORDS 
        None 

    RETURNS
        lengde: Integer, heltall med lengde 
    """
    vrefbiter = vegref.split(',')
    lengde = 0 
    for vref in vrefbiter: 
        if '-' in vref: 
            biter = vref.split( '-')
            tilM = biter[-1]
            fraM = biter[-2].split()[-1]

            try: 
                fraM = int( ''.join( filter( str.isdigit, fraM)))
                tilM = int( tilM )
            except ValueError: 
                pass
            else: 
                lengde += abs( tilM - fraM   )

    return lengde 
    

def shapelycut( line, distance): 
    """
    Kutter ei linje i to på angitt punkt, målt som antall meter (dvs koordinatsystem-enheter) fra starten av linja

    Hentet fra shapely-dokumentasjonen, tilpasset både 2D og 3D koordinater
    https://shapely.readthedocs.io/en/stable/manual.html#linear-referencing-methods 

    Merk at alle avstander i shapely regnes i ren 2D, dvs ut fra X og Y i kartplane. 
    Eventuelle Z-koordinater blir riktig interpolert, men Z-verdier spiller ingen rolle i beregning av avstand. 
    For en 10% stigning vil differansen i 2D versus 3D være om lag 5%. Samtidig er det noen argumenter
    for det å være 100% konsekvent med å regne avstander i kartplan (x,y) - hvilket er det valget shapely har tatt. 

    ARGUMENTS
        line - Shapely LineString objekt

        distance - Avstand fra starten av linja til det punktet der vi skal kutte, i meter (eller mer presist: Koordinatsystem-enheter)

    KEYWORDS
        N/A

    RETURNS 
        liste med to shapely LineString - objekter, det første fra start av linja til angitt distanse (der den gamle linja ble kuttet), 
        den andre linja fra kuttpunkt til slutt. 
        Merk at hvis distance = 0 eller > line.lenght så returneres den oppprinnelige geometrien, dvs kun ett shapely-objekt i lista

    TODO: 
      -  Er det behov for å angi kuttpunkt som andel (dvs tall mellom 0 og 1) i stedet for fysiske avstander? 
    """

    if distance <= 0.0 or distance >= line.length:
        return [LineString(line)]
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance: # --------- Angitt punkt matcher eksakt med et punkt langs linja, trenger ikke interpolere 
            return [
                LineString(coords[:i+1]),
                LineString(coords[i:])]
        if pd > distance:  # ---------------- Må interpolere, fordi vi ligger et sted mellom foregående og neste punkt
            cp = line.interpolate(distance)
            if line.has_z: # -------------------------------- 3D koordinater
                return[ LineString( coords[:i] + [(cp.x, cp.y, cp.z)]), 
                        LineString( [(cp.x, cp.y, cp.z)] + coords[i:] )] 
                
            else:         # --------------------------------- 2D koordinater
                return [
                    LineString(coords[:i] + [(cp.x, cp.y)]),
                    LineString([(cp.x, cp.y)] + coords[i:])]



def antioverlapp( listeA:list, listeB:list, debug=False ): 
    """
    Finner de veglenkeposisjonene i listeA som IKKE overlapper med det som finnes i listeB

    ARGUMENTS
        listeA, listeB - liste med tupler med fra- og tilposisjoner langs samme veglenkesekvens
        Hver tuple har to flyttalls-verdier med 8 siffers presisjon som angir hhv fra- og tilposisjon på vegnettet 
        Vi sorterer og rydder opp i (slår sammen) evt internt overlapp i listeA eller listeB 

    KEYWORDS
        N/A

    RETURNS
        Liste med tupler 
    """

    def validerVeglenkeposTupler( listeA ): 
        """
        Intern funksjon for antioverlapp 
        Sjekker at en liste inneholder tupler med veglenkeposisjoner der fra-posisjon <= til-posisjon

        Returnerer True hvis godkjent, eller kaster en AssertionError 
        """

        assert isinstance( listeA, list), "Input argument må være liste"
        for myItem in listeA: 
            assert isinstance( myItem, tuple ),  "Input argument må være liste som inneholder tupler "
            assert len( myItem ) == 2, "Hvert tuple må ha to elementer"
            assert isinstance( myItem[0], Number) and isinstance( myItem[1], Number), "Hvert element i tuple må være et tall"
            assert myItem[0] >= 0 and myItem[1] <= 1, f"Hvert element i tuple må være et tall mellom 0 og 1, fant ( {myItem[0]}, {myItem[1]} )"
            assert myItem[0] <= myItem[1], f"Det første tallet i tuple må være mindre eller lik det andre tallet, fant ( {myItem[0]}, {myItem[1]} )"

        return True 

    assert validerVeglenkeposTupler( listeA), "Validering av listeA feiler, skal være liste med tuple(r) med fra-til posisjon"
    listeA.sort()
    assert isinstance( listeB, list), "Input argument #2 må være en liste"

    # Slår først sammen evt internt overlapp i listeA 
    tmp = []
    tempStart = listeA[0][0]
    tempSlutt = listeA[0][1]
    for  vlenk in listeA: 
        if vlenk[0] > tempSlutt: 
            tmp.append( (tempStart, tempSlutt ))
            tempStart = vlenk[0]
            tempSlutt = vlenk[1]

        elif vlenk[1] > tempSlutt: 
            tempSlutt = vlenk[1]

    tmp.append( (tempStart, tempSlutt ))
    if debug: 
        print( f"Orginal liste A={listeA}, ny liste A={tmp} ")
    listeA = tmp 

    if len( listeB) > 0: 
        assert validerVeglenkeposTupler( listeB ), f"Validering av listeB feiler, skal være liste med tuple(r) med fra-til posisjon"  
        listeB.sort( )
        
        # Slår sammen evt internt overlapp i listeB
        tmp = []
        tempStart = listeB[0][0]
        tempSlutt = listeB[0][1]
        for  vlenk in listeB: 
            if vlenk[0] > tempSlutt: 
                tmp.append( (tempStart, tempSlutt ))
                tempStart = vlenk[0]
                tempSlutt = vlenk[1]

            elif vlenk[1] > tempSlutt: 
                tempSlutt = vlenk[1]

        tmp.append( (tempStart, tempSlutt ))
        listeB = tmp 

        # Itererer over listeA og listeB: 

        # Algoritmen her forutsetter en velordnet, sortert liste der
        # evt interne overlapp i vlenkA eller vlenkB er slått sammen. 
        tmp = []
        for vlenkA in listeA: 
            tempStart = vlenkA[0]
            tempSlutt = vlenkA[1]
            fullstendigOverlapp = False 

            for vlenkB in listeB: 

                # vlenkB dekker vlenkA fullstendig 
                if vlenkB[0] <= tempStart and vlenkB[1] >= tempSlutt: 
                    fullstendigOverlapp = True  

                # vlenkB starter litt til høyre for starten på vlenkA
                # Da må vi kutte. Den biten til venstre lagres. 
                # Hvis det finnes en bit til høyre så sjekkes den mot neste 
                # vlenkB-element i listeB  
                if vlenkB[0] >= tempStart and vlenkB[0] <= tempSlutt: 
                    if vlenkB[0] > tempStart:                           # Har vi en bit til venstre for starten av vlenkB? 
                        tmp.append( (tempStart, vlenkB[0]) )            #   JA => Lagrer venstre bit, fram til starten av vlenkB 
                    if vlenkB[1] < tempSlutt:                           # Finnes det en bit til høyre? 
                        tempStart = vlenkB[1]                           #   JA => "Kutter" ved å flytte startpunkt => slutten av vlenkB
                    else:                                               #   NEI => vlenkB dekker resten av vlenkA 
                        fullstendigOverlapp = True  

            # Lagrer unna den biten som gjenstår etter at vi er ferdige med å kutte - hvis det gjenstår noe, da
            if not fullstendigOverlapp: 
                tmp.append( (tempStart, tempSlutt ) )

        if debug: 
            print( f"Anti-overlapp {listeA} med {listeB} => {tmp}  \n\n")
        return tmp 

    else: # listeB er tom
        return listeA



def finnoverlappgeometri( geom1:LineString, geom2:LineString, frapos1:float, tilpos1:float, frapos2:float, tilpos2:float, debug=False ): 
    """
    Tar to LineString-geometrier og "klipper til" felles geometrisk overlapp basert på dimmensjonsløse lineære posisjoner. 

    Eks (frapos1, tilpos1) = (0 0.8) og (frapos2, tilpos2) = (0.5, 1) gir overlappet (0.5, 0.8) Vi tar den korteste av geometriene
    (i dette tilfelle geom2) og klipper vekk det som er utafor (0.5, 0.8). På veien dit må vi selvsagt regne om fra 
    lineære posisjoner til fysiske avstander, dvs hvor mange meter tilsvarer intervallene 0.5-0.8 og 0.8-1 på geom2? 

    Returnerer tom geometri (dvs LineString(), uten koordinater) og None, None hvis det ikke er gyldig overlapp 

    Hvis en av geometriene er None, tom eller har null lengde så returneres den andre geometrien og tilhørende veglenkeposisjoner

    ARGUMENTS
        geom1, geom2 : Shapely LineString - objekter som skal finne overlapp 

    KEYWORDS
        debug: Boolean, False (default) | True. Skriver ut mer detaljer om hva som skjer 

    RETURNS 
        (nyGeom, nyFrapos, nyTilpos) : Tuple med ny geometri og nye lineære posisjoner

    """

    # Har vi fått WKT? Prøver å konvertere til shapely-objekter
    if isinstance( geom1, str): 
        geom1 = wkt.loads( geom1 )
    if isinstance( geom2, str): 
        geom2 = wkt.loads( geom2 )

    # Sjekker om begge geometriene er gyldige, returnerer den andre hvis ikke
    if not isinstance( geom1, LineString) or geom1.length == 0:
        return (geom2, frapos2, tilpos2)
    elif not isinstance( geom2, LineString ) or geom2.length == 0: 
        return( geom1, frapos1, tilpos1 )

    # Velger en geometri 
    if geom1.length < geom2.length: 
        kortgeom = geom1 
        kort_frapos = frapos1
        kort_tilpos = tilpos1
        lang_frapos = frapos2
        lang_tilpos = tilpos2 
    else: 
        kortgeom =  geom2 
        kort_frapos = frapos2
        kort_tilpos = tilpos2
        lang_frapos = frapos1
        lang_tilpos = tilpos1 

    # Sjekker om vi i det hele tatt har overlapp:
    if frapos1 < tilpos2 and tilpos1 > frapos2: 
        pass # godkjent
    else: 
        print( f"nvdbgeotricks.finnoverlappgeometri: Ingen overlapp på disse lineærposisjonene {frapos1}-{tilpos1} og {frapos2}-{tilpos2} ")
        return (LineString(), None, None )

    # Sjekker om det ene settet med geometrier fullstendig overlapper med det andre. 
    # I så fall returnerer vi bare den korteste geometrien 
    #     (geom1 utstrekning er subsett av geom2) ELLER (geom2 utstrekning er subsett av geom1)
    if (frapos1 >= frapos2 and tilpos1 <= tilpos2) or (frapos2 >= frapos1 and tilpos2 <= tilpos1): 
        if debug: 
            print( f"nvdbgeotricks.finnoverlappgeometri:Fullstendig overlapp {frapos1}-{tilpos1} og {frapos2}-{tilpos2} ")
        return (kortgeom, max(frapos1, frapos2), min( tilpos1, tilpos2) )

    # Siden vi jobber med den korteste geometrien (og har behandlet det trivielle tilfellet der den lengste 
    # fullstendig overlapper den korteste) så må den korteste geometrien kuttes enten i starten eller i slutten. 
    if kort_frapos < lang_frapos:  
        kuttpos = lang_frapos # Den korteste geometrien ligger på starten av den lengste. 
        geomindex = 1         # Dvs når vi kutter den korte geometrien så forkaster vi den første biten
                              # (som ligger foran der overlapp-sone), og tar vare på den siste   
    else: 
        kuttpos = lang_tilpos # Den korteste geometrien ligger på slutten av den lengste
        geomindex = 0         # Vi forkaster den siste biten (som er bak overlapp-sonen), og tar vare på den første biten

    # Sanity check 
    assert kuttpos >= kort_frapos and kuttpos <= kort_tilpos,  "Feil logikk i vår håndtering av lineære posisjoner" 

    dpos_hele = np.float64( kort_tilpos ) - np.float64( kort_frapos )
    dpos_kutt = np.float64( kuttpos ) - np.float64( kort_frapos )
    fraction_kutt = dpos_kutt / dpos_hele 
    ny_lengde = fraction_kutt * np.float64( kortgeom.length )
    assert ny_lengde <= np.float64( kortgeom.length ), "Ny lengde må være kortere enn opprinnelig lengde"
    geomliste = shapelycut( kortgeom, ny_lengde )
    # from IPython import embed; embed() # DEBUG
    if len( geomliste ) == 0: 
        print( "nvdbgeotricks.finnoverlappgeometri: Fikk ingen gyldig geometri fra nvdbgeotricks.shapelycut???")
        return (LineString(), None, None )
    elif len( geomliste ) == 1: 
        return ( geomliste[0],  max(frapos1, frapos2), min( tilpos1, tilpos2) )
    elif len( geomliste ) == 2: 
        return geomliste[geomindex],  max(frapos1, frapos2), min( tilpos1, tilpos2) 

