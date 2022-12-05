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

from deepdiff import DeepDiff
# Må ha deepdiff installert på systemet!
# https://zepworks.com/deepdiff/current/
# Som i tillegg til pipy (pip install) også finnes på conda-forge 
# https://anaconda.org/conda-forge/deepdiff


def sammenlignEgenskaper( vegobjekter ): 
    """
    Sammenligner egenskapsverdier, stedfesting og datter-relasjoner for en liste med vegobjekter
    
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

    startobj = vegobjekter[0]
    
    # dictionary med alle egenskapvarianter
    startobj['egenskapdict'] = { x['navn'] : x for x in startobj['egenskaper']  }

#     startEgenskaper = plukkutEgenskaper( [ x['navn'] for x in startobj['egenskaper'] ], plukkType='egenskaper' )
    startEgenskaper = [ x['navn'] for x in startobj['egenskaper'] ] 
    
    startobjKey = str(startobj['id']) + 'versjon' + str( startobj['metadata']['versjon'])
    
    for egenskap in startEgenskaper: 
        kanskje_identiske[egenskap] = startobj['egenskapdict'][egenskap]

    for obj in vegobjekter[1:]:

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
    
    
