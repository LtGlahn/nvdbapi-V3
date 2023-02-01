"""
En samling rutiner for å sjekke om to objekter (objektversjoner) har identiske 
eller ulike egenskaper, stedfesting eller datter-relasjoner. 

Krever at du har biblioteket deepdiff installert på systemet. 
https://zepworks.com/deepdiff/current/

Som i tillegg til pipy (pip install) også finnes på conda-forge 
https://anaconda.org/conda-forge/deepdiff
"""
import re
from copy import deepcopy
import json

from deepdiff import DeepDiff
# Må ha deepdiff installert på systemet!
# https://zepworks.com/deepdiff/current/
# Som i tillegg til pipy (pip install) også finnes på conda-forge 
# https://anaconda.org/conda-forge/deepdiff


import nvdbapiv3

def sammenlignEgenskaper( vegobjekter, forb=None ): 
    """
    Sammenligner egenskapsverdier, stedfesting og datter-relasjoner for en liste med vegobjekter / objektversjoner

    Denne listen kan være dictionary lest direkte fra LES vegobjekter, eller lenke til objektversjon
    
    Returnerer dictionary med nøklene "identiske" og "avviker". 

    Identisk-oppføringene er en dictionary som helt enkelt gjengir det datainnholdet som er identisk. 
    Nøklene i denne er lik navnet på de egenskapene (stedfestingene, relasjonene) som finnes og er identisk 
    for alle objektene i listen

    Avviker-oppføringen er litt mer komplisert. Slik som for "identis"-dictonary har vi en nøkkel lik nvnet på den 
    egenskapen (stedfestingen, relasjonen) som sammenlignes. Under her igjen er enda en dictionary, med en eller flere 
    nøkkel for hver objektversjon med denne egenskapen. Nøkkelen her er bygget opp etter mønster <NvdbID>versjon<versjonsNummer>.
    Datainnholdet er egenskapverdien for denne objektversjonen.  
    Eksempel

    { 'avviker' : { 
        'Eier' :{ '212407375versjon5': {'id': 7999,
                            'navn': 'Eier',
                            'egenskapstype': 'Tekstenum',
                            'datatype': 'FlerverdiAttributt, Tekst',
                            'verdi': 'Stat, Statens vegvesen',
                            'enum_id': 10265}}  
                 }
    }

    
    """

    identiske = {   }
    kanskje_identiske = { }
    avviker   = {   }

    if not forb: 
        forb = nvdbapiv3.apiforbindelse( )

    startobj = vegobjekter[0]
    if isinstance( startobj, str): 
        r = forb.les( startobj )
        if r.ok: 
            startobj = r.json()
        else: 
            raise ValueError( f"Klarte ikke hente data med href {r.url}"  )

    if not isinstance( startobj, dict): 
        raise ValueError( f"Input data må være dictionary eller URL til objektversjon som faktisk finnes")
    
    # dictionary med alle egenskapvarianter
    startobj['egenskapdict'] = { x['navn'] : x for x in startobj['egenskaper']  }

#     startEgenskaper = plukkutEgenskaper( [ x['navn'] for x in startobj['egenskaper'] ], plukkType='egenskaper' )
    startEgenskaper = [ x['navn'] for x in startobj['egenskaper'] ] 
    
    startobjKey = str(startobj['id']) + 'versjon' + str( startobj['metadata']['versjon'])
    
    for egenskap in startEgenskaper: 
        kanskje_identiske[egenskap] = startobj['egenskapdict'][egenskap]

    for obj in vegobjekter[1:]:

        if isinstance( obj, str): 
            r = forb.les( obj )
            if r.ok: 
                obj = r.json()
            else: 
                raise ValueError( f"Klarte ikke hente data med href {r.url}"  )

        if not isinstance( obj, dict): 
            raise ValueError(  f"Input data må være dictionary eller URL til objektversjon som faktisk finnes" )


        obj['egenskapdict'] = { x['navn'] : x for x in obj['egenskaper'] }
#         objEgenskaper = plukkutEgenskaper( [ x['navn'] for x in obj['egenskaper'] ], plukkType='egenskaper' )
        objEgenskaper = [ x['navn'] for x in obj['egenskaper'] ]
        for egenskap in objEgenskaper: 
            mykey = str(obj['id']) + 'versjon' + str( obj['metadata']['versjon'])              
            
            if egenskap in kanskje_identiske: 
                
                if sammenlignEnkeltEgenskap( kanskje_identiske[egenskap], obj['egenskapdict'][egenskap]  ): 
                    pass
                    # Identiske, gjør ingenting
                else: 
                    # Flytter egenskap fra kanskje_identiske til avviker 
                    start_feilet = kanskje_identiske.pop( egenskap )
                    avviker[egenskap] = {}
                    avviker[egenskap][startobjKey] = start_feilet
                    
                    # Føyer dette objektets egenskap til i feilet-dictionary
                    avviker[egenskap][mykey] = obj['egenskapdict'][egenskap]
                
                # Test for å avgjøre om egenskapen er identiske
                # Logikk for hva som skjer når de er identiske vs når de avviker
            elif egenskap in avviker: 
                avviker[egenskap][mykey] = obj['egenskapdict'][egenskap]
            else: 

                if not egenskap in avviker: 
                    avviker[egenskap] = {}
                avviker[egenskap][mykey] = obj['egenskapdict'][egenskap]
                
        # Sjekker om vi har egenskapverdier i eldste objektversjon som IKKE finnes i nyere objektversjoner
        for egenskap in startEgenskaper: 
            if egenskap not in objEgenskaper: 
                if egenskap not in avviker: 
                    avviker[egenskap] = {}
                
                avviker[egenskap][startobjKey] = startobj['egenskapdict'][egenskap]
                junk = kanskje_identiske.pop( egenskap )

    return { 'identiske' : kanskje_identiske, 'avviker' : avviker}

def plukkutEgenskaper( egenskapsNavn, plukkType='egenskaper'): 
    """
    Filtererer egenskapsnavn ut fra om det er stedfesting (LokasjonsAttributt elller PunktTilknytning), relasjoner eller "vanlige" egenskaper

    ARGUMENTS
        egenskapsnavn = Liste med navn på egenskaper

    KEYWORDS 
        plukkType = 'egenskaper' (default), 'relasjoner', 'stedfesting' 

    RETURNS
        liste med egenskapsnavn filtrert etter regelverket 
    """

    stedfesting = ['PunktTilknytning', 'Liste av lokasjonsattributt']

    if plukkType == 'egenskaper': 
        returnListe = [ x for x in egenskapsNavn if not x in stedfesting ]
        returnListe = [ x for x in returnListe if not 'Assosiert' in x ]
    elif plukkType == 'relasjoner': 
        returnListe = [ x for x in egenskapsNavn if 'Assosiert' in x ]
    elif plukkType == 'stedfesting': 
        returnListe = [ x for x in egenskapsNavn if x in stedfesting ]
    else: 
        raise ValueError( f"The value {plukkType} for keyword plukkType is not accepted, it must be one of 'egenskaper', 'relasjoner' or 'stedfesting'")

    return returnListe

def sammenlignEnkeltEgenskap( eg1, eg2  ): 
    """
    Returnerer True hvis egenskapsverdiene er identiske. 
    """
    
    like = False 
    if 'geometri' in eg1['navn'].lower(): 
        like = sammelignEgenGeometrier( eg1, eg2)
    
    else:
        presisjon = 3
        if eg1['navn'].lower() in ['liste av lokasjonsattributt', 'PunktTilknytning']: 
            presisjon  = 8
        
        differanser = DeepDiff( eg1, eg2, significant_digits=presisjon, ignore_order=True  )
        if differanser == {}: 
            like = True 
        
    return like 

def sammelignEgenGeometrier( eg1, eg2): 
    """
    returnerer True hvis både tallene i geometrien  metadata (kvalitetsparametre) er like med 3 desimalers presisjon 
    """
    
    e1 = deepcopy( eg1 )
    e2 = deepcopy( eg2 )
    wkt1 = e1.pop('verdi')
    wkt2 = e2.pop( 'verdi')
    
    # Sammenligner metadata og kvalitetsparametre for geometrien
    differ1 = DeepDiff( e1, e2, significant_digits=3)
#     print( differ )
    
    # Sammenligner WKT-streng ved å gjøre alt om til ei (meningsløs) liste med tall 
    # Sjekker med 3 desimalers nøyaktighet (tilsvarer millimeter)
    liste1 = wkt2bambusListe( wkt1 )
    liste2 = wkt2bambusListe( wkt2 )
    differ2 = DeepDiff( liste1, liste2, significant_digits=3 )
 
    if differ1 == {} and differ2 == {}: 
        return True
    else: 
        return False 
    
def wkt2bambusListe( mywkt:str ): 
    """
    Hjelpefunksjon for å sammenligne geometrier
    
    Geometrien reduseres til en meningsløs liste med koordinatenes tallverdier. 
    """
    
    tempstr = re.sub( r'[a-zA-Z()]',  '', mywkt)
    re.sub( ',', ' ', tempstr )
    tempList = tempstr.split()
    return tempList
    
def dekodLesFeilmelding( responsobjekt ): 
    """
    Prøver å fiske ut LES-feilmeldinger fra requests respons-objekt

    Eks: 

        http 410 Gone 
        [   {
                code: 4016,
                message: "Feature 914876641, version 2 of type 241 gone!",
                help_url: "https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/"
            }
        ]

      blir til tekststrengen "http 410 Gone : Feature 914876641, version 2 of type 241 gone!"

    """
    melding = str( responsobjekt.status_code ) + " " + responsobjekt.reason
    msg = ''
    try: 
        info = responsobjekt.json()
        if isinstance( info, list) and len( info ) > 0 and 'message' in info[0]: 
            msg = info[0]['message']
        else: 
            msg = responsobjekt.text
    except JSONDecodeError: 
        msg = responsobjekt.text

    melding += ' : ' + msg 
    return melding 

def stedfestingSammendrag( stedfesting ): 
    """
    Komprimerer dictionary med stedfesting til kompakt tekststreng. 
    """
    retval = {}
    # Punkt 
    if stedfesting['navn'] == 'PunktTilknytning': 
        retval = str( stedfesting['relativPosisjon']) + '@' + str( stedfesting['veglenkesekvensid'])
        if 'retning' in stedfesting: 
            retval += ' ' + stedfesting['retning']
            
        if 'sideposisjon' in stedfesting: 
            retval += ' ' + stedfesting['sideposisjon']
            
        if 'kjørefelt' in stedfesting and len( stedfesting['kjørefelt'] ) > 0 : 
            retval += ' felt: ' + '#'.join( stedfesting['kjørefelt'] )
    
    elif stedfesting['navn'] == 'Liste av lokasjonsattributt': 
        # Liste med stedfestingverdier 
        tempdata = { }
        
        for linje in stedfesting['innhold']: 
            
            tempdata[ linje['veglenkesekvensid'] ] = str( linje['startposisjon'] ) + '-' + \
                    str( linje['sluttposisjon']) + '@' + str( linje['veglenkesekvensid']  ) 
            
            if 'retning' in linje: 
                tempdata[ linje['veglenkesekvensid'] ] += ' ' + linje['retning']

            if 'sideposisjon' in linje: 
                tempdata[ linje['veglenkesekvensid'] ] += ' ' + linje['sideposisjon']

            if 'kjørefelt' in linje and len( linje['kjørefelt'] ) > 0 : 
                tempdata[ linje['veglenkesekvensid'] ] += ' felt: ' + '#'.join( linje['kjørefelt'] )
            
        # Sorterer på veglenkesekvensId 
        vlenkid = list( tempdata.keys())
        vlenkid.sort()
        tempList = [ tempdata[x] for x in vlenkid ]
        retval = ','.join( tempList )
            
    else: 
        print( f"Kan ikke dekode stedfesting")
        print( stedfesting )
    
    return retval 
    
def objektdatoer( objektId, forb=None  ): 
    """
    Printer start- og sluttdato for alle objektversjoner for et objekt

    ARGUMENTS
        objektId - int: NVDB ID til objektet som skal undersøkes

    KEYWORDS
        forb : None eller et objekt av typen nvdbapiv3.apiforbindelse, som håndterer kommunikasjon mot LES 
    
    RETURNS
        none 
    """

    if not forb: 
        forb = nvdbapiv3.apiforbindelse()

    r = forb.les( '/vegobjekt', params={'id' : str( objektId ) } )
    if r.ok: 
        siste_objdata = r.json()
        
        if 'href' in siste_objdata: 
            siste_objektversjon = int( siste_objdata['href'].split('/')[-1] )
            data = []
            if siste_objektversjon > 1: 
                 for vid in range( 1, siste_objektversjon): 
                    r2 = forb.les( '/vegobjekter/' + str( siste_objdata['metadata']['type']['id'] ) + '/' + str( objektId) + '/' + str(vid) )
                    if r2.ok: 
                        data.append( r2.json() )
                    else: 
                        print( f"Fant ikke data: {r2.url}")
                        data.append( { 'id' : objektId, 'href' : '',  'metadata' : { 'startdato' : '---- -- -- ---- -- -- <= MANGLER / trolig fjernet?', 'versjon' : vid } }  )

            data.append( siste_objdata )

            # Ser om det ligger noen høyere versjoner på lur, vet aldri? 
            for vid in range( siste_objektversjon+1, siste_objektversjon+2):
                r2 = forb.les( '/vegobjekt/' + str( siste_objdata['metadata']['type']['id'] ) + '/' + str( objektId) )
                if r2.ok: 
                    data.append( r2.json() )
                

            print( f"Versjoner for NVDB objektid {objektId} type { siste_objdata['metadata']['type']['id']} {siste_objdata['metadata']['type']['navn']}  ")
            for obj in data: 
                sluttdato = '----      '
                if 'sluttdato' in obj['metadata']: 
                    sluttdato = obj['metadata']['sluttdato']
                print( f"{obj['id']} versjon {obj['metadata']['versjon']} {obj['metadata']['startdato']} {sluttdato} \t {obj['href']} ")

        else: 
            print( f"Ugyldig svar på spørring {r.url} \n{r.text[:250]}.... ")
    else: 
        print( f"Kan ikke hente NVDB objekt {objektId} : http { dekodLesFeilmelding( r ) } ")


def egenskapsavvikDetaljert( egenskapAnalyse:dict, eldsteVersjon:int ): 
    """
    Gir en detaljert oppsummering av de egenskapverdiene som er ulike for to objekter / objektversjoner
    
    Returnerer dictionary med to oppføringer per egenskapverdi: En for hver objekt / objektversjon
    """
    
    retval = {}
    
    for myKey in egenskapAnalyse['avviker'].keys(): 
        
        for ojbVersjonId in egenskapAnalyse['avviker'][myKey].keys():
            junk, versjonsId = ojbVersjonId.split( 'versjon')

            if int( versjonsId ) == eldsteVersjon: 
                eldreYngre = 'Eldre'
            else: 
                eldreYngre = 'Yngre'

            infoKey = f"{eldreYngre} (v{versjonsId}) {myKey}"
            
            if 'verdi' in egenskapAnalyse['avviker'][myKey][ojbVersjonId]: 
                retval[ infoKey ] = egenskapAnalyse['avviker'][myKey][ojbVersjonId]['verdi']
            elif 'ssosiert' in myKey and 'innhold' in egenskapAnalyse['avviker'][myKey][ojbVersjonId]:
                # Relasjoner er på formen 
                # {'Assosierte Rekkverksende': {'370453487versjon3': {'id': 220057,
                # 'navn': 'Assosierte Rekkverksende',
                # 'egenskapstype': 'Liste',
                # 'datatype': 'Liste',
                # 'innhold': [{'id': 200057,
                # 'navn': 'Assosiert Rekkverksende',
                # 'egenskapstype': 'Assosiasjon',
                # 'datatype': 'Assosiasjon',
                # 'verdi': 370453468}]},
                temp3 = [ str( x['verdi'] ) for x in egenskapAnalyse['avviker'][myKey][ojbVersjonId]['innhold'] ]
                temp3.sort()
                retval[ infoKey ] = ','.join( temp3)
                
            elif 'PunktTilknytning' == egenskapAnalyse['avviker'][myKey][ojbVersjonId]['navn']: 
                retval[ infoKey ] = stedfestingSammendrag( egenskapAnalyse['avviker'][myKey][ojbVersjonId] )
                
            elif 'Liste av lokasjonsattributt' == egenskapAnalyse['avviker'][myKey][ojbVersjonId]['navn']: 
                retval[ infoKey ] = stedfestingSammendrag( egenskapAnalyse['avviker'][myKey][ojbVersjonId] )
            else:
                print( f"SKjønte ikke datainnholdet her {myKey} - {ojbVersjonId}" )
                print( egenskapAnalyse['avviker'][myKey][ojbVersjonId] )
                

                
    return retval 