# -*- coding: utf-8 -*-
"""
Kommunikasjon mot, og skriving til NVDB skriveapi https://apiskriv.vegdata.no/ 

Det anbefales STERKT at utvikling foregår mot docker-instans av skriveapi. 
https://www.vegdata.no/2016/03/09/utviklerutgave-av-skrive-apiet-tilgjengelig-pa-docker-hub/


apiskrivforbindelse - Klasse som håndterer alt det praktiske med 
innlogging mot skriveapi. Kan brukes til å lese data fra 
skriveapi-endrepunkt (skriveoperasjoner, endringssett, låser m.m.)

Merk funksjonen klientinfo('Passe unik tekststreng'). Denne setter headeren 
X-Client lik tekststrengen. Bruk det til å søke / filtrere / gruppere i 
skriveapi'ets kontrollpanel. Endringssett som hører sammen kan ha samme 
klientinfo, evt med små perturbasjoner. 

endringssett - Klasse som håndterer alle steg i skriveprosessen: 
 - registrering
 - validering
 - startskriving
 - sjekkfremdrift 
 
Selve endringssettet - de data som skal skrives / endres / slettes / korrigeres / oppdateres - 
er en python-dict i endringssett.data  - attributten. Du kan legge data dit 
automatisk ved å sende dem inn som argument når du oppretter endringssett-objektet

Eksempel
    e1 = endringssett( <dine skriveklare data>)
alternativt
    e1.endringssett()
    e1.data = <dine skriveklare data>

Eksempler på endringssett finner du i /generator/ - endepunktet i docker-instans, 
evt https://www.vegvesen.no/nvdb/apiskriv/generator/

Endringssettet må ha en api-forbindelse. Dette er en instans av 
apiskrivforbindelse-objektet i attributten endringsset.forbindelse. 
Via funksjonen endringssett.lag_forbindelse( apiskrivforbindelse ) 
kan du (gjen)bruke en eksisterende forbindelse, eller opprette en ny. 

Eksempel: 
	endringssett.lag_forbindelse(  apiskskrivapiskrivforbindelse )

Alternativt
    endringssett()
    endringsett.lag_forbindelse() # Lager ny forbindelse til apiskriv
    endringssett.forbindelse.login( username=<du>, pw=<dittpassord>)

EKSEMPEL, fullstending løype
    e1 = endringssett(<dine skriveklare data>)
    
    ELLER
    e1 = endringssett()
    e1.data = <dine skriveklare data>
    
    e1.lag_forbindelse()
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
import getpass
import copy
import apiforbindelse

# class apiskrivforbindelse():
#     """
#     Håndterer innlogging og kommunikasjon mot skriveAPI.
#     """
    
#     def __init__( self, miljo='nvdbdocker', content='json'):
#         """
#         Oppretter en instans av apiskrivforbindelse
        
#         Arguments: 
#             None 
#         Keywords: 
#             miljo: string, 'nvdbdocker' | 'utv' | 'test' | 'prod'
#                     (Kan droppes, men settes da ved innlogging)
#             content: string 'json' (default) | 'xml'
                
#         """ 
        
#         self.headers = {  "Content-Type" : "application/json", 
#                             "Accept" : "application/json", 
#                             "X-Client" : "PythonNvdbskriv" 
#                               }
                              
#         if content== 'xml': 
#             self.headers["Content-Type"] = 'application/xml'
                              
#         self.proxies = {} 
#         self.tokenId = ''
                              
#     def login(self, miljo='nvdbdocker', proxies=False, username='jajens', 
#               pw=None, klient=None): 
#         """
#         Logger inn i skriveAPI.
        
#         Arguments: 
#             None
            
#         Keywords: 
#             miljo : string, en av 'nvdbdocker' (default), 'utv', 'test', 'prod'
            
#             proxies : Boolean True | False (default) 
#                 angir om vi skal prøve SVV-interrne proxy
        
#         """
        
#         if miljo == 'nvdbdocker': 
            
#             if proxies: 
#                 self.proxies = {'http': 'proxy.vegvesen.no:8080', 
#                                 'https': 'proxy.vegvesen.no:8080'} 

            
#             self.apiurl = 'http://164.132.107.230:8080'
#             bruker = 'root00'
            
#             self.requestsession = requests.session()
#             self.loginrespons = self.requestsession.post( url=self.apiurl + '/login', 
#                                          proxies=self.proxies, 
#                                          headers=self.headers, 
#                                          data = { 'user-id' : bruker })
            
#         else: 
#             if miljo == 'utv': 
#                 self.apiurl = 'https://www.utv.vegvesen.no' 
#                 openAMurl = 'https://www.utv.vegvesen.no/openam/json/authenticate' 
#                 openAmNavn = 'iPlanetDirectoryProOAMutv'
            
#             elif miljo == 'test': 
#                 self.apiurl = 'https://www.test.vegvesen.no' 
#                 openAMurl = 'https://www.test.vegvesen.no/openam/json/authenticate' 
#                 openAmNavn = 'iPlanetDirectoryProOAMTP'
                
                
#             elif miljo == 'prod': 
#                 self.apiurl = 'https://www.vegvesen.no' 
#                 openAMurl = 'https://www.vegvesen.no/openam/json/authenticate'
#                 openAmNavn = 'iPlanetDirectoryProOAM'
                
#             else:
#                 print( 'Miljø finnes ikke! utv, test eller prod - eller nvdbdocker')

#             headers = self.SVVpassord( username=username, pw=pw )
            
#             self.requestsession = requests.session()
#             self.loginrespons = self.requestsession.post( url=openAMurl, 
#                                          headers=headers, 
#                                          params = { 'realm' : 'External', 
#                                                  'authIndexType' : 'module', 
#                                                  'authIndexValue' : 'LDAP'})
            
#             if self.loginrespons.ok:
#                 temp = self.loginrespons.json()
#                 if 'tokenId' in temp.keys():
                    
#                     self.headers['Cookie'] = openAmNavn + '= ' + temp['tokenId']
                    
#                 else: 
#                     print( 'Fikk ikke logget på - ingen tokenId :(' )
                    
#             else: 
#                 print( "Fikk ikke logget på :( " )
        
#         # Setter sporbar http header X-Client 
#         if klient: 
#             self.klientinfo(klient)
        
#     def loggut(self): 
#         """
#         Logger ut av skriveAPI.
        
#         Arguments: 
#             None 
#         """ 
        
#         if 'vegvesen' in self.apiurl: 
#             self.debug = self.requestsession.get( self.apiurl + '/openam/UI/Logout') 
#         else: 
#             self.debug = self.requestsession.get( self.apiurl + '/logout')
        
#     def SVVpassord( self, username=None, pw=None): 
        
#         if not username: 
#             username = input( 'Username: ' )
#         if not pw: 
#             pw = getpass.getpass( username+"'s Password: ")
#         headers = copy.deepcopy( self.headers )
#         headers['X-OpenAM-Username'] = username
#         headers['X-OpenAM-Password'] = pw
        
#         return headers
    
#     def klientinfo( self, klientinfo):
#         """
#         Få bedre sporbarhet / enklere søk i skriveapi-GUI! 
        
#         Via http headeren X-Client kan du angi noe som er unikt for det problemet
#         du jobber med akkurat nå, f.eks. fikse bomstasjon-takster. 
        
        
#         Endringssett-objektets egenskap headers['X-Client'] settes lik klientinfo
        
#         Arguments: 
#             klientinfo TEKST - det du vil hete! 
            
#         Keywords: NONE
        
#         Returns: NONE
            
#         """
#         self.headers['X-Client'] = str( klientinfo )
    
#     def skrivtil( self, path, data, **kwargs): 
#         """
#         Poster data til NVDB api skriv.
        
#         Arguments:
#             path : URL, enten relativt til /apiskriv, eller fullstendig adresse
            
#             data : Datastrukturen som skal postes. Enten json (default) 
#                     eller xml (angis i så fall med content-argumentet ved 
#                     opprettelse av endringssett-objektet, eller ved å sette 
#                     manuelt 
#                     endringsett.headers["Content-Type"] = 'application/xml')
                    
#         Keywords: 
#             Eventuelle nøkkelord-argumenter sendes til python request-modulen

#         """
        
#         if path[0:4] == 'http': 
#             url = path
#         else: 
#             url = self.apiurl + path
        
#         if self.headers['Content-Type'] == 'applcation/xml': 
#             return self.requestsession.post( url=url, 
#                                      proxies=self.proxies, 
#                                      headers=self.headers, 
#                                      data = data, **kwargs)
#         elif self.headers['Content-Type'] == 'application/json': 
#             return self.requestsession.post( url=url, 
#                                     proxies=self.proxies, 
#                                     headers=self.headers, 
#                                     json = data, **kwargs)
#         else: 
#             print( "Sjekk CONTENT-TYPE på api-forbindelse objektet")
#             return None
        
#     def les( self, path, **kwargs): 
#         """
#         Http GET requests til NVDB REST skriveapi
        
#         Arguments:
#             path : URL, enten relativt til /apiskriv, eller fullstendig 
            
#         Keywords: 
#             Eventuelle nøkkelord-argumenter sendes til python request-modulen
#         """
        
#         if path[0:4] == 'http': 
#             url = path
#         else: 
#             url = self.apiurl + path
        
        
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
    
    e1.lag_forbindelse()
    e1.forbindelse.login(username='deg', pw='dittPw', miljo='docker')
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
        self.startlenke = False
        self.kansellerlenke = False
        self.statuslenke = False
        self.fremdriftlenke = False 
        self.validertresultat = False
    
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
                                   'korriger', 'delvisKorriger', 'slett' }
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
    


