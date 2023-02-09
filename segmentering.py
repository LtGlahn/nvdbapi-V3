"""
WORK IN PROGRESS - segmenteringsrutine

Segmenterer liste med (geo)dataframes med hensyn på en annen (geo)dataframe 

"""
import pdb
import json
from copy import deepcopy

import numpy as np 
from shapely import wkt
from shapely.geometry import Point, LineString
import pandas as pd
import geopandas as gpd 

import overlapp 

def segmenter( dfVeg, dfListe, agg={}, minsteLengde=0.1, glemNvdbDetaljer=True  ): 
    """
    Segmenterer liste med (geo)dataframes med hensyn på vegnett definert i dfVeg 

    Se også introduksjon på https://github.com/LtGlahn/nvdbapi-V3/blob/master/segmentering.md

    ARGUMENTS
        dfVeg : GeoDataFrame som definerer det vegnettet som er utgangspunkt for segmentering

        dfListe : Liste med GeoDataFrames med fagdata som skal segmenteres 

    KEYWORDS
        agg : Dictionary som angir aggregeringsregler, navnekonvensjon etc. Inspirert av pandas groupby - aggregering

        agg : {  5 : { 'Bruksområde' : { 'navn' : "Rekkverk bruksområde", 'agg' : 'AGGREGERINGSFUNKSJON' }}  }
                    Mulige aggregeringsfunksjoner er p.t: 
                    - 'first'  # Første forekomst (default)
                    - 'mean'   # Middelverdi
                    - 'median' # Medianverdi
                    - 'max'    # Største verdi 
                    - 'min'    # Minste verdi
                    - 'unique' # Ren tekst med kommaseparert verdier for de datavariantene som finnes på dette segmentet

                    Objekttyper og egenskaper som IKKE er nevnt i agg-dictionary beholder sitt opprinnelige egenskapsnavn
                    og summeres med metoden "first". 

        minsteLengde : float, default 0.1 meter (10 cm). Kortere segmenter enn dette blir slått sammen med nabosegmentet.

        glemNvdbDetaljer : bool, default True. Ignorerer mindre viktige NVDB-egenskaper som Prosjektreferanse, Eier etc. 

    RETURNS 

        Geodataframe med segmenteringsresultat

    TODO : Filtrer vekk kunstig små biter (degenerte biter)

    TODO : Ignorer meterverdi for vegsystemreferanse (parameterstyrt?)

    TODO : Lage fallback-rutine dersom (deler av) inngangsdata mangler vref-data. 
    Overlappfunksjonene har en funksjon vi kan bruke. 

    TODO : Sjekk for navnekollisjon egenskapsnavn i inngangsdata! 

    """
    def __lengdefilter( vpos:dict, myPos:list, LFAC:float, minsteLengde:float ):
        """
        Intern funksjon, kun tilgjengelig for segmenter-funksjonen! 
        Sikrer at alle segmenter har en på utstrekning > minsteLengde (i luftlengde, og langs veglenkeposisjoner omregnet til fysiske avstander). 
        Grunnen til at vi også må sjekke lengde med veglenkeposisjoner er RUNDKJØRINGER 
        - et spesialtilfelle er jo hvis vi er i enden av rundkjøringen: Da er jo avstanden i luftlengde mellom start og slutt temmelig liten
        (merk at denne omregningen fra veglenkepos =>geometrisk lengde er upresis pga uheldig numerikk, derfor runder vi ned med faktor .8 )

        Litt om vpos, mypos og de indeksene (løpenumrene) vi manipulerer her
          - vpos er en dictionary der nøklene = flyttalsverdier med posisjon på samme veglenke. En oppføring = ett potensielt 
            bruddpunkt til segmenteringsrutine. Dataverdien = shapely geografisk punktobjekt (fysiske koordinater for bruddpunkt) 
          - myPos er en sortert liste med alle potensielle bruddpunkter
          - nyPos er det ferdige subsettet av myPos, slik at alle segmenter < minsteLEngde 
          - Indeksene indexSluttArbSegment1 og indexSluttArbSegment2 er heltall, og iterer over myPos-listen
          - Logikken nedenfor (med manipulering av indekser) er for å konstruere et subsett av bruddpunkt (i riktig rekkefølge) 
            som sikrer at segmenteringen vår har en fysisk lengde > minsteLengde   

        Logikken er at vi konstruerer to "arbeidssegmenter" 
         - Arbeidssegment 1 er fra starten av vår vegnettsbit > minstelengde
         - Arbeidssegment 2 "spiser seg bortover" inntil arbeidssegment 2 > minstelengde. 
           Når det skjer så: 
              1) lagrer vi den veglenkeposisjonen som angir bruddpunkt mellom arbeidssegment 1 og 2
              2) Setter arbeidssegment 1 = arbeidssegment 2
              3) Starter nytt arbeidssegment 2
           Hvis vi når enden av vår vegnettsbit før arbeidssegment 2 har fått lengde > minstelengde så slås de to 
           arbeidssegmentene sammen (helt enkelt ved å LA VÆRE å lagre bruddpunktet mellom 1 og 2) 

        ADVARSEL: Langvarig stirring og grubling på ndekser (pekere) kan gi hodepine
        """
        nyPos = [ myPos[0]]
        # Lager arbeidssegment 1: 
        indexSluttArbSegment1 = 1 
        luftLengde = LineString( [ vpos[myPos[0]], vpos[myPos[indexSluttArbSegment1]] ] ).length
        linLengde  = LFAC * 0.8 * ( myPos[indexSluttArbSegment1] - myPos[0] )
        # import ipdb; ipdb.set_trace()

        # Jogger bortover langs vår veglenkebit til vi har lengde > minsteLengde 
        count = 0
        while luftLengde < minsteLengde and linLengde < minsteLengde and indexSluttArbSegment1 < len( myPos)-1: 
            indexSluttArbSegment1 += 1
            luftLengde = LineString( [ vpos[myPos[0]], vpos[myPos[indexSluttArbSegment1]] ] ).length
            linLengde  = LFAC * 0.8 * ( myPos[indexSluttArbSegment1] - myPos[0] )
            count += 1
            if count > 1000: 
                raise ValueError( f"Iterasjon {count}, tipper noe er gærnt")

        # OK, nå vet vi at de to pekerne (myPos[0],myPos[indexSluttArbSegment1]) definerer et segment > minsteLende
        # Dette er vårt "arbeidssegment1", en bit som vi vet er lang nok - men bruddpunktet (skillet arb.seg1 - arb.seg2) 
        # lagres ikke før vi er sikre på at PÅFØLGENDE segment (arbeidssegment2) også er langt nok.  
        # Vi starter med å la arb.segment 2 gå til første mulige bruddpunkt 
        indexSluttArbSegment2 = indexSluttArbSegment1 + 1
        for temp in range( indexSluttArbSegment2, len(myPos) ): 

            # indexSluttArbSegment2 kan løpe fra iteratorverdi temp gjennom while-løkka nedenfor
            if temp == indexSluttArbSegment2: 
                luftLengde = LineString( [ vpos[myPos[indexSluttArbSegment1]], vpos[myPos[indexSluttArbSegment2]] ] ).length
                linLengde  = LFAC * 0.8 * ( myPos[indexSluttArbSegment2] - myPos[indexSluttArbSegment1] )

                count = 0
                while luftLengde < minsteLengde and linLengde < minsteLengde and indexSluttArbSegment2 < len( myPos)-1: 
                    indexSluttArbSegment2 += 1
                    luftLengde = LineString( [ vpos[myPos[indexSluttArbSegment1]], vpos[myPos[indexSluttArbSegment2]] ] ).length
                    linLengde  = LFAC * 0.8 * ( myPos[indexSluttArbSegment2] - myPos[indexSluttArbSegment1] )
                    count += 1 
                    if count > 1000: 
                        raise ValueError( f"Iterasjon {count}, tipper noe er gærnt")
                # OK, nå vet vi at arb.segmen2, definert ved vpos[indexSluttArbSegment1] og vpos[indexSluttArbSegment2] ENTEN er lengre  > minsteLengde. 
                #  => Lagrer bruddpunkt mellom arb. segment 1 og 2, og setter arb.seg1 = arb.seg2, og starter en ny arb.seg2
                # ELLER så har vi kommet helt til slutten av veglenka vår (og da lagrer vi ikke bruddpunktet mellom arb.segment 1 og 2 
                if luftLengde > minsteLengde and linLengde > minsteLengde: 
                    nyPos.append( myPos[ indexSluttArbSegment1 ] )
                    indexSluttArbSegment1 = indexSluttArbSegment2 # Nytt arbeidssegment
                indexSluttArbSegment2 += 1 

        # Legger på aller, aller siste posisjon hvis den ikke har kommet til før. Dette sikrer at vi får den fulle utstrekningen av vår veglenkebit
        if nyPos[-1] != myPos[-1]: 
            nyPos.append( myPos[ -1 ] )

        return nyPos 
        # SLUTT privat funksjon __lengdefilter 

    dfVeg = dfVeg.copy()

    # Forkortelser 
    vl = 'veglenkesekvensid'
    fra = 'startposisjon'
    til = 'sluttposisjon'

    # Kolonner vi ignorerer i fagdata 
    ignorerCol = ['vref', vl, fra, til, 'nvdbId', 'objekttype', 'geometri', 'geometry', 'startdato', 'sluttdato', 
            'Eier', 'Prosjektreferanse', 'Vedlikeholdsansvarlig', 'Tilleggsinformasjon', 'ProsjektInternObjekt_ID',
             'relasjoner', 'veglenkesekvensid', 'detaljnivå',
            'typeVeg', 'kommune', 'fylke', 'vref', 'veglenkeType', 'vegkategori',
            'fase', 'vegnummer', 'relativPosisjon', 'adskilte_lop',
            'trafikantgruppe' ]

    if not isinstance( dfListe, list): 
        dfListe = [ dfListe ]

    data = []

    # Tar ett segment av gangen fra (geo)dataframe med vegnett
    for junk, vegbit in dfVeg.iterrows():

        vpos = { } # Dictionary med geometri for veglenkeposisjoner
        vref = { } # Dictionary med vegsystemreferanse - meterverdier. Vi antar at vi jobber innafor samme delstrekning  

        vpos[ vegbit[fra] ] = Point( vegbit['geometry'].coords[0] )
        vpos[ vegbit[til] ] = Point( vegbit['geometry'].coords[-1] )
        if 'vref' in dfVeg.columns: 
            vref[ vegbit[fra] ] = overlapp.splittvegsystemreferanse( vegbit['vref']  )[1]
            vref[ vegbit[til] ] = overlapp.splittvegsystemreferanse( vegbit['vref']  )[2]

        for myDf in dfListe: 
            myDf = myDf[ (myDf[vl] == vegbit[vl]) & (myDf[fra] < vegbit[til]) & (myDf[til] > vegbit[fra])]

            for ix, row in myDf.iterrows():
                vpos[ row[fra] ] = Point( row['geometry'].coords[0] )
                vpos[ row[til] ] = Point( row['geometry'].coords[-1] )
                if 'vref' in dfVeg.columns: 
                    vref[ row[fra] ] = overlapp.splittvegsystemreferanse( row['vref']  )[1]
                    vref[ row[til] ] = overlapp.splittvegsystemreferanse( row['vref']  )[2]


        # Finner stigender rekkefølge på veglenkeposisjoner 
        myPos =  [ x for x in sorted( vpos.keys() ) if x >= vegbit[fra] and x <= vegbit[til] ]

        # Må ha forhold mellom inkrement på lineær posisjon P => fysisk avstand, 
        # slik at vi kan regne ut fysisk avstand fra veglenkeposisjon 
        # y = f(P) = fysisk avstand / (P2-P1)
        LFAC = vegbit['geometry'].length / (vegbit[til] - vegbit[fra] ) 

        # Støyfilter, slår sammen biter < minstelengde
        myPos = __lengdefilter( vpos, myPos, LFAC, minsteLengde )

        for ix in range( len( myPos)-1): 
            nyttSeg = {  } 
            # Behandler fagdata som matcher disse veglenkeposisjonene
            for myDf in dfListe: 
                myDf2 = myDf[ (myDf[vl] == vegbit[vl]) & (myDf[fra] < myPos[ix+1]) & (myDf[til] > myPos[ix])]
                if len( myDf2 ) > 0: 
                    for myCol in myDf2.columns: 
                        if myCol not in ignorerCol:
                            if 'objekttype' in myDf.columns:  
                                vt = myDf.iloc[0]['objekttype'] 
                                print( f"Objekttype {vt}" )
                            else: 
                                vt = -9
                            nyttNavn = myCol 
                            # Har vi definert regler for navngiving og/eller aggregering for denne egenskapstypen via agg-dictionary? 
                            if vt in agg.keys() and myCol in agg[vt].keys(): 
                                if 'navn' in agg[vt][myCol]: 
                                    nyttNavn = agg[vt][myCol]['navn']
                                
                                if 'agg' in agg[vt][myCol]: 
                                    nyttSeg[nyttNavn] = oppsummerKolonne( myDf2[myCol].to_list( ), metode=agg[vt][myCol]['agg']  )
                                else: 
                                    nyttSeg[nyttNavn] = oppsummerKolonne( myDf2[myCol].to_list( ) )

                            else: 
                                nyttSeg[nyttNavn] = oppsummerKolonne( myDf2[myCol].to_list( ) )

            # Legger på vegsystemreferanse, lineære posisjoner og  geometri 
            nyttSeg[vl]  = vegbit[vl]
            nyttSeg[fra] = myPos[ix]
            nyttSeg[til] = myPos[ix+1] 
            if 'vref' in dfVeg.columns: 
                nyttSeg['vref'] = vegbit['vref'].lower().split('m')[0] + 'm' + str( vref[myPos[ix]]) + '-' + str( vref[myPos[ix+1]] )
            nyttSeg['geometry'] = overlapp.klippgeometriVeglenkepos( vegbit['geometry'], (vegbit[fra], vegbit[til] ), 
                                                    (myPos[ix], myPos[ix+1]), vpos, debug=False )

            data.append( nyttSeg )
            cp = deepcopy( nyttSeg)
            cp.pop( 'geometry', None )

            # print( json.dumps( cp, indent=4) )

    return gpd.GeoDataFrame( data, geometry='geometry', crs=5973 )


def oppsummerKolonne( myCol, metode='first' ): 
    """
    Oppsumerer en DataFrame-kolonne basert på datatype og hvilke unike verdier som finnes

    
    Mulige aggregeringsfunksjoner er p.t: 
        - 'first'  # Første forekomst (default)
        - 'mean'   # Middelverdi
        - 'median' # Medianverdi
        - 'max'    # Største verdi 
        - 'min'    # Minste verdi
        - 'unique' # Kommaseparert liste (som ren tekst)
    """
    assert isinstance( myCol, list ), f"Input argument #1 må være en liste"
    assert isinstance( metode, str ), f"Input nøkkelord metode='str' må være tekststreng (str)"
    metode = metode.lower()

    if metode == 'first': 
        return myCol[0]
    elif metode == 'mean': 
        return np.mean( myCol )
    elif metode == 'median': 
        return np.median( myCol )
    elif metode == 'max': 
        return np.max( myCol )
    elif metode == 'min': 
        return np.min( myCol )
    elif metode == 'unique': 
        myList = list( set( myCol ))
        return ','.join( [str(x ) for x in myList])
    else: 
        raise ValueError( f"Ukjent aggregeringsmetode {metode}")