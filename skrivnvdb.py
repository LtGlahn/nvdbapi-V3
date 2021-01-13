# -*- coding: utf-8 -*-
"""
Kommunikasjon mot, og skriving til NVDB skriveapi https://apiskriv.vegdata.no/ 

Det anbefales STERKT at utvikling foregår mot docker-instans av skriveapi. 
https://www.vegdata.no/2016/03/09/utviklerutgave-av-skrive-apiet-tilgjengelig-pa-docker-hub/


apiskrivforbindelse - Klasse som håndterer alt det praktiske med 
innlogging mot skriveapi. Kan brukes til å lese data fra 
skriveapi-endrepunkt (skriveoperasjoner, endringssett, låser m.m.). 
Brukes av klassen endringssett. 

Merk funksjonen klientinfo('Passe unik tekststreng'). Denne setter headeren 
X-Client lik tekststrengen. Bruk det til å søke / filtrere / gruppere i 
skriveapi'ets kontrollpanel. Endringssett som hører sammen kan ha samme 
klientinfo, evt med små perturbasjoner. 

endringssett - Klasse som håndterer alle steg i skriveprosessen: 
 - registrering
 - validering
 - startskriving
 - sjekkfremdrift 
 
Selve endringssettet - de data som skal skrives / endres / lukkes / korrigeres / oppdateres - 
er en python-dict i endringssett.data  - attributten. Du kan legge data dit 
automatisk ved å sende dem inn som argument når du oppretter endringssett-objektet

En instans av endringssett-klassen har en  "apiskrivforbindelse"-instans på egenskapen "forbindelse". 
Denne kan evt byttes ut ved å kopiere en eksisterende forbindelse. Nyttig hvis du ønsker å logge inn kun 
en gang, men har flere endringssett. 

Eksempel
    e1 = endringssett( <dine skriveklare data>)
alternativt
    e1.endringssett()
    e1.data = <dine skriveklare data>

Eksempler på endringssett finner du i /generator/ - endepunktet i docker-instans, 
evt https://www.vegvesen.no/nvdb/apiskriv/generator/


EKSEMPEL, fullstending løype
    e1 = endringssett(<dine skriveklare data>)
    
    ELLER
    e1 = endringssett()
    e1.data = <dine skriveklare data>
    
    e1.forbindelse.login(username='deg', pw='dittPw', miljo='docker')
    # Gjør det enklere å søke / filtrere i kontrollpanelet
    e1.forbindelse.klientinfo('Tekststreng for å skille / gruppere dine endringssett')
    e1.registrer()
    e1.valider()
    e1.validertrespons
    e1.start_skriving()
    e1.sjekkfremdrift()
    

	
"""
import requests
import json
from datetime import datetime
import getpass
import pdb 
# from copy import deepcopy 

from nvdbapiv3 import apiforbindelse
        
#         """Leser data fra NVDB api"""
#         return self.requestsession.get( url=url, 
#                                        proxies=self.proxies,
#                                        headers=self.headers, 
#                                        **kwargs)
        

#     def checklock( self, endringsettID ): 
#         """Python request kall for å sjekke låser for endringssett.
        
#         Returnerer python requests objekt. 
#         """
#         url = self.apiurl + '/nvdb/apiskriv/kontrollpanel/data/locks'
#         params  ={ 'blocking' : endringsettID }
        
#         r = self.les( url, params=params )
#         return r 
        
#     def checklock_prettyprint( self, endringsettID, printheader=False):
#         """
#         Pen utskrift av låser som evt blokkerer endringssettet.
#         """
#         r = self.checklock( endringsettID)
#         locks = r.json()
#         if len(locks) > 0: 
#             if printheader:
#                 print( "lockId endringssettID username commonName origin time")
#             for lock in locks: 
#                 print( lock['lockId'], endringsettID, lock['username'], lock['commonName'], 
#                       lock['origin'], lock['time'] )
#         else: 
#             print( "No locks for", endringsettID)

class endringssett(): 
    """
    Klasse for hele prosessen med skriving til NVDB skriveAPI. 
    
    Spiller sammen med apiskrivforbindelse, som håndterer REST kallene. 
    Bruk funksjonen lag_forbindelse() for å knytte en instans av 
    apiskrivforbindelse til endringssett-objektet ditt.
    
    EKSEMPEL, fullstending løype
    e1 = endringssett(<dine skriveklare data>)
    
    ELLER
    e1 = endringssett()
    e1.data = <dine skriveklare data>
    
    e1.forbindelse.login(username='deg', pw='dittPw', miljo='utvskriv')
    # Gjør det enklere å søke / filtrere i kontrollpanelet
    e1.forbindelse.klientinfo('Tekststreng for å skille / gruppere dine endringssett')
    e1.registrer()
    e1.valider()
    e1.validertresultat
    e1.start_skriving()
    e1.sjekkfremdrift()

    """ 
    
    
    
    def __init__(self, data=None):

        self.data = data
        self.status = 'ikke registrert' 
        
        # Initialiser attributter med False 
        self.forbindelse = False
        self.minlenke = False
        self.validertresultat = False
        self.lag_forbindelse()
    
    def lag_forbindelse( self, apiskriv=None): 
        """
        Oppretter en forbindelse til apiskriv. 
        
        Du kan (gjen)bruke en 
        eksisterende forbindelse eller opprette en ny
        
        Forbindelsen er en instans av apiskrivforbindelse-objektet, som 
        håndterer en brukersesjon mot skriveAPI. 
        
        arguments: 
            apiskrivforbindelse [valgfri] En instans av apiskrivforbindelse
         
        """
        if not apiskriv: 
            apiskriv = apiforbindelse.apiforbindelse()
        
        self.forbindelse = apiskriv
    
    def valider(self): 
        """Validerer et endringssett. Forutsetter innlogget tilkobling
        """
        
        if not self.forbindelse: 
            print( "Ingen aktiv forbindelse med NVDB api skriv")
            return 
            
        self.validertrespons = self.forbindelse.skrivtil( '/nvdb/apiskriv/rest/v3/endringssett/validator', self.data )
        if self.validertrespons.ok: 
            self.validertresultat = self.validertrespons.json()
            
    def finnvalideringsfeil(self): 
        if not self.validertresultat: 
            self.valider()
        else: 
            for ff in self.validertresultat['resultat']['vegObjekter']: 
                if ff['feil']: 
                    print( ff['feil'], ff['nvdbId'])
    
                    
    def finnskrivefeil(self, returnNvdbId=False): 
        b = self.sjekkstatus(returjson=True)
        nvdbid_feiler = []
        endringer = {}
        # datakeys = set( self.data.keys())
        # if 'delvisOppdater' in self.data.keys():
        harnvdbid =  { 'oppdater', 'delvisOppdater', 
                                   'korriger', 'delvisKorriger', 'slett', 'lukk' }
        bb = harnvdbid.intersection( set( self.data.keys()))
        if bb: 
            bb_str = bb.pop() # Henter tekst fra set - mengden. Skal kun være 1 - en 
            endringer = dict(( p['nvdbId'], p) for p in self.data[bb_str]['vegObjekter'])
        elif  'registrer' in self.data.keys(): 
            endringer = dict(( p['tempId'], p) for p in self.data['registrer']['vegObjekter'])
        else: 
            print( 'Funky... dette skulle IKKE skje, her er mine dict-oppslagsnøkler', 
                  self.data.keys())            


        print( "fremdrift:", b['fremdrift'])
        for ff in b['resultat']['vegObjekter']: 
            if ff['feil']: 
                nvdbid_feiler.append( ff['nvdbid'])
                print(' --- FEIL -- ' )
                print(ff['nvdbId'], ff['feil'] )
                print( 'endringssett:' )
                if endringer and str(ff['nvdbId']) in endringer.keys(): 
                    print( json.dumps(endringer[str(ff['nvdbId'])], indent=4) )
                else: 
                    print( "Fant ingen endringssett med NVDB id", ff['nvdbId'], '????')
                 
        if returnNvdbId: 
            return nvdbid_feiler
        
    def registrer(self, dryrun=False): 
        """Registrerer et endringssett. Forutsetter innlogget tilkobling
        """
        
        if not self.forbindelse: 
            print( "Ingen aktiv forbindelse med NVDB api skriv" )
            return
        
        if dryrun: 
            self.forbindelse.headers['X-NVDB-DryRun'] = 'true'
        else: 
            self.forbindelse.headers['X-NVDB-DryRun'] = 'false'

        self.registrertrespons = self.forbindelse.skrivtil('/nvdb/apiskriv/rest/v3/endringssett', self.data )
        if self.registrertrespons.ok: 
            self.status = 'registrert' 
            
            # Plukker ut lenker for å gå videre med prosessen. 
            data = json.loads( self.registrertrespons.text ) 
            for rel in data: 
                if rel['rel'] == 'self': 
                    self.minlenke = rel['src']

        else: 
            print( 'Endringssett IKKE registrert')
            print( self.registrertrespons.text )
            self.status = 'Nektet registrering'
            
    def startskriving(self ): 
        """Forutsetter at endringsettet er registrert og at vi har en aktiv 
        (innlogget) forbindelse til NVDB api skriv"""
        
        if self.status != 'registrert': 
            print( "Kan ikke starte skriveprosess før endringssett er registrert!" )
            return 
        
        if not self.forbindelse: 
            print( "Ingen aktiv forbindelse med NVDB api skriv")
            return 
            
        self.startrespons = self.forbindelse.skrivtil( self.minlenke + '/start', self.data)
        if self.startrespons.ok: 
            self.status = 'startet'
        
        
    def sjekkstatus(self, returjson=False ): 
        """Sjekker status på endringssettet"""
        if self.status == 'ikke registrert' and not self.minlenke:
            print( "Endringssettet er IKKE registrert hos NVDB api")
        else: 
            
            if self.status == 'startet': 
                print( "Skriveprosess startet i NVDB api, bruk funksjon sjekkfremdrift")
            elif self.status == 'registrert' or self.minlenke: 
                print( "Endringssett er registrert hos NVDB api")

            temp = None 
            if self.minlenke:     
                self.statusrespons = self.forbindelse.les( self.minlenke + '/status')
                
                temp = self.statusrespons.json()
                self.status = temp['fremdrift']
            
            if returjson and temp: 
                return( temp )
            elif temp and 'fremdrift' in temp.keys(): 
                print( temp['fremdrift'])
            else: 
                print( "ALVORLIG FEIL??? Sjekk returverdi .statusrespons på skriveobjektet")
            
    def sjekkfremdrift(self ): 
        """
        Sjekker fremdrift på skriveprosess NVDB api
        returnerer teksten vi får fra NVDB api /fremdrift, 
        til bruk i dine funksjoner, f.eks for å itere over
        mange endringssett (lurt å dele opp i mindre biter, pga låsekonflikt etc)
        Sjekk for verdien BEHANDLES i din applikasjon - det betyr at 
        skriveprosess ikke er ferdig behandlet. 
        """
        if self.status == 'ikke registrert' and not self.minlenke:
            returdata = "Endringssettet er IKKE registrert hos NVDB api"
            print( returdata )
        elif self.status == 'registrert':
            returdata = "Endringssettet registrert hos NVDB api, men" + \
                    " skriveprosess er ikke startet\n" +\
                    "Bruk funksjon startskriving for å starte skriveprosess" 
            print(returdata)
        else: 
            
            self.fremdriftrespons = self.forbindelse.les( self.minlenke + '/fremdrift')
            returdata = self.fremdriftrespons.text

            returdata = returdata.replace('"', '') # Fjerner dobbeltfnutter
            
            self.status = returdata
        
        return returdata
    


def endringssett_mal( datakatalogversjon=None, operasjon='delvisOppdater'): 
    """
    Tomt endringssett som så kan fylles med vegobjekter

    ARGUMENTS: NONE

    KEYWORDS:
        datakatalogversjon: None eller tekststreng med datakatalog-versjon, eksempel '2.19' 

        operasjon - hva slags skriveoperasjon vi ønsker. Mulige verdier: 
            'delvisOppdater' (DEFAULT), 'registrer', 'oppdater',  'korriger', 'delvisKorriger', 'lukk' 

    RETURNS 
        dictionary med skjelett for endringssett (tom liste med vegobjekter)
    """
    if not datakatalogversjon: 
        r = requests.get( 'https://www.vegvesen.no/nvdb/api/v3/status.json')
        status = r.json()
        datakatalogversjon = status['datagrunnlag']['datakatalog']['versjon'] 

    operasjoner = [ 'delvisOppdater', 'registrer', 'oppdater', 'korriger', 'delvisKorriger', 'lukk' ]
    if not operasjon in operasjoner: 
        raise ValueError( 'operasjon må være en av: ' + ', '.join( operasjoner ))

    try: 
        float( datakatalogversjon )
    except ValueError: 
        raise ValueError( "datakatalogversjon må våre tekst med flyttall, for eksempel '2.19' " )

    mal = {     
                "datakatalogversjon": datakatalogversjon
            }
    mal[operasjon] =  {  "vegobjekter": [ ] }

    return mal 


def fagdata2skrivemal( liste_eller_forekomst, operasjon='delvisOppdater', 
            ignorerAlleEgenskaper=False, kunDisseEgenskapene=None, ignorerStedfesting=False, effektDato=None,
            datakatalogversjon=None, slettegenskaper=False, kaskadelukking="JA" ): 
    """
    Konstruerer mal for skriving til NVDB skriveAPI ut fra (liste med) NVDB fagdata fra NVDB api LES V3

    Med nøkkeord styrer man hvilke egenskap(er) som evt skal inkluderes, eller om vi skal inkludere objektenes stedfesting. 

    TODO
        - Håndtering av relasjoner (liste med relasjoner)

    ARGUMENTS:
        liste_eller_forekomst: (liste med, eller enkelt-forekomst av) dictionary (json) med NVDB fagdata fra NVDB api LES V3

    KEYWORDS: 
        operasjon - hva slags skriveoperasjon vi ønsker. Mulige verdier: 
            'delvisOppdater' (DEFAULT), 'registrer', 'oppdater',  'korriger', 'delvisKorriger', 'lukk' 


        ignorerAlleEgenskaper=False

        kunDisseEgenskapene=None | [ liste med egenskap ID] 

        ignorerStedfesting=False (default) eller True. 

        effektDato=None (default) eller ISO-tekststreng på formen '2020-03-23'. Bruker dagens dato hvis du ikke angir annet. 

        datakatalogversjon: None eller tekststreng med datakatalog-versjon, eksempel '2.19' 

        slettegenskaper=False (default) eller True I kombinasjonen delvisOppdater/delvisKorriger kan du velge om egenskapene skal slettes. 
                                                Gjerne i kombinasjon med nøkkelordet kunDisseEgenskapene=[ liste med egenskap ID]

        kaskadelukking: "JA" (default) eller "NEI". Ved lukking av objekter kan man velge å også lukke datterobjekter (assosierte objekt)

    RETURNS
        dictionary: Endringssett du kan sende til NVDB skriveapi (evt etter å ha justert på det)
    """

    if isinstance( liste_eller_forekomst, list): 
        liste = liste_eller_forekomst
    else: 
        liste = [  liste_eller_forekomst ]


    if not effektDato: 
        effektDato = datetime.today().strftime('%Y-%m-%d')

    endringssett = endringssett_mal( operasjon=operasjon, datakatalogversjon=datakatalogversjon)

    
    for count, ettobj in enumerate( liste): 
        
        relasjoner = [ ]
        stedfestinger = None
        egenskaper = [ ]
        skrivobj = { 'typeId' : ettobj['metadata']['type']['id']    }

        for eg in ettobj['egenskaper']: 
            if 'lokasjonsattributt' in eg['navn'] or 'PunktTilknytning' in eg['navn']: 
                stedfestinger = eg
            elif 'Assosierte' in eg['navn']: 
                relasjoner.append( eg )
            else:   

                if (not ignorerAlleEgenskaper) and  ((kunDisseEgenskapene and eg['id'] in kunDisseEgenskapene) or not kunDisseEgenskapene): 
                    if slettegenskaper: 
                        egenskaper.append( egenskap2skriv(eg , operasjon='slett' ))
                    else: 
                        egenskaper.append( egenskap2skriv(eg, operasjon=operasjon))

        if len( egenskaper ) > 0: 
            skrivobj['egenskaper'] = egenskaper


        if operasjon == 'registrer':
            skrivobj['gyldighetsperiode'] =  { "startdato": effektDato }
            skrivobj['tempId'] = str( -1 * (count+1) )

        else: 
            skrivobj['nvdbId']  = ettobj['id']
            skrivobj['versjon'] = ettobj['metadata']['versjon']

        if 'ppdater' in operasjon or 'orriger' in operasjon: 
            skrivobj['gyldighetsperiode'] =  { "startdato": effektDato }

        elif operasjon == 'lukk':
            skrivobj['lukkedato'] = effektDato 
            skrivobj['kaskadelukking'] : kaskadelukking
            

        endringssett[operasjon]['vegobjekter'].append( skrivobj )

    return endringssett

def lokasjon2skriv( lokasjonsegenskap, operasjon='delvisOppdater', ignorerSideposisjon=False, ignorerFelt=False ):
    """
    Lager lokasjonselement til apiskriv basert på data fra apiles (egenskapen "Liste av lokasjonsattributt")
    """ 
    if 'punkt' in lokasjonsegenskap['navn'].lower(): 
        loktype = 'punkt'

        mal = { 'punkt': [ { 'veglenkesekvensNvdbId' :  lokasjonsegenskap['veglenkesekvensid'], 
                              'posisjon' :              lokasjonsegenskap['relativPosisjon'],
                              'retning' :               lokasjonsegenskap['retning']
                            }   
                        ]}
        if len( lokasjonsegenskap['kjørefelt']) > 0 and not ignorerFelt: 
            mal['punkt'][0]['kjørefelt'] = lokasjonsegenskap['kjørefelt']

        if 'sideposisjon' in lokasjonsegenskap and not ignorerSideposisjon: 
            mal['punkt'][0]['sideposisjon'] = lokasjonsegenskap['sideposisjon']

        if 'delvis' in operasjon: 
            mal['punkt'][0]['operasjon'] = 'ny'


    elif lokasjonsegenskap['navn'] == 'Liste av lokasjonsattributt': 
        loktype = 'linje'
        mal = { 'linje' : [ ] }

        for ll in lokasjonsegenskap['innhold']:
            l2 = { 'veglenkesekvensNvdbId' : ll['veglenkesekvensid'], 
                              'fra' :       ll['startposisjon'],
                              'til' :       ll['sluttposisjon'],
                              'retning' :   ll['retning']
                            } 

        if len( ll['kjørefelt']) > 0 and not ignorerFelt: 
            l2['kjørefelt'] = lokasjonsegenskap['kjørefelt']

        if 'sideposisjon' in lokasjonsegenskap and not ignorerSideposisjon: 
            l2['sideposisjon'] = lokasjonsegenskap['sideposisjon']

        if 'delvis' in operasjon: 
            l2['operasjon'] = 'ny'

        mal['linje'].append( l2 )

    else: 
        raise ValueError( 'Fant ikke ut av dette lokasjonsobjektet??? Skal være punkt eller linje?')

    
    return mal 

def egenskap2skriv(egenskap, operasjon='delvisOppdater' ): 
    """
    Omsetter en egenskapverdi fra NVDB api LES v3 til den datastrukturen apiskriv forventer 

    Takler IKKE lokasjon- og relasjonsegenskaper, dem har du filtrert vekk på forhånd 

    ARGUMENTS 
        egenskap: dictionary med egenskapverdi, hentet direkte fra NVDB apiles V3 

    KEYWORDS
       operasjon - hva slags skriveoperasjon vi ønsker. Mulige verdier: 
            'delvisOppdater' (DEFAULT), 'registrer', 'oppdater',  'korriger', 'delvisKorriger', 'lukk', 'slett' 
            NB! Slett er kun gyldig operasjon for sletting av egenskapverdier. Sletting av objekter er enten lukking  (sluttdato) eller fjerning (hard sletting)
    
    RETURNS 
        dictionary med egenskapverdi som kan inngå i endringssett til NVDB apiskriv
    """ 


    mal = { "typeId": egenskap['id'] } 
    
    if 'slett' in operasjon or 'lukk' in operasjon: 
        mal['operasjon'] = 'slett'
    else: 
        mal['verdi'] = [ str( egenskap['verdi']  )  ]

    if 'delvis' in operasjon: 
        mal['operasjon'] = 'oppdater'

    return mal 



def splittMultippelStedfesting( ettNvdbObjekt  ): 
    """
    Splitter ett NVDB objekt med multipppel stedfesting i flere

    Dvs objekt A med stedfesting ->1,2,3 => Objekt A får oppdatert sin stedfesting til =1, 
        og vi oppretter nye objekt objekt B med stedfesting 2, C med stedfesting 3 
    """