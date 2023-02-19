"""
Henter datasett med veglenker, noder og porter fra NVDB api LES 
"""
import pandas as pd
import geopandas as gpd
from shapely import wkt 

import nvdbapiv3 

def hentvegnett( vegnettfilter={}, filnavn=None, forb=None ): 
    """
    Henter vegnett med alt av detaljer: Lenker, noder, porter
    """

    # Henter først segmentert vegnett
    vegseg = pd.DataFrame( nvdbapiv3.nvdbVegnett( filter=vegnettfilter ).to_records( kvalitetsparametre=True ) )
    vegseg['geometry'] = vegseg['geometri'].apply( wkt.loads )
    vegseg = gpd.GeoDataFrame( vegseg, geometry='geometry', crs=5973 )

    # Henter noder 
    noder = pd.DataFrame( nvdbapiv3.nvdbNoder( filter=vegnettfilter ).to_records( kvalitetsparametre=True ) )
    noder['geometry'] = noder['geometri'].apply( wkt.loads )
    noder = gpd.GeoDataFrame( noder, geometry='geometry', crs=5973 )

    # Henter ikke-segmenterte veglenker og noder 
    lenker = []
    noder = []
    porter = []

    if not forb: 
        forb = nvdbapiv3.apiforbindelse()

    for vlid in vegseg['veglenkesekvensid'].unique():
        r = forb.les( '/vegnett/veglenkesekvenser/' + str( vlid ) )
        if not r.ok:
            raise ValueError( )
        else:  
            data = r.json()

            for lenke in data['veglenker']: 
                enLenke = nvdbapiv3.flatutvegnettsegment( lenke, kvalitetsparametre=True ) 
                enLenke['låst_lengde'] = data['låst_lengde']
                enLenke['lengde_lenkesekvens'] = data['lengde']
                enLenke['porter'] = data['porter']
                lenker.append( enLenke )

            for port in data['porter']: 
                port['veglenkesekvensid'] = vlid

                # r = forb.les( port['tilkobling']['href']  )
                # if not r.ok:
                #     raise ValueError( 'Klarer ikke hente data for node '+r.url ) 
                # else: 
                #     node = r.json()
                #     port['geometry'] = wkt.loads( node['geometri']['wkt'] )
                #     node['geometry'] = wkt.loads( node['geometri']['wkt'] )
                #     noder.append( node )
                #     porter.append( port )

    lenker  = pd.DataFrame( lenker )
    lenker['geometry'] = lenker['geometri'].apply( wkt.loads )
    lenker.drop( columns=['geometri'], inplace=True ) 
    lenker = gpd.GeoDataFrame( lenker, geometry='geometry', crs=5973 )
    porter = gpd.GeoDataFrame( porter, geometry='geometry', crs=5973 )
    noder  = gpd.GeoDataFrame( noder, geometry='geometry', crs=5973)


    return { 'segmenterte lenker' : vegseg, 'lenker' : lenker, 'porter' : porter, 'noder' : noder }



