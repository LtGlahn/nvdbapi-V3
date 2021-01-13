# -*- coding: utf-8 -*-
"""
Kommunikasjon mot NVDB api v3 LES og SKRIV

apiforbindelse - Klasse som håndterer alt det praktiske med 
innlogging mot NVDB api skriv eller les. 


""" 
import uuid
import getpass
import requests
import json
import copy 
import pdb
from time import sleep
from  requests.exceptions import SSLError

class apiforbindelse( ):
    """
    Håndterer innlogging og kommunikasjon mot NVDB api LES og SKRIV .
    """
    
    def __init__( self, miljo='prodles' ):
        """
        Oppretter en instans av apiskrivforbindelse
        
        Arguments: 
            None 
        Keywords: 
            miljo: string, en av 
                    utvles
                    testles
                    prodles 
                    utvskriv
                    testskriv
                    prodskriv

                    (Kan droppes hvis den settes ved innlogging)
                
        """ 
        
        self.headers = {    
                            "X-Client" : "LtGlahn python", "User-Agent" : "LtGlahn python requests"
                              }
        self.tokenId = ''
        self.requestsession = requests.session()
        self.headers['X-Client-Session'] = str( uuid.uuid4() )
        if miljo:
            self.velgmiljo( miljo=miljo)
        self.proxies = None
        # self.proxies =  {  "http": "http://proxy.vegvesen.no:8080", "https": "http://proxy.vegvesen.no:8080" }

    def velgmiljo( self, miljo='utvles'):
        """
        Velger miljø. Default = utvles, eller bruk nøkkelord miljo=<navn på miljø>. 

        Lovlige verdier: NVDB api les v3: utvles, testles, prodles
                         NVDB api SKRIV v3: utvskriv, testskriv, prodskriv
        """ 
        self.miljo = miljo

        self.headers['Accept'] = 'application/vnd.vegvesen.nvdb-v3-rev1+json'
              
        if miljo == 'utvles': 
            self.apiurl = 'https://nvdbapiles-v3.utv.atlas.vegvesen.no' 

#            self.proxies =  {  "http": "proxy.vegvesen.no:8080", "https": "proxy.vegvesen.no:8080" }

        elif miljo == 'stm-utvles': 
            self.apiurl = 'https://nvdbapiles-v3-stm.utv.atlas.vegvesen.no' 


        elif miljo == 'testles': 
            self.apiurl = 'https://nvdbapiles-v3.test.atlas.vegvesen.no' 
        
        elif miljo == 'prodles': 
            self.apiurl = 'https://nvdbapiles-v3.atlas.vegvesen.no' 

        elif miljo == 'utvskriv':
            self.apiurl = 'https://www.utv.vegvesen.no' 
            self.skrivloginurl = 'https://www.utv.vegvesen.no/ws/no/vegvesen/ikt/sikkerhet/aaa/autentiser' 
            self.headers['Accept'] = 'application/json'
            self.headers['Content-Type'] = 'application/json'

        elif miljo == 'testskriv': 
            self.apiurl = 'https://www.test.vegvesen.no' 
            self.skrivloginurl = 'https://www.test.vegvesen.no/ws/no/vegvesen/ikt/sikkerhet/aaa/autentiser' 
            self.headers['Accept'] = 'application/json'
            self.headers['Content-Type'] = 'application/json'            
            
        elif miljo == 'prodskriv': 
            self.apiurl = 'https://www.vegvesen.no' 
            self.skrivloginurl = 'https://www.vegvesen.no/ws/no/vegvesen/ikt/sikkerhet/aaa/autentiser'
            self.headers['Accept'] = 'application/json'
            self.headers['Content-Type'] = 'application/json'
            
        else:
            print( 'Miljø finnes ikke! utvles, utvskriv, testles, testskriv, prodles, prodskriv')

                              
    def login(self, miljo=None, username='jajens', pw=None, klient=None, user_type='employee'): 
        """
        Logger inn i api.
        
        Arguments: 
            None
            
        Keywords: 
            miljo : None eller string, en av 
                    utvles,   testles,   prodles
                    utvskriv, testskriv, prodskriv

            username : None eller string, ditt brukernavn. Du blir spurt om du ikke oppgir dette

            pw :  None eller string, du blir spurt om du ikke oppgir dette 

            klient : None eller string, Øk sporbarhet ved å gjør det lettere å finne endringssettene dine i 
                                        APISKRIV sitt endringssett-panel 

            user_type : string, 'employe' eller XXX (hva vi nå kaller fjesløse brukere i dag)
                                TODO: Oppdater dokumentasjon med riktig fjesløs-begrep XXX 
        
        """
        
        if miljo: 
            self.velgmiljo( miljo=miljo)

        if 'skriv' in self.miljo: 
            self.__loginskriv( username='jajens', pw=pw )
        elif 'les' in self.miljo: 
           self.__loginles( username='jajens', pw=pw) 
        else: 
            print( 'Miljø ikke korrekt angitt', self.miljo )
    
        # Setter sporbarhet 
        if klient: 
            self.klientinfo(klient)

        self.headers['X-Client-Session'] = str( uuid.uuid4() )

    def __loginles( self, username='jajens', pw=None, user_type='employee' ): 
        """
        Logger inn på apiles, ref
        https://nvdbapilesv3.docs.apiary.io/#reference/0/autentisering/innlogging
        """ 

        temp = self.SVVpassord( username=username, pw=pw )
        body = { 'username' :  temp['X-OpenAM-Username'], 
                 'password' :  temp['X-OpenAM-Password']
                }

        if user_type: 
            body['user_type'] = user_type 

        headers = { 'Content-Type' : 'application/json'}


        self.requestsession = requests.session()
        loginurl = url=self.apiurl + '/auth/login'
        self.loginrespons = self.requestsession.post( loginurl, 
                                                            headers=headers, json=body  )

        if self.loginrespons.ok: 
            temp = self.loginrespons.json( )
            if 'idToken' in temp.keys(): 
                self.headers['Authorization'] = 'Bearer ' + temp['idToken']
            else: 
                print( 'Login', self.apiurl, 'FEILER, ingen idToken i respons')

            if 'refreshToken' in temp.keys():
                self.refreshToken = temp['refreshToken']
            else: 
                print( 'Ingen refreshToken i login-respons fra', self.apiurl)

        else: 
            print( 'Login', loginurl, 'feiler med kode', self.loginrespons.status_code)
            print( self.loginrespons.text )


    def __loginskriv( self, username='jajens', pw=None, klient=None): 
        """
        Logger inn mot apiskriv 

        """
        temp = self.SVVpassord( username=username, pw=pw )
        body = { 'username' :  temp['X-OpenAM-Username'], 
                 'password' :  temp['X-OpenAM-Password']
                }        
        headers = { "Content-Type" : "application/json"}
        
        self.loginrespons = self.requestsession.post( url=self.skrivloginurl, 
                                        headers=headers, 
                                        json=body )
        
        if self.loginrespons.ok:
            temp = self.loginrespons.json()
            if 'token' in temp.keys():
                
                self.headers['Cookie'] = temp['tokenname'] + '= ' + temp['token']
                
            else: 
                print( 'Fikk ikke logget på - ingen token :(' )
                
        else: 
            print( "Fikk ikke logget på :(, loginrespons ", self.loginrespons.status_code )

               
    # def loggut(self): 
    #     """
    #     Logger ut av skriveAPI.
        
    #     Arguments: 
    #         None 
    #     """ 
        
    #     if 'vegvesen' in self.apiurl: 
    #         self.debug = self.requestsession.get( self.apiurl + '/openam/UI/Logout') 
    #     else: 
    #         self.debug = self.requestsession.get( self.apiurl + '/logout')
        
    def SVVpassord( self, username=None, pw=None): 
        
        if not username: 
            username = input( 'Username: ' )
        if not pw: 
            pw = getpass.getpass( username+"'s Password: ")
        headers = copy.deepcopy( self.headers )
        headers['X-OpenAM-Username'] = username
        headers['X-OpenAM-Password'] = pw
        
        return headers
    
    def klientinfo( self, klientinfo):
        """
        Få bedre sporbarhet / enklere søk i skriveapi-GUI! 
        
        Via http headeren X-Client kan du angi noe som er unikt for det problemet
        du jobber med akkurat nå, f.eks. fikse bomstasjon-takster. 
        
        
        Endringssett-objektets egenskap headers['X-Client'] settes lik klientinfo
        
        Arguments: 
            klientinfo TEKST - det du vil hete! 
            
        Keywords: NONE
        
        Returns: NONE
            
        """
        self.headers['X-Client'] = str( klientinfo )
    
    def skrivtil( self, path, data, **kwargs): 
        """
        Poster data til NVDB api skriv.
        
        Arguments:
            path : URL, enten relativt til /apiskriv, eller fullstendig adresse
            
            data : Datastrukturen som skal postes. Enten json (default) 
                    eller xml (angis i så fall med content-argumentet ved 
                    opprettelse av endringssett-objektet, eller ved å sette 
                    manuelt 
                    endringsett.headers["Content-Type"] = 'application/xml')
                    
        Keywords: 
            Eventuelle nøkkelord-argumenter sendes til python request-modulen
        """
        
        if path[0:4] == 'http': 
            url = path
        else: 
            url = self.apiurl + path
        

        return self.requestsession.post( url=url, 
                                            proxies=self.proxies, 
                                            headers=self.headers, 
                                            json = data, **kwargs)
        
    def les( self, path, headers={}, **kwargs): 
        """
        Http GET requests til NVDB REST skriveapi eller leseapi 
        
        Arguments:
            path : URL, enten relativt til rot-endepunt for API, eller fullstendig 
            
        Keywords: 
            Eventuelle nøkkelord-argumenter sendes til python request-modulen
        """
        
        if path[0:4] == 'http': 
            url = path
        else: 
            url = self.apiurl + path

        # Kopierer self.headers og angitte headers over i ny dictionary. 
        myheaders = { **self.headers, **headers}

        """Leser data fra NVDB api"""
        try:
            r = self.requestsession.get( url=url, 
                                       proxies=self.proxies,
                                       headers=myheaders, 
                                       **kwargs)
        except SSLError as e:
            venteperiode = 5
            print( 'Feilmelding ved henting av data, prøver på ny om', venteperiode, 'sekunder', e)
            sleep( 5 )
            r = self.requestsession.get( url=url, 
                                       proxies=self.proxies,
                                       headers=myheaders, 
                                       **kwargs)        
        
        return r 

    def finnid( self, objektid, kunvegnett=False, kunfagdata=False, miljo=False): 
        """Henter NVDB objekt (enten veglenke eller fagdata) ut fra objektID.
        Bruk nøkkelord kunvegnett=True eller kunfagdata=True for å avgrense til 
        vegnett og/eller fagdata (vi har betydelig overlapp på ID'er mellom vegnett 
        og fagdata)

        Fagdata returnerer en DICT
        Vegnett returnerer en LISTE med alle vegnettselementene for veglenka

        """

        # Henter fagdata    
        if kunfagdata or (not kunvegnett): 
            try:
                res = self.les( self.apiurl +  '/vegobjekt', params = { 'id' : objektid } )
                res = res.json()

            except ValueError: 
                pass

            else:
                # Må hente fagobjektet på ny for å få alle segmenter (inkluder=alle)
                res = self.les( res['href'], params = { 'inkluder' : 'alle' } ) 
                res = res.json()

        # Henter vegnett
        if kunvegnett or (not kunfagdata) or (not res and not kunfagdata): 
            try: 
                res = self.les( self.apiurl + '/vegnett/veglenkesekvenser/segmentert/' + str(objektid))
                res = res.json()            
            except ValueError: 
                pass

            # Sikrer at vi alltid returnerer liste med vegsegmenter - selv om vi kun har ett segment
            if isinstance( res, dict): 
                res = [ res ]

        if not res: 
            print( "Fant intet NVDB objekt eller vegnett med ID = " + str(objektid))
            
        return res