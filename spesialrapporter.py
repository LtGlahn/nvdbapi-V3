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
import numpy as np

import nvdbapiv3
from nvdbapiv3 import apiforbindelse
import nvdbgeotricks

def splitBruksklasse_vekt( bruksklasse ): 
    """
    Henter ut vekt- og bruksklassetall fra bruksklasse-streng og returnerer numeriske verdier

    Eks 'BK 10/60' => (10, 60) eller 'Bk10 - 50 tonn' => (10, 50)
    """

    bk = np.nan
    vekt = np.nan

    if isinstance( bruksklasse, float) or bruksklasse == None or bruksklasse == '' or 'Spesiell begrensning' in bruksklasse: 
        return( bk, vekt )

    bruksklasse = bruksklasse.strip()


    try: 

        if 'tonn' in bruksklasse.lower() and '-' in bruksklasse: 
            tmp  = bruksklasse.split( '-')
            vekt = int( tmp[1].lower().split('tonn')[0])
            if 't' in tmp[0].lower(): 
                bk   =  int(  tmp[0].lower().split('bkt')[1]   )
            else: 
                bk   =  int(  tmp[0].lower().split('bk')[1]   )
        
        elif '/' in bruksklasse and 'bk' in bruksklasse.lower(): 
            tmp = bruksklasse.split( '/')

            vekt    = int( tmp[1] )
            if 't' in tmp[0].lower(): 
               bk      = int(  tmp[0].lower().split('t')[1]   ) 
            else: 
               bk      = int(  tmp[0].lower().split('bk')[1]   )
        else: 
            print( f'Kan ikke splitte bruksklasse-verdi {bruksklasse} ')

    except ValueError: 
        print( f'Kan ikke splitte bruksklasse-verdi {bruksklasse} ')

        
    return (bk, vekt )

def brutusBKoverlapp( mittfilter=None, offisiell=False, kunEnTypeBK=None ): 
    """
    Finner de bruksklasse-objektene som overlapper med bruer. 

    finner overlapp mellom bruenes vegsegmenter og vegsegmenter for BK-typene "Normaltransport", "Spesialtransport" og "12/100 vegnett"
    Bruk evt nøkkelord kunEnTypeBK for å plukke ut en av disse. 
    
    Bruk nøkkelord offisiell=True for å hente uoffisielle BK-verdier (krever innlogging)

    Brusøket kan snevres inn  med nøkkelord mittfilter={}, ref dokumentasjon for spørring etter vegobjekter 
    https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid_ 

    ARGUMENTS: 
        None

    KEYWORDS
        mittfilter=None (default) Valgfritt dictionary med eventuelle filtre for bruenes egenskaper, veg- eller områdefilter m.m. 
            Se nvdbapiv3.nvdbFagdata eller API dokumentasjon 
            https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid_ 

        offisiell=False (default) | True. Angir om vi skal bruke offisielle eller uoffisielle bruksklassedata (krever innlogging)

        kunEnTypeBK = None (default) eller en tekststreng som angir hvilke type bruksklasse vi skal hente. Lovlige verdier: 
                None        : Henter alle BK-variantene
                'normal'    : Kun Bruksklasse, normaltransport 
                'spesial'   : Kun Bruksklasse, Spesialtransport
                'tolv65'    : Kun Bruksklasse, 12/65 mobilkran m.m.
                'tolv100'   : Kun Bruksklasse, 12/100 vegnett
    
    RETURNS
        geopandas geodataframe
    """

    filteret = {}
    # Kopierer mittfilter for å unngå sideefekter 
    if mittfilter: 
        filteret = deepcopy( mittfilter )

    # Kun Brukategori = vegbru
    if 'egenskap' in filteret: 
        filteret ['egenskap'] = '1263=7304 and ' + filteret['egenskap']
    else: 
        filteret ['egenskap'] = '1263=7304'

    brusok = nvdbapiv3.nvdbFagdata( 60 )
    # brusok.filter( filteret )
    bruer = pd.DataFrame( brusok.to_records( relasjoner=False ) )
    bruer = bruer[ bruer['trafikantgruppe'] == 'K' ]

    #  BRUKSLAST/TOTALVEKT i utdraget.              I UTDRAG. Antar vi bruker BK normaltransport. Skal sammenligne BK og totalvekt. 
    # Veggruppe - fra spesialtransport              I UTDRAG  Spesialtransport
    # SV12/65 godkjent J/N                          I UTDRAG  BK 12/65 (finnes eller finnes ikke)
    # SV12/00 godjkent J/N                          I UTDRAG  BK 12/100 (finnes / finnes ikke)
    # SV 12/100 restriksjoner (sakte/sentrisk etc)  - nikx
    # SV 12/100 avstand                             - niks


    if offisiell: 
        normalprefiks = 'bk904_'
        spesialprefix = 'bk902_'
        tolv65prefix  = 'bk891_'
        tolv100prefix = 'bk893_'

        normalsok  = nvdbapiv3.nvdbFagdata( 904 ) #Normal
        spesialsok = nvdbapiv3.nvdbFagdata( 902 ) #Spesial
        tolv65sok  = nvdbapiv3.nvdbFagdata( 891 ) # 12/65 
        tolv100sok = nvdbapiv3.nvdbFagdata( 893 ) # 12/100 vegnett

    else: 
        normalprefiks = 'bk905_'
        spesialprefix = 'bk903_'
        tolv65prefix  = 'bk892_'
        tolv100prefix = 'bk894_'

        normalsok  = nvdbapiv3.nvdbFagdata( 905 ) 
        spesialsok = nvdbapiv3.nvdbFagdata( 903 )
        tolv65sok  = nvdbapiv3.nvdbFagdata( 892 )
        tolv100sok = nvdbapiv3.nvdbFagdata( 894 )

        normalsok.forbindelse.login( miljo='prodles', username='jajens' )
        spesialsok.forbindelse = normalsok.forbindelse 
        tolv65sok.forbindelse  = normalsok.forbindelse
        tolv100sok.forbindelse = normalsok.forbindelse

    normalsok.filter(  { 'overlapp' : '60' })
    spesialsok.filter( { 'overlapp' : '60' })
    tolv65sok.filter(  { 'overlapp' : '60' })
    tolv100sok.filter( { 'overlapp' : '60' })

    normal  = pd.DataFrame( normalsok.to_records(  relasjoner=False ))
    spesial = pd.DataFrame( spesialsok.to_records( relasjoner=False ))
    tolv65  = pd.DataFrame( tolv65sok.to_records(  relasjoner=False ))
    tolv100 = pd.DataFrame( tolv100sok.to_records( relasjoner=False ))

    normal['bktall'] = normal['Bruksklasse'].apply( lambda x : splitBruksklasse_vekt( x )[0] )  
    normal['bkvekt'] = normal['Bruksklasse'].apply( lambda x : splitBruksklasse_vekt( x )[1] )  
    # normal['Maks vogntoglengde'] = normal['Maks vogntoglengde'].apply( lambda x : float( x.replace( ',', '.') ) if '.' in x )

    # 'Vegliste gjelder alltid',
    sletteliste = [ 'objekttype', 'nvdbId', 'versjon', 'startdato',  
                    'detaljnivå', 'typeVeg', 'kommune', 'fylke', 'veglenkeType', 'segmentlengde', 
                    'geometri', 'vegkategori', 'fase', 'vegnummer', 'adskilte_lop', 
                    'trafikantgruppe', 'Strekningsbeskrivelse']

    slettelliste_normal  = ['Bruksklasse vinter'  ]

    normal.drop(  columns=sletteliste+slettelliste_normal, inplace=True )
    spesial.drop( columns=sletteliste+slettelliste_normal, inplace=True )
    tolv65.drop(  columns=sletteliste, inplace=True )
    tolv100.drop( columns=sletteliste, inplace=True )

    bruprefix = 'bru_'
    bruer = bruer.add_prefix( bruprefix )
    brucol_nvdbId = bruprefix + 'nvdbId'
    sluttresultat = None 
    # Overlapp bruer - normaltransport 
    if kunEnTypeBK == None or kunEnTypeBK == 'normal': 
        mellomresultat2 = nvdbgeotricks.finnoverlapp( bruer,           normal, prefixA=bruprefix, prefixB=normalprefiks, join='left')
        mellomresultat2.drop( columns=[ normalprefiks+'veglenkesekvensid', normalprefiks+'startposisjon', normalprefiks+'sluttposisjon' ], inplace=True )
        sluttresultat = mellomresultat2.copy()
    else: 
        mellomresultat2 = bruer
        
    # Overlapp bruer - spesial 
    if kunEnTypeBK == None or kunEnTypeBK == 'spesial': 
        mellomresultat4 = nvdbgeotricks.finnoverlapp( mellomresultat2, spesial, prefixA=bruprefix, prefixB=spesialprefix, join='left')
        mellomresultat4.drop( columns=[ spesialprefix+'veglenkesekvensid', spesialprefix+'startposisjon', spesialprefix+'sluttposisjon' ], inplace=True )
        sluttresultat = mellomresultat4.copy()
    else: 
        mellomresultat4 = bruer
    
    # Overlapp bruer - 12/65
    if kunEnTypeBK == None or kunEnTypeBK == 'tolv65': 
        mellomresultat6 = nvdbgeotricks.finnoverlapp( mellomresultat4, tolv65,  prefixA=bruprefix, prefixB=tolv65prefix, join='left')
        mellomresultat6.drop( columns=[ tolv65prefix+'veglenkesekvensid', tolv65prefix+'startposisjon', tolv65prefix+'sluttposisjon' ], inplace=True )
        sluttresultat = mellomresultat6.copy()
    else: 
        mellomresultat6 = bruer
    
    # Overlapp bruer - 12/100
    if kunEnTypeBK == None or kunEnTypeBK == 'tolv100': 
        mellomresultat8 = nvdbgeotricks.finnoverlapp( mellomresultat6, tolv100, prefixA=bruprefix, prefixB=tolv100prefix, join='left')
        mellomresultat8.drop( columns=[ tolv100prefix+'veglenkesekvensid', tolv100prefix+'startposisjon', tolv100prefix+'sluttposisjon' ], inplace=True )
        sluttresultat = mellomresultat8.copy()


    # Lager geodataframe 
    bruer['geometry'] = bruer[ 'bru_geometri'].apply( lambda x : wkt.loads( x ) )
    bruer = gpd.GeoDataFrame( bruer , geometry='geometry', crs=5973 ) 

    sluttresultat['geometry'] =  sluttresultat[ 'bru_geometri'].apply( lambda x : wkt.loads( x ) )
    minGdf = gpd.GeoDataFrame( sluttresultat , geometry='geometry', crs=5973 ) 

    return minGdf


def tunnelrapport( mittfilter=None  ):
    """
    Setter sammen tunnel, tunnelløp og en del fagdata

    Bruk nøkkelord mittfilter=dictionary med NVDB api LES filtermuligheter for å snevre inn søket 
        eks: mittfilter={ 'vegsystemreferanse' : 'Rv', fylke=30 } 

    returnerer TO dataframes, en med full rapport og en komprimert (per unike tunnelobjekt)
    """

    filteret = {}
    # Kopierer mittfilter for å unngå sideefekter 
    if mittfilter: 
        filteret = deepcopy( mittfilter )

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
    # Kan ikke ta for gitt at alle kolonnene finnes: 
    kolonner_finnes = set( mellomresultat3.columns ) 
    komprimertKolonner = list( kolonner_finnes.intersection( set( komprimertKolonner) ) )

    komprimert = mellomresultat3.drop_duplicates( subset=komprimertKolonner ).copy()

    # slett = ['t67_nvdbId', 't67_kommune', 't67_fylke', 't67_vref', 't67_startposisjon', 
    #             't67_sluttposisjon', 't67_segmentlengde', 't67_geometri']


    slett = ['t67_nvdbId', 't67_kommune', 't67_fylke', 't67_startposisjon', 
                't67_sluttposisjon', 't67_segmentlengde', 't67_geometri']


    komprimert.drop( columns=slett, inplace=True )

    return (mellomresultat3, komprimert )


def KOSTRAfiltrering( data:pd.DataFrame, trafikantgruppe='K', alledata=False  ): 
    """
    Filtrerer vegnett og fagdata etter KOSTRA-regelverket (fjerner adskilte løp=MOT, sideanlegg og konnekteringslenker)

    Bruk trafikantgruppe=None eller trafikantgruppe='G' for å få med både G/S veg og kjøreveg, evt bare G/S-veg

    ARGUMENTS
        data : Pandas DataFrame laget ut fra .to_records() funksjonen til nvdb vegnett eller nvdb fagdata søkeobjekt
                    til nvdbapiv3 - biblioteket https://github.com/LtGlahn/nvdbapi-V3 

    KEYWORDS
        trafikantgruppe : Defaultverdi = 'K'. Filtrerer på om det er vegnett for kjørende ('K') eller for gående+syklende ('G')
                    bruk verdien None dersom du ønsker alt vegnett (både gående og syklende)

        alledata = False, bool. Hvis du setter denne lik True så får du returnert orginaldatasettet tagget med verdiene 
                    'KOSTRAveg' eller 'IKKE Kostra-Veg' i den nye kolonnen 'KOSTRA-statistikk' 

    RETURNS
        pandas dataframe: Returnerer en selvstendig (redigerbar) pandas DataFrame med samme datastruktur som det du sendte inn
                    Inngangsdata skal IKKE bli endret pga "call-by-references", vi lager en kopi og reduserer denne med relevante
                    filtre.  
    """

    mydata = data.copy()
    if alledata: 
        mydata['KOSTRA-statistikk'] = 'IKKE Kostra-Veg'
        col_temp_indeks_SLETT = 'SLETT_asdfasdfasdf'
        mydata[col_temp_indeks_SLETT] = mydata.index 
        orginaldata = mydata.copy()

    ## Felles for vegnett og fagdata

    # Fjerner sideanlegg
    mydata = mydata[ ~mydata['vref'].str.contains( 'SD') ]

    # Fjerner adskilte løp = Mot
    mydata = mydata[ mydata['adskilte_lop'] != 'Mot' ] 

    # Typeveg
    mydata = mydata[ mydata['typeVeg'].isin([ 'Kanalisert veg','Enkel bilveg','Rampe','Rundkjøring','Gatetun' ])]

    # Verifisere at det ikke er noe kødd med skrivemåte adskilte løp
    test = [x.lower() for x in list( mydata['adskilte_lop'].unique()) if not pd.isnull(x) ]
    if 'mot' in test: 
        raise ValueError( f"Oppdater spesialrapporter.py/kostrafiltrering med nye skrivemåter adskilte løp: {test1} " )

    # Trafikantgruppe
    if trafikantgruppe:
        if isinstance( trafikantgruppe, str) and trafikantgruppe in [ 'G', 'K']:
            mydata = mydata[ mydata['trafikantgruppe'] == trafikantgruppe ]
        else: 
            raise ValueError( f"Ugyldig verdi '{trafikantgruppe}' for  trafikantgruppe, må være enten 'G' eller 'K'")

    ## Ulike kolonnenavn vegnett og fagdata
    if 'typeVeg_sosi' in mydata.columns: 
        typeVegCOL = 'type'

    elif 'nvdbId' in mydata.columns: 
        typeVegCOL = 'veglenkeType'
         
    else: 
        raise ValueError( f"Fant ikke de kolonnene jeg forventet av NVDB fagdata eller NVDB vegnett" )

    # Fjerner konnekteringslenker og evt kjørebane/kjørefelt i samme operasjon
    mydata = mydata[ mydata[typeVegCOL] == 'HOVED']

    # Kopierer slik at du kan redigere på sluttresultatet, dvs ikke en dataFrame som er et subsett av 
    # en annen dataframe med pekere (index) til orginal-DataFrame 
    retdata = mydata.copy()

    if alledata: 
        retdata['KOSTRA-statistikk'] = 'KOSTRAveg'
        ikkeKostra = orginaldata[ ~orginaldata[col_temp_indeks_SLETT].isin( retdata[col_temp_indeks_SLETT] )]
        retdata = pd.concat( [ retdata, ikkeKostra ] )
        retdata.drop( columns=col_temp_indeks_SLETT, inplace=True )
    
    return retdata
