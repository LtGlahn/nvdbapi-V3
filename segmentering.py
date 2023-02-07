"""
WORK IN PROGRESS - segmenteringsrutine

Segmenterer liste med (geo)dataframes med hensyn på en annen (geo)dataframe 

"""
import pdb

import numpy as np 
from shapely import wkt
from shapely.geometry import Point, LineString
import pandas as pd
import geopandas as gpd 

import overlapp 

def segmenter( dfVeg, dfListe): 
    """
    Segmenterer liste med (geo)dataframes med hensyn på vegnettet beskrevet i dfVeg 

    TODO : Filtrer vekk kunstig små biter (degenerte biter)

    TODO : Segmenter med hensyn på vegsystemreferanse (parameterstyrt?)

    """

    dfVeg = dfVeg.copy()

    # Forkortelser 
    vl = 'veglenkesekvensid'
    fra = 'startposisjon'
    til = 'sluttposisjon'

    # Kolonner vi ignorerer i fagdata 
    ignorerCol = ['vref', vl, fra, til, 'nvdbId', 'objektType', 'geometri', 'geometry']

    if not isinstance( dfListe, list): 
        dfListe = [ dfListe ]

    data = []

    # Tar ett segment av gangen fra (geo)dataframe med vegnett
    for junk, vegbit in dfVeg.iterrows():

        vpos = { } # Dictionary med geometri for veglenkeposisjoner
        vref = { } # Dictionary med vegsystemreferanse - meterverdier. Vi antar at vi jobber innafor samme delstrekning  

        vpos[ vegbit[fra] ] = Point( vegbit['geometry'].coords[0] )
        vpos[ vegbit[til] ] = Point( vegbit['geometry'].coords[-1] )
        vref[ vegbit[fra] ] = overlapp.splittvegsystemreferanse( vegbit['vref']  )[1]
        vref[ vegbit[til] ] = overlapp.splittvegsystemreferanse( vegbit['vref']  )[2]

        for myDf in dfListe: 
            myDf = myDf[ (myDf[vl] == vegbit[vl]) & (myDf[fra] < vegbit[til]) & (myDf[til] > vegbit[fra])]

            for ix, row in myDf.iterrows():
                vpos[ row[fra] ] = Point( row['geometry'].coords[0] )
                vpos[ row[til] ] = Point( row['geometry'].coords[-1] )
                vref[ row[fra] ] = overlapp.splittvegsystemreferanse( row['vref']  )[1]
                vref[ row[til] ] = overlapp.splittvegsystemreferanse( row['vref']  )[2]


        # Finner stigender rekkefølge på veglenkeposisjoner 
        myPos =  [ x for x in sorted( vpos.keys() ) if x >= vegbit[fra] and x <= vegbit[til] ]
        for ix in range( len( myPos)-1): 
            nyttSeg = {  } 
            # Behandler fagdata som matcher disse veglenkeposisjonene
            for myDf in dfListe: 
                myDf = myDf[ (myDf[vl] == vegbit[vl]) & (myDf[fra] < myPos[ix+1]) & (myDf[til] > myPos[ix])]
                if len( myDf ) > 0: 
                    for myCol in myDf.columns: 
                        if myCol not in ignorerCol: 
                            # nyttSeg[myCol] = myDf.iloc[0][myCol]
                            nyttSeg[myCol] = oppsummerKolonne( myDf[myCol].to_list( ) )


            # Legger på vegsystemreferanse, lineære posisjoner og  geometri 
            nyttSeg[vl]  = vegbit[vl]
            nyttSeg[fra] = myPos[ix]
            nyttSeg[til] = myPos[ix+1] 
            nyttSeg['vref'] = vegbit['vref'].lower().split('m')[0] + 'm' + str( vref[myPos[ix]]) + '-' + str( vref[myPos[ix+1]] )
            nyttSeg['geometry'] = overlapp.klippgeometriVeglenkepos( vegbit['geometry'], (vegbit[fra], vegbit[til] ), 
                                                    (myPos[ix], myPos[ix+1]), vpos, debug=False )

            data.append( nyttSeg )

            print( nyttSeg )

    return gpd.GeoDataFrame( data, geometry='geometry', crs=5973 )


def oppsummerKolonne( myCol, metode='best' ): 
    """
    Oppsumerer en DataFrame-kolonne basert på datatype og hvilke unike verdier som finnes
    """
    if len( myCol ) == 1: 
        return myCol[0]

    elif len( myCol ) == 0: 
        return None 
    elif isinstance( myCol[0], str): 
        myList = list( set( myCol ))
        return ','.join( [str(x ) for x in myList])
    elif isinstance( myCol[0], int) or isinstance( myCol[0], float): 
        return np.mean( myCol )
    else: 
        return None 