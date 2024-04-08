# -*- coding: utf-8 -*-
"""Bibliotek for å hente data fra NVDB api V3 (og senere versjoner)
Har 3 klasser: 
    - nvdbVegnett: Søkeobjekt for å søke og laste ned vegnett
    - nvdbFagdata: Søkeobjekt for å søke og laste ned vegobjekter 
    - nvdbFagObjekt: Har metoder for å hente ut egenskapverdi(er) og relasjoner for et NVDB objekt

Har disse hjelpefunksjonene:
    - finnid: Henter vegobjekt og/eller lenkesekvens med angitt ID
    - nvdbfagdata2records: Flater ut NVDB-vegobjekt (direkte fra NVDB api) til enklere (forutsigbar) dictionary-struktur
    - egenskaper2records: Oversetter liste med egenskapverdier til dictionary 
    - vegrefpunkt: Slår opp på et punkt på vegnettet

Sjekk README.md for detaljer, og https://github.com/LtGlahn/nvdbapi-V3/issues for kjente feil og mangler. 

"""

import json
import requests
from warnings import warn
import os
from copy import deepcopy
from time import sleep
# import pdb
from datetime import datetime
import dateutil.parser
import re
from json import JSONDecodeError

from . import apiforbindelse
import nvdbapiv3

# Uncomment to silent those unverified https-request warnings
requests.packages.urllib3.disable_warnings() 

class nvdbVegnett: 
    """Klasse for spørringer mot NVDB for å hente segmentert vegnett. 
    Jobber dynamisk mot NVDB api for å hente statistikk, laste ned data etc.
    Holder alle parametre som inngår i dialogen med NVDB api. 

    Grovt sett skal vi ha disse komponentene / funksjonene: 
        - Enkle metoder for å sette søkefilter
        (geografisk filter, egenskapsfilter som veglenketype etc)
        Et filter er en dictionary  
        
        - Smart utnyttelse av NVDB api'ets pagineringsfunksjon. 

    Vi er kun en tynn "wrapper" som henter segmentert vegnett fra NVDB api LES, og viser til dokumentasjon 
    for dette endepunktet for mer info om aktuelle søkefiltre etc. 
    https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_vegnett_veglenkesekvenser_segmentert 

    n = nvdbVegnett() 
    n.filter( {'kommune' : 5001 })            # Veger i Trondheim kommune
    n.filter( {'vegsystemreferanse' : 'Ev' }) # Europaveger - som addert med forrige filter blir til Europaveger i Trondheim
    for v in n: 
        print v['id']  # Gjør noe spennende


    Filter kan også settes når søkeobjektet oppretes med nøkkelordet "filter", eksempel
    n = nvdbVegnett( filter={'vegsystemreferanse' : 'Ev', 'kommune' : 5001 })
    """
    
    
    def __init__( self, miljo=None, debug=False, filter=None ):
        
        
        self.filterdata = {}
        self.geofilter = {} # DEPRECEATED
        self.headers =   { 'accept' : 'application/vnd.vegvesen.nvdb-v3-rev3+json', 
                            'X-Client' : 'nvdbapi.py',
                            'X-Kontaktperson' : 'jan.kristian.jensen@vegvesen.no'}
                            
        self.update_http_header()
                            
        
        self.paginering = { 'antall'                : 1000,     # Hvor mange obj vi henter samtidig.
                            'hvilken'               : 0,        # iterasjon i det lokale datasettet 
                                                                # Dvs i+1 til array self.data['objekter'] 
                                                                # 
                            'antallObjektReturnert' : 0,        # Løpenummer, antall objekter vi har 
                                                                # returnert totalt fra nesteForekomst / next  
                                                                # 
                            'meredata'              : True,     # Gjetning på om vi kan hente mere data
                            'initielt'              : True,     # Initiell ladning av datasett
                            'dummy'                 : False     # Jukse-bruk av paginering 
                    } 
    

        # Standardverdier for responsen, og holder evt tilleggsparametre
        # Initielt tom for vegnett, men langt fagdata
        self.respons  = { }
        
        self.data = { 'objekter' : []}
        self.forbindelse = apiforbindelse.apiforbindelse()
        if not miljo:
            miljo = 'prod'
        self.miljo( miljo)

        self.debug = debug

        if isinstance( filter, dict ): 
            self.filterdata = filter 


    def __iter__(self): 
        """
        Mer python-generisk iterasjonsstøtte. 

        Har brukt denne oppskriften: https://towardsdatascience.com/how-to-loop-through-your-own-objects-in-python-1609c81e11ff
        """
        return self 

    def __next__(self): 
        """
        Bruker nesteForekomst for en mer generell pythonisk iterasjon

        Har brukt denne oppskriften: https://towardsdatascience.com/how-to-loop-through-your-own-objects-in-python-1609c81e11ff 
        """
        data = self.nesteForekomst()
        if data:
            return data
        else:  
            raise StopIteration

        
    def nesteForekomst(self, debug=False): 
        """Returnerer en enkelt forekomst av vegnettet. 
        Brukes for å iterere over mottatte data uten å bekymre seg 
        om evt paginering.
        Eksempel: 
            v = nvdbVegNett()
            veg = v.nesteForekomst()
            while veg: 
                print veg.id # Gjør noe spennende med dette enkeltobjektet
                veg = v.nesteForekomst()
        """
        if isinstance( self, nvdbFagdata) and not self.objektTypeId: 
            raise ValueError( '\n'.join(('ObjektTypeID mangler.',  
                                    '\tEks: N = nvdbFagData(45)', 
                                    '\teller: N = nvdbFagData()',
                                    '       N.objektType(45)')))

        if isinstance( self, nvdbFagdata) and not self.antall:
            self.statistikk()

        antObjLokalt = len(self.data['objekter'])
        if self.debug or debug: 
            print( "debug nesteForekomst: Pagineringsdata", self.paginering) 

        if self.paginering['dummy']:
            # Noen har faket et søkeobjekt og dytta inn data der...
            if self.paginering['hvilken'] < len( self.data['objekter']): 
                self.paginering['hvilken'] += 1
                return self.data['objekter'][self.paginering['hvilken']-1]
            else: 
                return None
             
        elif self.paginering['initielt']: 
        
            if isinstance( self, nvdbFagdata): 
                parametre = merge_dicts(  self.filterdata, self.respons )
                self.data = self.anrope( '/'.join(('vegobjekter', str(self.objektTypeId) )), 
                    parametre=parametre ) 
                self.antall = self.data['metadata']['antall']

            elif isinstance( self, nvdbNoder ): 
                parametre = self.filterdata
                self.data = self.anrope( 'vegnett/noder', parametre=parametre )

            elif isinstance( self, nvdbVegnett): 
                parametre = self.filterdata
                self.data = self.anrope( 'vegnett/veglenkesekvenser/segmentert', parametre=parametre )
                self.antall = self.data['metadata']['antall']

            self.paginering['initielt'] = False

            if self.data['metadata']['returnert'] > 0: 
                self.paginering['hvilken'] = 1
                self.paginering['antallObjektReturnert'] += 1 
                return self.data['objekter'][0]
            else: 
                self.paginering['meredata'] = False
                return None
                
        elif self.paginering['meredata'] and self.paginering['hvilken'] > antObjLokalt-1: 
            self.data = self.anrope( self.data['metadata']['neste']['href'] ) 
            self.paginering['hvilken'] = 1
            
            if self.data['metadata']['returnert'] > 0: 
                self.paginering['antallObjektReturnert'] += 1 
                return self.data['objekter'][0]
            else: 
                self.paginering['meredata'] = False
                return None
        
        elif self.paginering['meredata']: 
        
            self.paginering['hvilken'] += 1
            self.paginering['antallObjektReturnert'] += 1 
            return self.data['objekter'][self.paginering['hvilken']-1]
        
    def addfilter_geo(self, *args):
        """
        DEPRECEATED: replaced with addfilter - function
        
        addfilter_geo, addfilter_egenskap and addfilter_overlapp are now obsolete and 
        replaced with the generic addfilter function 

        For now, any arguments to addfilter_geo is simply 
        passed on to the addfilter - function
        """
        warn( "addfilter_geo is depreceated, please use the generic addfilter function", DeprecationWarning)


        if len( args) > 0: 
            data = self.filter( self, *args )

    def filter(self, *arg, **kwargs):
        """Get or set filters to your search. 
        Input argument is a dict with one or more filter(s). 
        Previous added filters are unchanged unless the dictionary keys
        are identical, in which case the old values are overwritten 
        are modified (if the keys match) or kept unchanged. 


        See 
        http://api.vegdata.no  or this repository README-file 
        https://github.com/LtGlahn/nvdbapi-V3/blob/master/README.md 
        for a list of possible filters and their values. 
                
        addfilter with no arguments returns the current filter. 
        
        Input empty dict {} or string to clear all filters
        """ 
        
        if len( arg) == 1: 
            if isinstance( arg[0], dict) and arg[0]: 
                self.filterdata.update( arg[0]) 
            elif isinstance( arg[0], dict) and not arg[0]: 
                self.filterdata = {} 
            elif isinstance( arg[0], str): 
                self.filterdata = {} 

            else:
                warn('Wrong input to addfilter. Should be dict') 
        else:
            return self.filterdata

    def add_request_arguments( self, parameters): 
        """Appends (or updates) key-value parameters to the data retrieval request (but not "statistikk"-queries)
        Input argument is a dict. 

        Typically usage: Keywords that modifies the response, but isn't part of the search query
        
        Example
        p = nvdbFagdata(45)
        p.add_request_arguments( { 'srid' : 4326 })
        # Coordinates are now in lat/lon, not epsg:25833 / 32633
        """
        if parameters and isinstance( parameters, dict): 
            for k in parameters.keys(): 
                self.respons[k] = parameters[k]
                
        else: 
            warn("Input argument to add_request_arguments should be dict")
    

    def anrope(self, path, parametre=None, debug=False, silent=False, logganrop=False, iterasjontelling = 0): 
    
        logganrop = False # Logger alle anrop til fil
        maks_iterasjoner = 5
    
        # if not self.apiurl in path: 
        if not 'http' in path: 
            if path[0] == '/':
                url = ''.join(( self.forbindelse.apiurl, path))
            else: 
                url = '/'.join(( self.forbindelse.apiurl, path))
        else: 
            url = path 

        # r = requests.get(url, params=parametre, headers=self.headers)
        r = self.forbindelse.les( url, params=parametre, headers=self.headers )
        
        self.sisteanrop = r.url
        
        if debug:
            print( r.url[33:]) # DEBUG
        
        if r.status_code == requests.codes.ok:
            data = None 
            try: 
                data = r.json()
            except JSONDecodeError as err: 
                if iterasjontelling < maks_iterasjoner: 
                    print( 'Fikk feilmelding på JSON-dekoding av respons, hikke fra NVDB api? Prøver på ny en håndfull ganger med litt pause')
                    sleep( 15 )
                    iterasjontelling += 1
                    self.anrope( path, parametre=parametre, debug=debug, silent=silent, logganrop=logganrop, iterasjontelling=iterasjontelling )
                else: 
                    print( 'Beklager, må gi opp å parse data hentet med url', r.url)
                    print( err )
                    raise ValueError("Klarte ikke oversette respons fra NVDB api til JSON for kall " + r.url ) 
            else: 

                if debug and 'metadata' in data.keys(): 
                    print( '\n',  data['metadata'], '\n' ) 
                    
                if logganrop: 
                    loggfil = 'logganrop.txt'
                    if not os.path.exists( loggfil): 
                        with open( loggfil, 'w' ) as f2: 
                            f2.write( 'Logger alle anrop mot NVDB api V2 fra nvdbapi.py\n' ) 
                            f2.write( r.url ) 
                            f2.write( '\n' ) 
                            f2.write( json.dumps( data, indent=4, ensure_ascii=False) )
                            f2.write( '\n' )                          
                
                    with open(loggfil, 'a', encoding='utf-8' ) as f: 
                        f.write( '\n==========================\n' ) 
                        f.write( r.url ) 
                        f.write( '\n' ) 
                        f.write( json.dumps( data, indent=4, ensure_ascii=False) )
                        f.write( '\n' )  

            # Normalsituasjon, returnerer JSON-data    
            return data 

        elif r.status_code in [ 503, 504 ] and iterasjontelling < maks_iterasjoner: # Gateway timeout
            iterasjontelling += 1
            print( 'Http error, prøver om igjen', str( iterasjontelling), 'av', str( maks_iterasjoner), 'ganger om bittelita stund: '+str(r.status_code) +' '+r.url +
                            '\n' + r.text )
            sleep( 15 )
            data = self.anrope( path, parametre=parametre, debug=debug, silent=silent, logganrop=logganrop, iterasjontelling=iterasjontelling )
            return data 

        elif r.status_code == 401: 
            raise ValueError( 'Ugyldig pålogging', str(r.status_code) + ' ' + r.url + '\n' + r.text ) 

        elif r.status_code == 403: 
            raise ValueError( 'Ugyldig pålogging', str(r.status_code) + ' ' + r.url + '\n' + r.text ) 

        else:
            if not silent: 
                print( 'Http error: '+str(r.status_code) +' '+r.url +
                            '\n' + r.text )
            raise ValueError('Http error: '+str(r.status_code) +' '+r.url +
                            '\n' + r.text )
                            
    def refresh(self):
        """Deletes all data, resets pagination to 0"""
        self.paginering['hvilken'] = 0
        self.paginering['initielt'] = True
        self.paginering['meredata'] = True
        self.data =  { 'objekter' : []}
    
    

    def update_http_header(self, filename='nvdbapi-clientinfo.json'): 
    
        contactsfile = filename
        
        # Tricks for at qgis skal kunne finne klientinfo
        if 'nvdbapi-dir' in os.environ.keys():
            contactsfile = os.environ['nvdbapi-dir'] + '/' + contactsfile
        
        # Http header info
        try: 
            with open(contactsfile) as data_file:    
                contacts = json.load(data_file)

            if isinstance( contacts, dict): 
                self.headers = merge_dicts( self.headers, contacts) 

                if 'X-Client' not in contacts.keys(): 
                    warn(' '.join(('No X-Client defined in ', contactsfile)) ) 
                    
                if 'X-Kontaktperson' not in contacts.keys(): 
                    warn(' '.join(('No X-Contact defined in ', contactsfile)) ) 

            else: 
                warn( 'X-Client and X-Contact not updated')
                warn( ''.join(( 'Tror ikke ', contactsfile, 
                            ' har riktig struktur', '\nSe dokumentasjon')) )
                
        except IOError:
            mytext = ' '.join( ('\nYou should provide the file', 
                            contactsfile,  '\n',   
                    '\n{ "X-Client" : "YOUR SYSTEM",\n', 
                    '"X-Kontaktperson" : "ola.nordmann@eposten.din" }\n' ))
            # warn( mytext ) 

    def miljo(self, *args):
        """Kun internt på vegvesen-nettet!
        Kan endre hvilket miljø vi går mot.
        Parametre: 
            ingen - skriver ut hvilken URL vi bruker for å hente data fra NVDB api
            'utv' - bruker UTVIKLINGSmiljøet (ATLAS)
            'test' - bruker TESTmiljø (ATLAS)
            'prod' - går mot PRODUKSJON (ATLAS)
        eksempel
        b = nvdbFagdata(45)
        b.miljo()
        b.miljo('utv')
        b.miljo('test')
        b.miljo('prod')
        """
        
        if args and isinstance( args[0], str): 
            
            if 'utv' in  args[0].lower() and not 'stm' in args[0].lower(): 
                self.apiurl = 'https://nvdbapiles-v3.utv.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('utvles')
            elif 'stm-utvles' in args[0].lower(): 
                self.apiurl = 'https://nvdbapiles-v3-stm.utv.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('stm-utvles')
            elif 'test' in args[0].lower(): 
                self.apiurl = 'https://nvdbapiles-v3.test.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('testles')
            elif 'prod' in args[0].lower(): 
                self.apiurl = 'https://nvdbapiles-v3.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('prodles')
            else: 
                print( "Forstod ikke parameter:", args[0])
                print("Lovlige valg: utv, test eller prod")
        
        # if not silent: 
        # print( "Bruker ", self.apiurl)


    def info(self): 


        if isinstance( self, nvdbFagdata): 

            print( 'nvdbFagdata: Søkeobjekt for vegobjekter fra NVDB api V3')

            if self.objektTypeId: 
                print( 'ObjektType:', 
                    str(self.objektTypeId), self.objektTypeDef['navn'] )
        
            else: 
                print( 'Ikke definert noen objekttype ennå') 
                print( 'Bruk: x = nvdbFagdatID) eller\n', ' x = nvdbFagdata()\n', 
                        'x.objektType(ID)\n', 
                        'hvor ID er objekttypens ID, eks bomstasjon = 45\n\n') 
                
        elif isinstance( self, nvdbVegnett):
            print( 'nvdbVegnett: Søkeobjekt for vegnett fra NVDB api V3')


    
        print( 'Filtere')
        print( json.dumps( self.filterdata, indent=4))
        print( 'Parametre som styrer responsen:' ) 
        print( json.dumps( self.respons, indent=4))
        if isinstance( self, nvdbFagdata):         
            print( 'Statistikk fra NVDB api V3') 
            print( json.dumps( self.statistikk(), indent = 4))

        print( 'Pagineringsinfo: Antall objekt i databuffer=', len( self.data['objekter']))
        print( json.dumps( self.paginering, indent = 4)) 
                
    def to_records(self, **kwargs): 
        """
        Eksporterer søk for vegnett til liste med NVDB api V3 segmentert vegnett, littegrann forflatet

        Vi henter informasjon fra strekning, sideanlegg og kryssystem og legger på rot-nivå, slik at det 
        blir enklere å bruke. 

        ARGUMENTS
            None
        KEYWORDS 
            droppRiksvegruter : True (defalt) Tar vekk informasjon om riksvegruter. Sett til False for å 
                                                få med dictionary med riksvegrute-informasjon

            droppKontrakter : True (default) Tar vekk informasjon om kontraktsområder. Sett til False for å 
                                                få med dictionary med kontraktsområder-informasjon 

            kvalitetsparametre : False (default), sett lik True for å ta med geometriens kvalitetsparametre 

            Alle nøkkelord sendes videre til funksjonen flatutvegnetsegment 

        Returns
            Liste med segmentert vegnett fra NVDB api V3, forflatet for enklere bruk 
        """

        data = []
        v1 = self.nesteForekomst()

        if hasattr( self, 'antall') and self.antall > 10000: 
            print( 'Eksport av', self.antall, 'vegsegmenter kommer til å ta tid...')

        count = 1
        while v1: 

            v1 = flatutvegnettsegment( v1, **kwargs )
            data.append( v1 )
            v1 = self.nesteForekomst()
            count += 1
            if count == 1000 or count == 5000 or count % 10000 == 0: 
                print( 'Vegsegment', count, 'av', self.antall)            

        return data

    def vegrefrutesok(self, vref1, vref2, **kwargs ): 
        """
        PROTOTYPE - Finner vegnett langs rute mellom start- og sluttpunkt angitt med vegsystemreferanse

        https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_beta_vegnett_rute

        Resultatene puttes inn i søkeobjektets datastruktur, og du kan bruke de vanlige funksjonene 
        for å aksessere dem (nesteForekomst, to_records() og så videre) 

        Bruker stand-alone funksjonen vegref2rute 

        TODO: Tweake på parameterrom etc til funksjonen er optimalt tilpasset bruksmønster, f.eks 
            - flere måter å angi start- og sluttpunkt på ruta? (koordinater, posisjon på veglenkesekvens) 

        ARGUMENTS: 
            vref1 - string, vegsystemreferanse for starten på ruta
            vref2 - string, vegsystemreferanse for slutten på ruta

        KEYWORDS: 
            Evt nøkkelord blir brukt som parametre i rutesøket mot NVDB api V3 /beta/vegnett/rute
            https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_beta_vegnett_rute

        RETURNS: 
            None. Modifiserer i stedet datainnholdet i Vegnett - forekomsten 
        """

        data = vegref2rute(vref1, vref2, forb=self.forbindelse, **kwargs )

        if data and 'vegnettsrutesegmenter' in data and len( data['vegnettsrutesegmenter']) > 0: 
            self.refresh()
            self.data['objekter'] = data['vegnettsrutesegmenter']
            self.paginering['meredata'] = False
            self.paginering['initielt'] = False
            self.paginering['dummy'] = True 
        else: 
            print( 'Fant ikke gyldig rute', vref1, vref2 )


class nvdbNoder(nvdbVegnett): 
    """
    Henter ut noder fra NVDB api LES, nesten slik som nvdbVegnett. Har flesteparten av de samme metodene som nvdbVegnett 

    Ref https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_vegnett_noder
    """

    def __init__( self, miljo=None, debug=False, filter=None):
        self.filterdata = {}
        self.headers =   { 'accept' : 'application/vnd.vegvesen.nvdb-v3-rev3+json', 
                            'X-Client' : 'nvdbapi.py',
                            'X-Kontaktperson' : 'jan.kristian.jensen@vegvesen.no'}

        self.paginering = { 'antall'                : 1000,     # Hvor mange obj vi henter samtidig.
                            'hvilken'               : 0,        # iterasjon i det lokale datasettet 
                                                                # Dvs i+1 til array self.data['objekter'] 
                                                                # 
                            'antallObjektReturnert' : 0,        # Løpenummer, antall objekter vi har 
                                                                # returnert totalt fra nesteForekomst / next  
                                                                # 
                            'meredata'              : True,     # Gjetning på om vi kan hente mere data
                            'initielt'              : True,     # Initiell ladning av datasett
                            'dummy'                 : False     # Jukse-bruk av paginering 
                    } 

        self.data = { 'objekter' : []}
        self.filterdata = {}
        if isinstance( filter, dict ): 
            self.filterdata = filter 

        self.forbindelse = apiforbindelse.apiforbindelse()
        if not miljo:
            miljo = 'prod'
        self.miljo( miljo )
        self.forbindelse.velgmiljo( miljo.lower()+'les')
        self.debug = debug

        # Leser verdier for http header fra JSON-fil
        self.update_http_header()
        
        # Refresh er lurt, (arver tilstand fra andre instanser). 
        self.refresh()



class nvdbFagdata(nvdbVegnett): 
    """Søkeobjekt - dvs klasse for spørringer mot NVDB ang en spesifikk objekttype. 
    Jobber dynamisk mot NVDB api for å hente statistikk, laste ned data etc.
    Holder alle parametre som inngår i dialogen med NVDB api. 

    Grovt sett har vi disse funksjonene: 
        - Enkle metoder for å sette søkefilter
        (geografisk filter, egenskapsfilter m.m.) 

        - Enkle metoder for å hente, lagre og inspisere alle NVDB fagdata
        som tilfreddstiller søkekriteriene. 
        
        - Smart utnyttelse av NVDB api'ets pagineringsfunksjon. 
            - Liste med objekter man kan iterere over
            - Hent neste "batch" med objekter 
            - Hent hvert enkelt objekt

        - Statistikk for dette søket  

    # EKSEMPEL    
    n = nvdbFagdata(45) # Søkeobjekt for objekttype 45, dvs Bomstasjon
    n.filter( { 'egenskap' :  '1820>=20' } ) # Filterer bomstasjoner med takst liten bil >= 20kr. 
    
    Filteret kan også settes som parameter når du oppretter søkeobjektet, eksempel 
    n = nvdbFagdata( 45, filter={'kommune' : 5001})

    # EKSEMPEL: Iterer over alle bomstasjoner
    n = nvdbFagdata(45) 
    bomst = n.nesteForekomst()
    while bomst: 
        print bomst['id']  # Gjør noe spennende
        bomst = n.nesteForekomst()

    """
    
    
    
    def __init__( self, objTypeID, miljo=None, debug=False, filter=None ):


        self.headers =   { 'accept' : 'application/vnd.vegvesen.nvdb-v3-rev1+json', 
                        'X-Client' : 'nvdbapi.py',
                        'X-Kontaktperson' : 'Anonymous'}
    
        self.paginering = { 'antall'                : 1000,     # Hvor mange obj vi henter samtidig.
                            'hvilken'               : 0,        # iterasjon i det lokale datasettet 
                                                                # Dvs i+1 til array self.data['objekter'] 
                                                                # 
                            'antallObjektReturnert' : 0,        # Løpenummer, antall objekter vi har 
                                                                # returnert totalt fra nesteForekomst / next  
                                                                # 
                            'meredata'              : True,     # Gjetning på om vi kan hente mere data
                            'initielt'              : True,     # Initiell ladning av datasett
                            'dummy'                 : False     # Jukse-bruk av paginering 
                    }  
    
        self.data = { 'objekter' : []}
        self.apiurl = 'https://nvdbapiles-v3.atlas.vegvesen.no/'
        self.objektTypeId = None
        self.objektTypeDef = None
        self.antall = None
        self.strekningslengde = None
        self.filterdata = {}
        self.geofilter = {}         # DEPRECEATED
        self.egenskapsfilter = {}   # DEPRECEATED
        self.overlappfilter = {}    # DEPRECEATED
        self.forbindelse = apiforbindelse.apiforbindelse()
        if not miljo: 
            miljo = 'prod'
        self.miljo( miljo)
        self.forbindelse.velgmiljo( 'prodles')

        self.debug = debug


        # Standardverdier for responsen
        self.respons  = { 'inkluder' :  ['alle'] # Komma-separert liste
                        }
        
        # Leser verdier for http header fra JSON-fil
        self.update_http_header()
        
        # Refresh er lurt, (arver tilstand fra andre instanser). 
        self.refresh()

        # Leser typedefinisjon fra NVDB api
        self.objektTypeDef = self.anrope( '/'.join(( 'vegobjekttyper', 
                                            str(objTypeID))) )
        self.objektTypeId = objTypeID 

        if isinstance( filter, dict ): 
            self.filterdata = filter 

    def statistikk(self): 
        if self.objektTypeId: 
        
            parametre =  self.filterdata
            
            # Fjerner parametre som ikke gir mening (men feilmelding) for statistikk-kall
            forbud = [ 'antall', 'start', 'inkluder', 'geometritoleranse', 'projeksjon', 'dybde' ]
            for nei in forbud: 
                if nei in parametre.keys():
                    junk = parametre.pop(nei) 
            
            stat = self.anrope( '/'.join(('vegobjekter', str(self.objektTypeId), 
                            'statistikk')), parametre=parametre  )  
            self.antall = stat['antall'] 
            self.strekningslengde = stat['lengde'] 
            return stat
            
        else: 
            self.antall = None
            self.strekningslengde = None
            return { 'antall' : None, 'strekningslengde' : None }

    def egenskaper(self, *arg):
        """Skriver ut definisjonen av angitt egenskapstype (ID, heltall). 
        Hvis ingen ID oppgis skriver vi ut en liste med ID, navn og type
        for alle egenskapstyper for denne objekttypen. 
        """

        if len(arg) == 0: 
            for eg in self.objektTypeDef['egenskapstyper']:
                print( eg['id'], eg['navn'], eg['egenskapstype'] )
                
        else: 
            for eg in self.objektTypeDef['egenskapstyper']:
                if eg['id'] == arg[0] or str(arg[0]) in eg['navn']: 
                    print( json.dumps( eg, indent=4)) 
        
    def egenskaper_fastskjema( self, missing=None): 
        """Returnerer enkel mal for ALLE egenskaper etter datakatalogen. 
        (uten reelle data). Bruk missing-nøkkelord om du vil ha annen "tom" 
        verdi enn None. 
        
        Brukes for de tilfellene der du trenger data ihht fastlagt skjema, 
        f.eks. CSV-dump eller tilsvarende 
        """ 
        
        data = {}
        for eg in self.objektTypeDef['egenskapstyper']:
                data[eg['navn']] = missing
                
        return data
               
    def addfilter_overlapp( self, *arg): 
        """
        DEPRECEATED: replaced with addfilter - function
        
        addfilter_geo, addfilter_egenskap and addfilter_overlapp are now obsolete and 
        replaced with the generic addfilter function 

        For now, any addfilter_overlap-arguments are simply passed to 
        the addfilter function: filter( {'overlapp' : 'YOUR ARGUMENT HERE'})
        """ 
        warn( "addfilter_geo is depreceated, please use the generic addfilter function", DeprecationWarning)
        
        if len( arg) == 1 and arg[0]: 
            self.filter( { 'overlapp' : arg[0] } ) 
        
    def addfilter_egenskap( self, *arg): 
        """
        DEPRECEATED: replaced with addfilter - function
        
        addfilter_geo, addfilter_egenskap and addfilter_overlapp are now obsolete and 
        replaced with the generic addfilter function 

        For now, any addfilter_egenskap-arguments are simply passed to 
        the addfilter function: filter( {'egenskap' : 'YOUR ARGUMENT HERE'})

        """ 
        
        warn( "addfilter_egenskap is depreceated, please use the generic addfilter function", DeprecationWarning)
        
        if len( arg) == 1 and arg[0]: 
            self.filter( { 'egenskap' : arg[0] } ) 
                        
    def nesteNvdbFagObjekt( self ): 
        fagdata = self.nesteForekomst()
        if fagdata: 
            fagobj = nvdbFagObjekt(fagdata)
            return( fagobj)
        else: 
            return None
        
    def to_records(self, vegsegmenter=True, relasjoner=True, geometri=False, debug=False, tidspunkt=None, ignorerGeometriFeil=False, geometrikvalitet=False ): 
        """
        Eksporterer til en liste med dictionaries med struktur 
        "objekttype" : INT,
        "objektId" : INT, 
        "versjon" : INT,
        "metadata" : metadata-element (dictionary)
        "egenskapnavn1" : verdi,
        "egenskapnavn2" : geometri,
            ...
        "geometri" : "WELL KNOWN TEXT" 
        "vref" : Kortform vegsystemreferanse. Hvis det er fler enn ett element blir dette en 
                    kommaseparert liste.  
        "vegsystemreferanser : [ liste med vegsystemreferanse-dictionary ]
        "vegsegmenter" : [ liste med vegsegmenter ]

        Parameter vegsegmenter=True de-normaliserer, dvs hvis et objekt har N vegsegmenter 
        får du returnert N forekomster av objektet, ett for hver unike vegsegment. Videre 
        blir egenskapene vegsystemreferanse og vegsegmenter ikke lister, men dictionaries 

        Paramter relasjoner=True: Tar med dictionary over relasjoner til andre objekter

        Parameter geometri=False: Tar ikke med s.k. egengeometri(er)

        ARGUMENTS
            feature_eller_liste Dictionary eller liste med dictionies med NVDB fagdata slik de kommer fra NVDB api V3

        KEYWORDS 
            vegsegmenter=True (default) | False : Gi en forekomst (av objektet) per unike vegsegment
            
            relasjoner=True (default) | False : Ta med mer detaljer om objektets relasjoner 
            
            geometri=False (default) | True : Hent geometri fra objektets vegtilknytning, evt bruk objektets 
                                            egengeometri (hvis den finnes, vegtilknytning er alltid fallback) 
            
            debug=False (default) | True : Detaljert debug-informasjon 
            
            tidspunkt=None | datostreng (tekst) på formen '2010-01-01'. DEAKTIVERT, NVDB api gir oss uansett kun de vegsegmentene
                        som er gyldige for det tidspunktet som står i API-kallet. 

            ignorerGeometriFeil=False (default) Hvis True så tar vi med også de objektene som mangler noen form for geometridata

            geometrikvalitet=False (default), Hvis True så tar vi med kvalitetsparametre (metadata) for objektets egengeometri (hvis de finnes). 
                                              Forutsetter at du også har valgt geometri=True

        RETURNS
            liste med dictionaries (NVDB-objekt fra NVDB api LES v3 i utflatet struktur)

        """

        if ignorerGeometriFeil: 
            print( f"To_records: Tar med vegobjekt som mangler geometridata")

        mydata = []
        if not self.antall: 
            self.statistikk()

        if self.antall and self.antall > 10000: 
            print( 'Eksport av', self.antall, 'objekter kommer til å ta tid...')

        # Sjekker om vi jobber med historiske data:
        if not tidspunkt: 
            if 'tidspunkt' in self.filterdata.keys():
                tidspunkt = self.filterdata['tidspunkt']

        count = 0
        nvdbid_manglergeom = []
        terskler = [ 1000, 10000]
        feat = self.nesteForekomst()
        while feat:
            count += 1
            if count == 1000 or count == 5000 or count % 10000 == 0: 
                print( 'Objekt', count, 'av', self.antall)

            # Ignorerer dem med tomt geometrielement, ref 
            # https://github.com/LtGlahn/diskusjon_diverse/tree/master/debug_nvdbapilesv3/vegobjekter 
            if 'geometri' in feat.keys() or ignorerGeometriFeil:

                featureliste = nvdbfagdata2records( feat, vegsegmenter=vegsegmenter, relasjoner=relasjoner, 
                                                    geometri=geometri, debug=debug, tidspunkt=tidspunkt, 
                                                    ignorerGeometriFeil=ignorerGeometriFeil, geometrikvalitet=geometrikvalitet )
            
                mydata.extend( featureliste )
            else: 
                nvdbid_manglergeom.append( feat['id'])


            feat = self.nesteForekomst()

        if len( nvdbid_manglergeom ) > 0: 
            print( 'Manglende geometri-element for', len( nvdbid_manglergeom), 'vegobjekter fra dette søket')
            self.info()
            print( 'fra miljø', self.apiurl )
            if debug: 
                print( nvdbid_manglergeom )

        return mydata


class nvdbFagObjekt():
    """Class for NVDB objects, with methods to get data from them"""
    
    def __init__( self, rawdata, ignorewarnings=False): 
        
        self.href = rawdata['href']
        self.lokasjon       = rawdata['lokasjon']
        self.id             = rawdata['id']
        self.relasjoner     = rawdata['relasjoner']
        self.metadata       = rawdata['metadata']

        # Litt klønete håndtering, ikke alle objekter som er knyttet til 
        # gyldig vegnett - og de mangler lokasjonsdata
        # Noen av disse mangler også egenskapsdata... 
        if 'vegsegmenter' in rawdata:    
            self.vegsegmenter   = rawdata['vegsegmenter']
        else: 
            self.vegsegmenter = []
            if not ignorewarnings: 
                warn(' '.join(['Ingen vegsegmenter i NVDB objekt', str(rawdata['id'])]) )

        if 'geometri' in rawdata: 
            self.geometri       = rawdata['geometri']
        else: 
            self.geometri = None
            if not ignorewarnings: 
                warn(' '.join(['Ingen geometri i NVDB objekt', str(rawdata['id'])]) )

        if 'egenskaper' in rawdata: 
            self.egenskaper       = rawdata['egenskaper']
        else: 
            self.egenskaper = []
            if not ignorewarnings: 
                warn(' '.join(['Ingen egenskaper i NVDB objekt', str(rawdata['id'])]) )

        
    def egenskap( self, id_or_navn, empty=None ):
        """Returns property egenskap with ID or NAME (navn) = id_or_navn
        Optional keyword empty changes what you get if this property 
        does not exist (i.e. does not have value) for this data
        The return value contains some metadata with ID's and stuff, 
        example: 
            {'navn': {'datatype': 1,
              'datatype_tekst': 'Tekst',
              'id': 8129,
              'navn': 'Navn',
              'verdi': 'Lofoten'}}

        To just get the data value, use function egenskapverdi
        """
        
        for i, dic in enumerate( self.egenskaper): 
            if dic['id'] == id_or_navn or str( id_or_navn) == dic['navn'] or \
                        str( id_or_navn ).lower() in dic['navn'].lower() or \
                        str(dic['id']) == str( id_or_navn): 

                return dic

        return empty 
    
            
    def egenskapverdi( self, id_or_navn, empty=None ):
        """Returns the property VALUE with ID or NAME (navn) = id_or_navn
        Just a convenient wraper around the egenskap - method, so you just 
        get the data value (and not all metadata, with ID's and definitions)

        Nytt i NVDB api V3: Stedfesting på vegnett og assossiasjon (relasjon mellom objekter) 
        er også egenskaper. Hvis du eksplisitt ber om disse så får du en tekst-representasjon av 
        denne datastrukturen(json.dumps)
        """ 
        egenskap = self.egenskap( id_or_navn, empty=empty)

        stedfesting_eller_assosiasjon = [ 'Stedfesting', 'Liste' ]

        if egenskap and egenskap != empty and egenskap['egenskapstype'] not in stedfesting_eller_assosiasjon: 
            if 'verdi' in egenskap: 
                return egenskap['verdi']
            elif egenskap['egenskapstype'].upper( ) == 'BINÆR' and 'href' in egenskap: 
                return egenskap['href'] 
                
        elif egenskap and egenskap != empty and egenskap['egenskapstype'] in stedfesting_eller_assosiasjon:
            return json.dumps( egenskap, indent=4, ensure_ascii=False)
        else: 
            return egenskap

    def enumverdi( self, id_or_navn, empty=None): 
        """Same as egenskapsverdi - but will return the ENUM code 
        for ENUM values. For non-enum datatypes you will get 
        your favourite empty-value (default: None) 
        """ 
        egenskap = self.egenskap( id_or_navn, empty=empty)
        if egenskap and egenskap['datatype'] in [29,30]: 
            return egenskap['enum_id']
        else: 
            return empty
            
            
    def egenskapverdier_fastskjema(self, skjema  ): 
        """Fyller ut skjema med de egenskapsverdiene som matcher egenskapsnavn"""
        
        skjem2 = deepcopy( skjema)
        for eg in self.egenskaper: 
            if eg['navn'] in skjem2.keys():
                skjem2[eg['navn']] = eg['verdi']
            
        return skjem2        

    def wkt( self):
        """Returns the geometry of the object as Well Known text (WKT)
        https://en.wikipedia.org/wiki/Well-known_text
        """ 
        return self.geometri['wkt']

    def relasjon( self, relasjon=None): 
        """Returns all or a subset of relations to other NVDB objects
        Keyword relasjon='barn' or 'foreldre',  or the name or ID of the 
        object type you wish were releated. 
        """
        
        # If we have integers as strings => cast to int
        # Makes the logic less messy... 
        if isinstance( relasjon, str) and relasjon.isdigit():
            relasjon = int(relasjon)
        
        if not relasjon: 
            return self.relasjoner
            
        # INT: Match on datakatalog ID
        elif isinstance(relasjon, int): 
            if isinstance( relasjon, str): 
                relasjon = int(relasjon)
                            
            for key, liste in self.relasjoner.items():
        
                for elem in liste: 
                    if elem['type']['id'] == relasjon:
                        return elem
     
            return None
            
        elif isinstance( relasjon, str):
            if relasjon.lower() == 'mor' or relasjon.lower() == 'foreldre':
                if 'foreldre' in self.relasjoner:
                    return self.relasjoner['foreldre']
                else: 
                    return None

            elif  relasjon.lower() == 'barn' or relasjon.lower() == 'datter': 
                if 'barn' in self.relasjoner:
                    return self.relasjoner['barn']                
                else:
                    return None
                
            else: 

        # Match on data catalogue name                 
        # Finding exact match - if any
                for key, liste in self.relasjoner.items():

                    for elem in liste: 
                        if relasjon == elem['type']['navn']:
                            return elem
                
        # Finding partial match - if any 
                for key, liste in self.relasjoner.items():
                    for elem in liste: 
                        if relasjon in elem['type']['navn']:
                            return elem
                    
                    return None
            
            
        else: 
            # Raise error
            raise ValueError('Function relasjon: Keyword argument relasjon must be int or string' )
            


def nvdbfagobjekt2records( feature_eller_liste, **kwargs): 
    """
    DEPRECEATED, bruk nvdbfagdata2records

    Navnebytte å unngå navneforvirring med vår egen pythonklasse  "nvdbFagobjekt" 
    """

    warn( 'nvdbfagobjekt2records har byttet navn => nvdbfagdata2records', category=DeprecationWarning, stacklevel=2)

    data = nvdbfagdata2records( feature_eller_liste, **kwargs) 
    return data 

def nvdbfagdata2records( feature_eller_liste, vegsegmenter=True, relasjoner=True, geometri=False, debug=False, tidspunkt=None, ignorerGeometriFeil=False, geometrikvalitet=False  ): 
    """
    Gjør om (liste med) nvdb fagdata fra NVDB api LES til records, dvs de-normalisert til dictionaries med enkel struktur. 

    Denne brukes av funksjonen nvdbFagobjekt.to_records(), men er skilt ut fordi den er nyttig for alle
    som har en liste med NVDB objekter :) 

    Eksporterer til en liste med dictionaries med struktur 
    "objekttype" : INT,
    "objektId" : INT, 
    "versjon" : INT,
    "metadata" : metadata-element (dictionary)
    "egenskapnavn1" : verdi,
    "egenskapnavn2" : geometri,
        ...
    "geometri" : "WELL KNOWN TEXT" 
    "vref" : Kortform vegsystemreferanse. Hvis det er fler enn ett element blir dette en 
                kommaseparert liste.  
    "vegsystemreferanser : [ liste med vegsystemreferanse-dictionary ]
    "vegsegmenter" : [ liste med vegsegmenter ]

    Parameter vegsegmenter=True vil gi deg en forekomst av objektet per vegsegment, 
    dvs hvis et objekt har N vegsegmenter får du returnert N forekomster av objektet, 
    ett for hver unike vegsegment. Videre blir egenskapene vegsystemreferanse og vegsegmenter 
    ikke lister, men dictionaries 

    Paramter relasjoner=True: Tar med dataelementet "relasjoner" fra objektet (dictionary-struktur med de ulike typer
    relasjoner for objektet)

    Parameter geometri=False: Tar ikke med s.k. egengeometri(er)

    ARGUMENTS
        feature_eller_liste Dictionary eller liste med dictionies med NVDB fagdata slik de kommer fra NVDB api V3

    KEYWORDS 
        vegsegmenter=True (default) | False : Gi en forekomst (av objektet) per unike vegsegment
        
        relasjoner=True (default) | False : Ta med mer detaljer om objektets relasjoner 
        
        geometri=False (default) | True : Hent geometri fra objektets vegtilknytning, evt bruk objektets 
                                          egengeometri (hvis den finnes, vegtilknytning er alltid fallback) 
        
        debug=False (default) | True : Detaljert debug-informasjon 
        
        tidspunkt=None | dato som tekst på formen '2010-01-01'. Angi tidspunkt som brukes til å filtrere hvilke vegsegmenter som tas med
                DEAKTIVERT, NVDB api gir kun ut de vegsegmentene som er gyldige på angitt tidspunkt for spørringen

        ignorerGeometriFeil=False, tar med objekter som mangler gyldige geometridata (tomt dataelement)

        geometrikvalitet=False, tar med kvalitetsparametre (metadata) for geometri (hvis den finnes). Forutsetter at geometri=True

    RETURNS
        liste med dictionaries (vegobjekt fra NVDB api LES i flatere dictionary-struktur)

    """
    if not isinstance( feature_eller_liste, list): 
        feature_eller_liste = [ feature_eller_liste ]

    mydata = [ ]

    if tidspunkt: 
        gyldigdato = dateutil.parser.parse( tidspunkt )

    nvdbid_manglergeom = []
    terskler = [ 1000, 10000]

    for count, feat in enumerate(feature_eller_liste): 
        
        if ignorerGeometriFeil or 'geometri' in feat.keys():

            meta = { }
            
            meta['objekttype']  = feat['metadata']['type']['id']
            meta['nvdbId'] = feat['id']
            meta['versjon'] = feat['metadata']['versjon']
            meta['startdato'] = feat['metadata']['startdato']
            if 'sluttdato' in feat['metadata'].keys():
                meta['sluttdato'] = feat['metadata']['sluttdato']

            # meta['metadata'] = feat['metadata']

            egenskaper = egenskaper2records( feat['egenskaper'], relasjoner=False, geometri=geometri, geometrikvalitet=geometrikvalitet )
            if relasjoner and 'relasjoner' in feat.keys() and len( feat['relasjoner']) > 0: 
                egenskaper['relasjoner'] = feat['relasjoner']

            egenskaper = merge_dicts( meta, egenskaper)

            if vegsegmenter: 
                for seg in feat['vegsegmenter']:

                    # Kommenterer ut tidspunkt-logikk fordi NVDB api nå (per mai 2021) kun presenterer de vegsegmentene som er 
                    # gyldige på angitt tidspunkt (default i dag) i API-kallet 
                    # if not 'sluttdato' in seg.keys() or (tidspunkt  and \
                    #     dateutil.parser.parse( seg['startdato'] ) <= gyldigdato and \
                    #     dateutil.parser.parse( seg['sluttdato'] ) > gyldigdato ):


                    s2 = {  'veglenkesekvensid' : seg['veglenkesekvensid'], 
                            'detaljnivå'        : seg['detaljnivå'],
                            'typeVeg'           : seg['typeVeg'],
                            'kommune'           : seg['kommune'], 
                            'fylke'             : seg['fylke']
                            }

                    if 'vegsystemreferanse' in seg.keys() and 'kortform' in seg['vegsystemreferanse'].keys():
                        s2['vref'] = seg['vegsystemreferanse']['kortform'] 

                    if 'veglenkeType' in seg: 
                        s2['veglenkeType'] = seg['veglenkeType']

                    if 'medium' in seg: 
                        s2['medium'] = seg['medium']

                    vr = 'vegsystemreferanse'
                    if 'vegsystem' in seg[vr].keys():
                        s2['vegkategori'] = seg[vr]['vegsystem']['vegkategori']
                        s2['fase'] = seg[vr]['vegsystem']['fase']
                        if 'nummer' in seg[vr]['vegsystem']: 
                            s2['vegnummer'] = seg[vr]['vegsystem']['nummer']

                    if 'startposisjon' in seg.keys() and 'sluttposisjon' in seg.keys():
                        s2['startposisjon'] = seg['startposisjon'] 
                        s2['sluttposisjon'] = seg['sluttposisjon']
                        s2['segmentlengde']        = seg['lengde']
                    elif 'relativPosisjon' in seg.keys(): 
                        s2['relativPosisjon'] = seg['relativPosisjon']
                    else: 
                        print( 'Snål feil, mangler posisjon langs lenkesekvens???', feat['id'])

                    if 'strekning' in seg[vr].keys() and 'adskilte_løp' in seg[vr]['strekning']:
                        s2['adskilte_lop'] = seg[vr]['strekning']['adskilte_løp']


                    delkeys = [ 'strekning', 'kryssystem', 'sideanlegg']
                    for hvaslag in delkeys: 
                        if  hvaslag in seg['vegsystemreferanse'].keys(): 
                            s2['trafikantgruppe'] = seg['vegsystemreferanse'][hvaslag]['trafikantgruppe']
                            s2['segmentretning']  = seg['vegsystemreferanse'][hvaslag]['retning']
                        
                    s2['geometri'] = seg['geometri']['wkt']

                    # Itererer over lokasjons-elementene for å finne evt sideposisjon og kjørefelt-stedfesting
                    for lok in feat['lokasjon']['stedfestinger']: 
                        if 'relativPosisjon' in seg:
                            if lok['veglenkesekvensid'] == seg['veglenkesekvensid'] and lok['relativPosisjon'] == seg['relativPosisjon']: 
                                if 'sideposisjon' in lok and isinstance( lok['sideposisjon'], str): 
                                    s2['sideposisjon'] = lok['sideposisjon']
                                if 'kjørefelt' in lok and isinstance( lok['kjørefelt'], list) and len( lok['kjørefelt'] ) > 0:
                                    s2['stedfesting_felt'] = ','.join( lok['kjørefelt'])                                 
                                if 'retning' in lok: 
                                    s2['stedfesting_retning'] = lok['retning']
                            
                        else: 
                            if lok['veglenkesekvensid'] == seg['veglenkesekvensid'] and lok['startposisjon'] == seg['startposisjon'] and lok['sluttposisjon'] == seg['sluttposisjon']:
                                if 'sideposisjon' in lok: 
                                    s2['sideposisjon'] = lok['sideposisjon']
                                if 'kjørefelt' in lok and isinstance( lok['kjørefelt'], list) and len( lok['kjørefelt'] ) > 0:
                                    s2['stedfesting_felt'] = ','.join( lok['kjørefelt']) 
                                if 'retning' in lok: 
                                    s2['stedfesting_retning'] = lok['retning']

                    egenskaper_kopi = deepcopy( egenskaper )
                    egenskaper_kopi = merge_dicts( egenskaper_kopi, s2)
                    mydata.append( egenskaper_kopi )
            else: 
                egenskaper['vegsystemreferanser'] = ','.join([ d['kortform'] for d in feat['lokasjon']['vegsystemreferanser'] ] )
                egenskaper['stedfestinger']       = ','.join([ d['kortform'] for d in feat['lokasjon']['stedfestinger'] ] )

                # Itererer over stedfesting-elementer for å få med evt sideposisjon og felt-stedfesting 
                stedfestinger = [] # Liste med tekst
                for lok in feat['lokasjon']['stedfestinger']: 
                    side = ''
                    felt = ''
                    retning = ''
                    if 'retning' in lok: 
                        retning = ' ' + lok['retning']
                    if 'sideposisjon' in lok: 
                        side = ' ' + lok['sideposisjon']
                    if 'kjørefelt' in lok and isinstance( lok['kjørefelt'], list) and len( lok['kjørefelt'] ) > 0: 
                        felt = ' (' +  ','.join( lok['kjørefelt']) + ')'
                    stedfestinger.append( lok['kortform'] + retning + side + felt )
                egenskaper['stedfesting_detaljer'] = ','.join( stedfestinger )

                egenskaper['vegsegmenter']        = feat['vegsegmenter']
                if 'geometri' in feat.keys():
                    egenskaper['geometri']  = feat['geometri']['wkt']
                else:
                    nvdbid_manglergeom.append( feat['id']) 

                if 'lengde' in feat['lokasjon']: 
                    egenskaper['strekningslengde'] = feat['lokasjon']['lengde']
                mydata.append( egenskaper )

        else: 
            nvdbid_manglergeom.append( feat['id'])

    if len( nvdbid_manglergeom ) > 0: 
        if ignorerGeometriFeil: 
            print( f"{len(nvdbid_manglergeom)} av {len(mydata)} rader mangler geometriinformasjon")
        else: 
            print( 'nvdbfagdata2records: Ignorerer ', len(nvdbid_manglergeom ), ' NVDB objektversjoner som mangler geometri. Returnerer ', len(feature_eller_liste ), ' rader')

    return mydata 


def finnid(objektid, kunvegnett=False, kunfagdata=False, miljo=False): 
    """Henter NVDB objekt (enten lenkesekvens eller fagdata) ut fra objektID.
    Bruk nøkkelord kunvegnett=True eller kunfagdata=True for å avgrense til 
    vegnett og/eller fagdata (vi har betydelig overlapp på ID'er mellom vegnett 
    og fagdata)
    
    Fagdata returnerer en DICT
    Vegnett returnerer en LISTE med alle vegnettselementene for veglenka
    
    Nøkkelord miljo='utv', 'test' eller 'prod' (default) spesifiserer hvilket
    miljø som skal brukes.
    """
    
    # Dummy objekt for å gjenbruke anrops-funksjonene
    b = nvdbFagdata(45)
    if miljo:
        b.miljo( miljo)
    res = None

    # Henter fagdata    
    if kunfagdata or (not kunvegnett): 
        try:
            res = b.anrope( 'vegobjekt', parametre = { 'id' : objektid }, silent=True )
        except ValueError: 
            pass

        else:
            # Må hente fagobjektet på ny for å få alle segmenter (inkluder=alle)
            res = b.anrope( res['href'], parametre = { 'inkluder' : 'alle' } ) 

    # Henter vegnett
    if kunvegnett or (not kunfagdata) or (not res and not kunfagdata): 
        try: 
            res = b.anrope( 'vegnett/veglenkesekvenser/segmentert/' + str(objektid), silent=True)
            
        except ValueError: 
            pass

        # Sikrer at vi alltid returnerer liste med vegsegmenter - selv om vi kun har ett segment
        if isinstance( res, dict): 
            res = [ res ]

    if not res: 
        print( "Fant intet NVDB objekt eller vegnett med ID = " + str(objektid))
        
    return res

def vegrefpunkt( vref, retur='veglenkeposisjon', forb=None ): 
    """
    Slår opp vegsystemreferanse i NVDBAPILES V3. Returnerer koordinater, veglenkeposisjon eller hele datastrukturen. 

    https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_veg

    ARGUMENTS: 
        vref - string, vegsystemreferanse 

    KEYWORDS 
        retur - string, en av 
            - 'veglenkeposisjon' (default), 
            - 'wkt', string, koordinater formattert som well known text
            - 'komplett' : Dictionary med responsen fra NVDB api 

        forb - En instans av nvdbapiforbindelse. Angis dersom du skal bruke et annet miljø enn PROD

    RETURNS 
        - string eller dictionary, se 'retur'-nøkkelord. Returnerer None hvis feiler 
    """

    if not forb: 
        forb = apiforbindelse.apiforbindelse()
    params = { 'vegsystemreferanse' : vref }
    r = forb.les('/veg', params=params)
    if r.ok: 
        data = r.json() 
        if 'vegle' in retur.lower()  and 'veglenkesekvens' in data.keys() and 'kortform' in data['veglenkesekvens'].keys(): 
            return data['veglenkesekvens']['kortform']
        elif retur.lower() == 'wkt' and 'geometri' in data.keys() and 'wkt' in data['geometri'].keys(): 
            return data['geometri']['wkt']
        elif retur.lower() == 'komplett': 
            return data 

    return None 

def veglenkepunkt( vpos, retur='wkt', forb=None ): 
    """
    Slår opp vegsystemreferanse i NVDBAPILES V3. Returnerer koordinater, vegsystemreferanse eller hele datastrukturen. 

    https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_veg

    ARGUMENTS: 
        vpos - string, veglenkeposisjon på formatet .8225@21802 

    KEYWORDS 
        retur - string, en av 
            - 'wkt', string, koordinater formattert som well known text (default)
            - 'vegsystemreferanse' 
            - 'komplett' : Dictionary med responsen fra NVDB api 

        forb - En instans av nvdbapiforbindelse. Angis dersom du skal bruke et annet miljø enn PROD

    RETURNS 
        - string eller dictionary, se 'retur'-nøkkelord. Returnerer None hvis feiler 
    """

    if not forb: 
        forb = apiforbindelse.apiforbindelse()
    params = { 'veglenkesekvens' : vpos }
    r = forb.les('/veg', params=params)
    if r.ok: 
        data = r.json() 
        if 'ref' in retur.lower()  and 'vegsystemreferanse' in data.keys() and 'kortform' in data['vegsystemreferanse'].keys(): 
            return data['vegsystemreferanse']['kortform']
        elif retur.lower() == 'wkt' and 'geometri' in data.keys() and 'wkt' in data['geometri'].keys(): 
            return data['geometri']['wkt']
        elif retur.lower() == 'komplett': 
            return data 

    return None 


def vegref2rute( vref1, vref2, forb=None, **kwargs ): 
    """
    Finner rute (liste med veglenke-biter) mellom to punkt angitt som vegsystemreferanse i NVDBAPILES V3. 

    https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_beta_vegnett_rute

    ARGUMENTS: 
        vref1 - string, vegsystemreferanse for starten på ruta
        vref2 - string, vegsystemreferanse for slutten på ruta

    KEYWORDS 

        forb - En instans av nvdbapiforbindelse. Angis dersom du skal bruke et annet miljø enn PROD

        Alle resterende nøkkelord blir brukt som parametre i spørringene til /vegnett/beta/rute 

    RETURNS 
        liste med (biter av) veglenker som til sammen angir ei rute langs NVDB vegnett
    """
    returdata = []

    if not forb: 
        forb = apiforbindelse.apiforbindelse()

    # Finner posisjon på veglenkesekvens for start og slutt
    pos1 = vegrefpunkt( vref1, forb=forb )
    pos2 = vegrefpunkt( vref2, forb=forb )

    if pos1 and pos2: 
        returdata = hentrute( pos1, pos2, forb=forb, **kwargs )
    else: 
        if not pos1: 
            print( 'Ugyldig vegreferanse (eller timeout på spørring): ', vref1 )
        if not pos2: 
            print( 'Ugyldig vegreferanse (eller timeout på spørring): ', vref2 )

    return returdata


def hentrute( pos1, pos2, forb=None, droppRiksvegruter=True, droppKontrakter=True, **kwargs ): 
    """
    Henter vegnett langs rute fra pos1 => pos2 

    Henter vegnett som forbinder to posisjoner (pos1, pos2) på vegnettettet fra 
    endepunktet NVDB api LES / beta / vegnett / rute 

    ARGUMENTS
        pos1, pos2 - tekststreng med posisjon på veglenkesekvens, skrevet på formen 0.3744@21765 

    KEYWORDS
        forb: Instans av objekttype apiforbindelse. Brukes for å teste funksjonalitet i andre miljø enn PROD

        droppRiksvegruter : True (defalt) Tar vekk informasjon om riksvegruter. Sett til False for å 
                                            få med dictionary med riksvegrute-informasjon

        droppKontrakter : True (default) Tar vekk informasjon om kontraktsområder. Sett til False for å 
                                            få med dictionary med kontraktsområder-informasjon         

        Alle andre nøkkelord blir tolket som spørreparametre (filter) i spørringen til beta/vegnett/rute, 
        se dokumentasjon for https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_beta_vegnett_rute 

        TODO: Fjern beta-delen av URL når NVDB api oppgraderer vekk beta-stempelet

    RETURNS 
        liste med dictionaries, formulert på samme måte som det du får
                fra søkeobjektet nvdbVegnett sin funksjon .to_records() 
    """

    returdata = []

    if not forb or not 'apiforbindelse' in str( type( forb ) ): 
        forb = apiforbindelse.apiforbindelse()

    params = {}
    for (key,val) in kwargs.items(): 
        params[key] = val

    params['start']  = pos1
    params['slutt']  = pos2

    r = forb.les( '/beta/vegnett/rute', params=params )
    if r.ok: 
        data = r.json()

        # Ikke funnet rute? Prøver med større bbox 
        if 'IKKE' in data['metadata']['status_tekst'].upper() and (not 'omkrets' in params.keys() or params['omkrets'] < 10000): 
            params['omkrets'] = 10000
            returdata = hentrute( pos1, pos2, forb=forb, **params )

        else: 
            for segment in data['vegnettsrutesegmenter']: 
                v1 = flatutvegnettsegment( segment, droppRiksvegruter=droppRiksvegruter, droppKontrakter=droppKontrakter )
                returdata.append( v1 )

        if len( returdata ) == 0: 
            print( 'beta/vegnett/rute: Tomt resultatsett:', r.url )
    else: 
        print( 'beta/vegnett/rute: feilkode: ', r.status_code, r.url )

    return returdata 

def flatutvegnettsegment( vegnettsegment, droppRiksvegruter=True, droppKontrakter=True, kvalitetsparametre=False  ): 
    """
    Flater ut et veglenkesegment til en forenklet dictionary-struktur 

    Vi tar et segment fra NVDB api LES /vegnett/segmentert eller /beta/vegnett/rute og pakker 
    det om til en "flat" dictionary struktur, dvs bytter ut den objektorienterte NVDB-strukturen med 
    en flat key->value tilnærming. Noen egenskaper sletter vi (kontraktsområde, riksvegrute)

    Denne funksjonen brukes av søkebojektet nvdbVegnett.to_records() og rutesøk-funksjonene 

    ARGUMENTS
        vegnettsegment - dictionary med data for et vegnettsegment 

    KEYWORDS 
        droppRiksvegruter : True (defalt) Tar vekk informasjon om riksvegruter. Sett til False for å 
                                            få med dictionary med riksvegrute-informasjon

        droppKontrakter : True (default) Tar vekk informasjon om kontraktsområder. Sett til False for å 
                                            få med dictionary med kontraktsområder-informasjon 

        kvalitetsparametre : False (default), sett til True hvis du ønsker å bevare kvalitetsparametre

    RETURNS 
        dictionary, input-data med vegnettsinformasjon omarbeidet til flat struktur 
    """

    v1 = deepcopy( vegnettsegment ) 

    metadata = v1.pop( 'metadata', { } )
    v1.update( metadata)
    vr = 'vegsystemreferanse'
    vsys = 'vegsystem'
    strek = 'strekning'
    kryss = 'kryssystem'
    sidea = 'sideanlegg'

    if kvalitetsparametre: 
        v1['geometri_kvalitet']       = v1['geometri'].pop( 'kvalitet', None  )
        v1['geometri_datafangstdato'] = v1['geometri'].pop( 'datafangstdato', None )
        v1['geometri_temakode']       = v1['geometri'].pop( 'temakode', None ) 

    struktur = [ 
        { 'navn' : 'medium',    'verdi' : { 'l1' : 'geometri',    'l2' : 'medium'  }}, 
        { 'navn' : 'geometri',  'verdi' : { 'l1' : 'geometri',    'l2' : 'wkt'  }}, # NB! Geometri-dictionary byttes nå ut med WKT-tekststreng!
                                                                                    # Hvis du vil ha mer data ut av geometri-elementet 
                                                                                    # må du gjøre det FØR denne operasjonen (eller ta vare på data eksplisitt)
        { 'navn' : 'vref',      'verdi' : { 'l1' : vr,            'l2' : 'kortform'  }}
    ]

    for mykey in struktur: 
        try: 
                v1[mykey['navn']] = v1[mykey['verdi']['l1']][mykey['verdi']['l2']]
        except (KeyError, TypeError): 
            pass                 
    # Gjør om feltoversikt fra liste-objekt til (kommaseparert) ren tekst 
    try: 
        v1['feltoversikt']  = ','.join( v1['feltoversikt'])
    except KeyError: 
        pass 

    # Noen av disse verdiene hentes fra strekning, men overskrives med  data
    # fra kryssdel eller sidenanlegg dersom de finnes. 
    # Vi følger python-idomet med å prøve om verdiene er der og ubekymret springe 
    # videre hvis de ikke finnes. 
    struktur = [{ 'navn' : 'vegkategori'     , 'verdi' :  { 'l1' : vr, 'l2' : vsys, 'l3' : 'vegkategori'        }}, 
                { 'navn' : 'fase'            , 'verdi' :  { 'l1' : vr, 'l2' : vsys, 'l3' : 'fase'               }},  
                { 'navn' : 'nummer'          , 'verdi' :  { 'l1' : vr, 'l2' : vsys, 'l3' : 'nummer'             }}, 
                { 'navn' : 'strekning'       , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'strekning'         }}, 
                { 'navn' : 'delstrekning'    , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'delstrekning'      }}, 
                { 'navn' : 'ankerpunktmeter' , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'meter'             }}, 
                { 'navn' : 'kryssdel'        , 'verdi' :  { 'l1' : vr, 'l2' : kryss, 'l3' : 'kryssdel'          }}, 
                { 'navn' : 'sideanleggsdel'  , 'verdi' :  { 'l1' : vr, 'l2' : sidea, 'l3' : 'sideanleggsdel'    }},   
                { 'navn' : 'fra_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'fra_meter'         }}, 
                { 'navn' : 'til_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'til_meter'         }}, 
                { 'navn' : 'trafikantgruppe' , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'trafikantgruppe'   }}, 
                { 'navn' : 'fra_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : kryss, 'l3' : 'fra_meter'         }}, 
                { 'navn' : 'til_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : kryss, 'l3' : 'til_meter'         }}, 
                { 'navn' : 'trafikantgruppe' , 'verdi' :  { 'l1' : vr, 'l2' : kryss, 'l3' : 'trafikantgruppe'   }}, 
                { 'navn' : 'fra_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : sidea, 'l3' : 'fra_meter'         }}, 
                { 'navn' : 'til_meter'       , 'verdi' :  { 'l1' : vr, 'l2' : sidea, 'l3' : 'til_meter'         }}, 
                { 'navn' : 'trafikantgruppe' , 'verdi' :  { 'l1' : vr, 'l2' : sidea, 'l3' : 'trafikantgruppe'   }}, 
                { 'navn' : 'adskilte_lop'    , 'verdi' :  { 'l1' : vr, 'l2' : strek, 'l3' : 'adskilte_løp'      }}
                ]

    for mykey in struktur: 
        try: 
            v1[mykey['navn']] = v1[mykey['verdi']['l1']][mykey['verdi']['l2']][mykey['verdi']['l3']]
        except KeyError: 
            pass 
    
    if droppKontrakter: 
        v1.pop( 'kontraktsområder', None)
    if droppRiksvegruter: 
        v1.pop( 'riksvegruter', None)    

    return v1 

def egenskaper2records( egenskaper, relasjoner=False, geometri=False, geometrikvalitet=False ):
    """
    Oversetter liste med egenskapverdier til dictionary med struktur 
        "egenskapnavn" : Verdi

    Relasjoner til andre NVDB-objekt er en egenskap, det også - men i mange
    sammenghenger er du ikke så veldig interessert i disse. egenskaper=False 
    filtrerer vekk relasjonene. 

    Geometri-egenskap(er), såkalt egengeometri, er også av variabel interesse. 
    geometri=True tar med egengeometri-egenskapene. 

    NB! Hopper over egenskaper av typen Liste og Struktur

    ARGUMENTS
        egenskaper: Liste med egenskapverdier, hentet fra NVDB api LES

    KEYWORDS
        relasjoner : False, sett til True hvis du ønsker å ha med relasjoner

        geometri:    False, sett til True hvis du ønsker å ha med objektets egengeometri-egenskap

        geometrikvalitet : False, sett til True hvis du ønsker å ha med kvalitetsparametre (metadata) for objektets egengeometri-egnskap  
                                 Forutsetter at du også har valgt geometri=True 

    RETURNS 
        dictionary med egenskapsnavn og verdier 
    """
    data = {}

    for eg in egenskaper: 
        if eg['id'] < 100000 and not eg['egenskapstype'].lower() in ['struktur', 'liste']: 

            if eg['navn'] == 'Vedlegg':
                vedleggnavn = eg['navn']
                count = 0 
                # Legger til rette for at vi kan ha en liste med vedlegg (vedlegg1, vedlegg2, ...)
                # Bør testes før vi stoler 100% på denne funksjonen, gjetter
                # litt i blinde her. 
                while vedleggnavn in data.keys():
                    count += 1
                    vedleggnavn = eg['navn'] + str( count )
                    print( "Flere vedlegg (eksperimentelt!", vedleggnavn)
                    print( json.dumps( eg, indent=4 ))

                if 'href' in eg: 
                    data[vedleggnavn] = eg['href']
                else: 
                    print( 'Primitiv vedleggshåndtering, denne skjønte jeg ikke:')
                    print( json.dumps( eg, indent=4 ))

            # Skal vi ignorere geometri-egenskaper? I så fall er nøkkelord geometri==False, og vi 
            # hopper over de egenskapene som sier noe om egengeometri.  
            elif geometri or not 'geometri' in eg['navn'].lower(): 
                if 'egenskapstype' in eg.keys() and eg['egenskapstype'] == 'Binær' and 'href' in eg.keys(): 
                    data[eg['navn']] = eg['href']
                else: 
                    try: 
                        data[eg['navn']] = eg['verdi']
                    except KeyError:
                        print( 'Fant ingen verdi i denne egenskapen, ignorerer:\n', json.dumps( eg, indent=4) )
                        # TODO må kanskje gå gjennom alle egenskaptype-varianter mer i detalj og eksplisitt? 

                    else: 
                        # Føyer på kvalitetsparametre geometri (hvis vi er bedt om det, og hvis den finnes)
                        if geometrikvalitet and 'geometri' in eg['navn'].lower() and 'kvalitet' in eg.keys(): 
                            data[eg['navn']+'_kvalitet'] = eg['kvalitet']

    if relasjoner: 
        warn( 'Uthenting av relasjoner fra egenskapverdier er ikke implementert (ennå). Bruk to_records() eller nvdbfagdata2records()')

    return data 
            
def merge_dicts(*dict_args):
    """
    Python < 3.5 kompatibel kode for å slå sammen to eller flere dict. 
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    Sakset fra http://stackoverflow.com/questions/38987/
        how-can-i-merge-two-python-dictionaries-in-a-single-expression
    """
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def esriSikkerTekst( mintekst): 
    """
    Fjerner kjipe tegn fra tekststreng. Står igjen med kun bokstaver, tall og underscore

    Nyttig f.eks for å sikre at navn på kartlag og egenskaper ikke gir krøll i ulike kartsystem

    ARGUMENTS
        mintekst - tekststreng 

    KEYWORDS
        None
    
    RETURNS
        mintekst hvor skumle tegn (mellomrom, komma, skråstrek, bindestrek m.m.) er byttet ut med 
                underscore. 

    """

    # Bytter ut noen spesialtegn med underscore 
    mintekst = re.sub( ',', '_', mintekst)
    mintekst = re.sub( '/', '_', mintekst)
    mintekst = re.sub( ' ', '_', mintekst)
    mintekst = re.sub( '-', '_', mintekst)

    # Fjerner opphopning av underscores 
    mintekst = re.sub( '__', '_', mintekst)
    mintekst = re.sub( '__', '_', mintekst)
    mintekst = re.sub( '__', '_', mintekst)


    tt = [val for val in mintekst if val.isalpha() or val.isnumeric() or val == '_' ] 
    mintekst = ''.join( tt )

    return mintekst
