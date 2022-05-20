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

from shapely import wkt 
from shapely.geometry import Point, LineString
# from shapely.ops import unary_union
import pandas as pd 
import geopandas as gpd 
from datetime import datetime
import numpy as np

import nvdbapiv3
from nvdbapiv3 import apiforbindelse

def finnoverlapp( dfA, dfB, prefixA=None, prefixB=None, join='inner', klippgeometri=False,  klippvegsystemreferanse=True, debug=False ): 
    """
    Finner overlapp mellom to (geo)pandas (geo)dataframes med veglenkeposisjoner. 
    
    For å minimere navnekollisjon gir vi et prefiks til alle kolonnenanv i Dataframe B basert på objekttypen 
    (prefikset kan overstyres med nøkkelord prefixB )

    Returverdien er en dataframe med alle vegsegmenter som overlapper. Ett vegobjekt har gjerne flere vegsegmenter. 
    Hvis man ønsker en rad per vegobjekt-kombinasjon må man filtrere inputada i forkant eller resultatene i 
    etterkant. Det mest lettvinte er da å fjerne duplikater basert på Nvdb ID (vegobjekt id). 

    Hvis du har en verdikjede hvor du ønsker å kombinere mange dataett (for eksempel mange ulike objekttyper) så 
    må du selv ta ansvar for å unngå navnekollisjon og forvirring. Vi har tre metoder: 

        1) Definer hvilken objekttype som alltid blir dfA i koblingene. Kolonnenavnene i dfA endres ikke i 
        resultatdatasettet, og kan derfor "gjenbrukes" når resultatdatasettet kobles med dataframes for andre 
        objekttyper. For eksempel dersom du kobler tunnelløp med fartsgrense og trafikkmengde kan du gjøre noe slikt: 

        resultat1 = finnoverlapp( dfTunnellop, dfFartsgrenser  ) 
        resultat2 = finnoverlapp( resultat1, dfTrafikkmengde )

        resultat2 har da tunnelløp koblet med fartsgrenser (med forstavelsen t105_ ) og trafikkmengde (med forstavelsen t540_ )

        2) Ta eksplisitt kontroll over prefiks med nøkkelordene prefixA, prefixB. Merk at prefiks kun føyes til kolonnenavn 
        dersom det ikke finnes fra før, så vi inngår prefiks av typen t67_t67_ 

        3) Fjern "overflødige" kolonner fra mellomliggende resultater, gjerne kombinert med tricks 2) 
    
    Samme navnelogikk er brukt i funksjonen finndatter.  
    
    ARGUMENTS
        dfA, dfB - Pandas dataframe eller Geopandas geodataframe, eller kombinasjon. Returverdi blir identisk med dfA. 

    KEYWORDS
        prefixA=None Valgfri tekststreng med det prefikset som skal føyes til navn i dfA, eller det prefikset som 
                     er brukt fordi dfA er resultatet fra en tidligere kobling 

        prefixB=None Valgfri tekststreng med det prefikset som skal føyes til navn i dfB. Hvis ikke angitt så komponerer vi 
                     prefiks ut fra objektTypeID, for eksempel "67_" for 67 Tunnelløp. 

        join = 'inner' | 'left' . Hva slags sql-join vi skal gjøre, mest aktuelle er 'INNER' (default) eller 'LEFT'. I prinsippet en hvilke
                    som helst variant som er støttet av sqlite3.

        klippgeometri = False (default) | True. Klipper geometri slik at den får riktig utstrekning ihht overlapp på veglenkeposisjoner.

        klippvegsystemreferanse = True (default) | False. Endrer eller oppretter kolonnen "vegsystemreferanse" slik at meterverdiene får riktig overlapp-utstrekning 
                                                    (ved å ta maksimum og minimumsverdi av fra- og tilmeter for de to dataframene)

        debug = False (default) | True . Printer ut mer detaljer om hva som skjer underveis

    RETURNS
        Pandas DataFrame, eller Geopandas Geodataframe, avhengig av hva dfA er for slag. 

    TODO: Inputdata er Vegnett + vegnett eller vegobjekter + vegnett ? (Trengs dette?)   

    """

    # Lager kopier, så vi ikke får kjipe sideeffekter av orginaldatasettet 
    dfA = dfA.copy()
    dfB = dfB.copy()

    col_vlinkA  = 'veglenkesekvensid'   
    col_startA  = 'startposisjon'   
    col_sluttA  = 'sluttposisjon'
    col_relposA = 'relativPosisjon'
    col_geomA   = 'geometry'
    col_stedfestingA = 'stedfesting'

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

    # Må gjøre om shapely-objekter til Well Known Text, ellers klager sql'en vår 
    if isinstance( dfA.iloc[0][col_geomA], LineString): 
        dfA[col_geomA] = dfA[col_geomA].apply( lambda x : x.wkt )
    if isinstance( dfB.iloc[0][col_geomB], LineString): 
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

    # Har vi punkt-vs punkt? Spesialcase. De andre tifellene (linje vs linje, punkt-linje eller linje-punkt)
    # kan vi håndtere fint ved å trickse med å sette startposisjon, sluttposisjon - navnente lik  relativPosisjon - kolonnen
    # Vi kategoriserer de to 

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

    if typeA == 'PUNKT' and typeB == 'PUNKT': 
        qry = ( f"select * from A\n"
                f"{join.upper()} JOIN B ON\n"
                f"A.{col_vlinkA} = B.{col_vlinkB} and\n"
                f"A.{col_relposA} = B{col_relposB} "
            )
    else: 
        qry = ( f"select * from A\n"
                f"{join.upper()} JOIN B ON\n"
                f"A.{col_vlinkA} = B.{col_vlinkB} and\n"
                f"A.{col_startA} < B.{col_sluttB} and\n"
                f"A.{col_sluttA} > B.{col_startB} "
            )

    if debug: 
        print( "Join-spørring:\n", qry )

    conn = sqlite3.connect( ':memory:')
    dfA.to_sql( 'A', conn, index=False )
    dfB.to_sql( 'B', conn, index=False )
    joined = pd.read_sql_query( qry, conn )

    # EKSEMPELKODE!
    # LBger virituell database, slik at vi kan gjøre SQL-spørringer
    # conn = sqlite3.connect( ':memory:')
    # temp2010.to_sql( 'v2010', conn, index=False )
    # temp2009.to_sql( 'v2009', conn, index=False )

    # qry = """
    # select  max( v2010.startposisjon, v2009.d2009_startposisjon ) as frapos, 
    #         min( v2010.sluttposisjon, v2009.d2009_sluttposisjon ) as tilpos, 
    #         * from v2009
    #         INNER JOIN v2010 ON 
    #         v2009.d2009_veglenkesekvensid = v2010.veglenkesekvensid and
    #         v2009.d2009_startposisjon     < v2010.sluttposisjon and 
    #         v2009.d2009_sluttposisjon     > v2010.startposisjon
    # """
    #
    # joined = pd.read_sql_query( qry, conn)        



    if klippgeometri: 
        if col_geomA in joined.columns and col_geomB in joined.columns: 

            tmp = joined.apply( lambda x : finnoverlappgeometri( x[col_geomA], x[col_geomB], x[col_startA], x[col_sluttA], x[col_startB], x[col_sluttB], debug=debug  ) , axis=1) 
            joined['geometry']      = tmp.apply( lambda x : x[0] )
            joined['startposisjon'] = tmp.apply( lambda x : x[1] )
            joined['sluttposisjon'] = tmp.apply( lambda x : x[2] )

            joined = gpd.GeoDataFrame( joined, geometry='geometry', crs='epsg:5973')
            joined['segmentlengde'] = joined['geometry'].apply( lambda x: x.length )


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
            joined['vegsystemreferanse'] = joined.apply( lambda x : vegsystemreferanseoverlapp( x[col_vrefA], x[col_vrefB]  ), axis=1 )

    return joined 



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
        minGdf.drop( 'vegsegmenter', 1, inplace=True)

    minGdf.drop( 'geometri', 1, inplace=True)
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

    writer.save( )
    print( f"skrev {len( dataFrameListe )} faner til {filnavn} ")

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

