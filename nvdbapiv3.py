# -*- coding: utf-8 -*-

import six # python 2 vs 3 compability library
import json
import requests
from warnings import warn
import os
from copy import deepcopy
import apiforbindelse
#import pdb

# Uncomment to silent those unverified https-request warnings
requests.packages.urllib3.disable_warnings() 

"""Bibliotek for å hente data fra NVDB api V3 (og senere versjoner)
Har 2 klasser, nvdbVegnett og nvdbFagdata

UFERDIG, holder på å skrive om til V3... 
"""

class nvdbVegnett: 
    """Klasse for spørringer mot NVDB for å hente segmentert vegnett. 
    Jobber dynamisk mot NVDB api for å hente statistikk, laste ned data etc.
    Holder alle parametre som inngår i dialogen med NVDB api. 

    Grovt sett skal vi ha disse komponentene / funksjonene: 
        - Enkle metoder for å sette søkekriterier
        (geografisk filter) 
        
        - Smart utnyttelse av NVDB api'ets pagineringsfunksjon. 
            - Liste med objekter man kan iterere over
            - Hent neste "batch" med objekter 
            - Hent hvert enkelt objekt

    n = nvdbVegnett() 
    v = n.nesteForekomst()
    while v: 
        print v['id']  # Gjør noe spennende
        v = n.nesteForekomst()

    """
    
    
    def __init__( self, miljo=None):
        
        
        self.geofilter = {}
        self.headers =   { 'accept' : 'application/vnd.vegvesen.nvdb-v3-rev1+json', 
                            'X-Client' : 'nvdbapi.py',
                            'X-Kontaktperson' : 'jan.kristian.jensen@vegvesen.no'}
                            
        self.update_http_header()
                            
        
        self.paginering = { 'antall'         : 1000,     # Hvor mange obj vi henter samtidig.
                                
                                'hvilken'       : 0,    # iterasjon 
                                                        # i det lokale datasettet 
                                                        # Dvs i+1 til 
                                                        # array self.data['objekter'] 
                                                        # 
                                'meredata'      : True, # Gjetning på om vi kan hente mere data
                                'initielt'      : True,  # Initiell ladning av datasett
                                'dummy'         : False # Jukse-bruk av paginering 
                    } 
        
        # Standardverdier for responsen, og holder evt tilleggsparametre
        # Initielt tom for vegnett, men langt fagdata
        self.respons  = { }
        
        self.data = { 'objekter' : []}
        self.forbindelse = apiforbindelse.apiforbindelse()
        if not miljo:
            miljo = 'prod'
        self.miljo( miljo)


    def nestePaginering(self):
        """ = True | False. Blar videre til neste oppslag (side) i pagineringen.
        Nyttig for dem som selv vil kopiere / iterere over listen av objekter, 
        som holdes i attributten nvdbFagdata.data 
        Returnerer True eller False
        
        Eksempel
            n = nvdbFagdata( 45) # bomstasjon
            suksess = n.nestePaginering()
            while suksess: 
                mycopy = n.data['objekter']
                for bomst in mycopy:
                    print bomst['id'] # Gjør noe spennende. 
                suksess = n.nestePaginering()
        """
        if isinstance( self, nvdbFagdata) and not self.objektTypeId: 
            raise ValueError( '\n'.join(('ObjektTypeID mangler.',  
                                    '\tEks: N = nvdbFagData(45)', 
                                    '\teller: N = nvdbFagData()',
                                    '       N.objektType(45)')))
        if isinstance( self, nvdbFagdata) and not self.antall: 
           self.statistikk()
        
        if self.paginering['initielt']: 
        
            if isinstance( self, nvdbFagdata): 
                parametre = merge_dicts(    self.geofilter, 
                                            self.overlappfilter, 
                                            self.egenskapsfilter, 
                                            self.respons, 
                        { 'antall' :  self.paginering['antall'] } )
                self.data = self.anrope( '/'.join(('vegobjekter', str(self.objektTypeId) )), 
                    parametre=parametre ) 
                    
            elif isinstance( self, nvdbVegnett): 
                parametre = merge_dicts( self.geofilter, 
                        { 'antall' : self.paginering['antall'] } )
                self.data = self.anrope( 'vegnett/veglenkesekvenser/segmentert', parametre=parametre )

            self.paginering['initielt'] = False

            if self.data['metadata']['antall'] > 0: 
                return True
            else: 
                self.paginering['meredata'] = False
                return False
                
        elif self.paginering['meredata']:
            self.data = self.anrope( self.data['metadata']['neste']['href'] ) 
            
            if self.data['metadata']['returnert'] > 0: 
                return True
            else: 
                self.paginering['meredata'] = False
                return False
        
        else: 
            return False
        
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
        if debug: 
            print( "Paginering?", self.paginering) 
            
        if self.paginering['dummy']:
            # Noen har faket et søkeobjekt og dytta inn data der...
            if self.paginering['hvilken'] < len( self.data['objekter']): 
                self.paginering['hvilken'] += 1
                return self.data['objekter'][self.paginering['hvilken']-1]
            else: 
                return None
             
        elif self.paginering['initielt']: 
        
            if isinstance( self, nvdbFagdata): 
                parametre = merge_dicts(    self.geofilter, 
                                            self.overlappfilter, 
                                            self.egenskapsfilter, 
                                            self.respons, 
                        { 'antall' :  self.paginering['antall'] } )
                self.data = self.anrope( '/'.join(('vegobjekter', str(self.objektTypeId) )), 
                    parametre=parametre ) 
                    
            elif isinstance( self, nvdbVegnett): 
                parametre = merge_dicts( self.geofilter, 
                        { 'antall' : self.paginering['antall'] } )
                self.data = self.anrope( 'vegnett/veglenkesekvenser/segmentert', parametre=parametre )

            self.paginering['initielt'] = False

            if self.data['metadata']['returnert'] > 0: 
                self.paginering['hvilken'] = 1
                return self.data['objekter'][0]
            else: 
                self.paginering['meredata'] = False
                return None
                
        elif self.paginering['meredata'] and self.paginering['hvilken'] > antObjLokalt-1: 
            self.data = self.anrope( self.data['metadata']['neste']['href'] ) 
            self.paginering['hvilken'] = 1
            
            if self.data['metadata']['returnert'] > 0: 
                return self.data['objekter'][0]
            else: 
                self.paginering['meredata'] = False
                return None
        
        elif self.paginering['meredata']: 
        
            self.paginering['hvilken'] += 1
            return self.data['objekter'][self.paginering['hvilken']-1]

        
    def addfilter_geo(self, *arg):
        """Get or set GEO filters to your search. 
        Input argument is a dict with area- or road network filter, which are 
        appended to existing values. 

        
        See 
        https://www.vegvesen.no/nvdb/apidokumentasjon/#/parameter/lokasjonsfilter 
        for a list of possible values. 
        
        Example 
        p = nvdb.nvdbFagdata(809)
        p.addfilter_geo( { 'vegreferanse' : 'Ev39' }
        p.addfilter_geo( { 'fylke' : [3,4] }
        p.addfilter_geo() # Returns the current value of this filter 
        
        addfilter_geo with no arguments returns the current filter. 
        
        Input empty dict {} or string to clear all GEO - filters
        
        """ 
        
        if len( arg) == 1: 
            if isinstance( arg[0], dict) and arg[0]: 
                self.geofilter.update( arg[0]) 
            elif isinstance( arg[0], dict) and not arg[0]: 
                self.geofilter = {} 
            elif isinstance( arg[0], str): 
                self.geofilter = {} 

            else:
                warn('Wrong input to addfilter_geo. Should be dict') 
        else:
            return self.geofilter

    def add_request_arguments( self, parameters): 
        """Appends (or updates) key-value parameters to the data retrieval request
        Input argument is a dict. 
        This modifies the response 
        
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
    

    def anrope(self, path, parametre=None, debug=False, silent=False, logganrop=False): 
    
        logganrop = False # Logger alle anrop til fil
    
        if not self.apiurl in path: 
            url = ''.join(( self.apiurl, path)) 
        else: 
            url = path 

        # r = requests.get(url, params=parametre, headers=self.headers)
        r = self.forbindelse.les( url, params=parametre, headers=self.headers )
        
        self.sisteanrop = r.url
        
        if debug:
            print( r.url[33:]) # DEBUG
        
        if r.status_code == requests.codes.ok:
            data = r.json()
            if debug and 'metadata' in data.keys(): 
                print( '\n',  data['metadata'], '\n' ) 
                
            if logganrop: 
                loggfil = 'D:/Brukere/Jan/jobb/nvdbapi-V2/logganrop.txt'
                if not os.path.exists( loggfil): 
                    with open( loggfil, 'w' ) as f2: 
                        f2.write( 'Logger alle anrop mot NVDB api V2 fra nvdbapi.py\n' ) 
            
                with open(loggfil, 'a', encoding='utf-8' ) as f: 
                    f.write( '\n==========================\n' ) 
                    f.write( r.url ) 
                    f.write( '\n' ) 
                    f.write( json.dumps( data, indent=4, ensure_ascii=False) )
                    f.write( '\n' )  
                
            return r.json()
        
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
            warn( mytext ) 

    def miljo(self, *args):
        """Kun internt på vegvesen-nettet!
        Kan endre hvilket miljø vi går mot.
        Parametre: 
            ingen - skriver lenken til NVDB api
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
            
            if args[0].lower() == 'utv': 
                self.apiurl = 'https://nvdbapiles-v3.utv.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('utvles')
            elif args[0].lower() == 'test': 
                self.apiurl = 'https://nvdbapiles-v3.test.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('testles')
            elif args[0].lower() == 'prod': 
                self.apiurl = 'https://nvdbapiles-v3.atlas.vegvesen.no/'
                self.forbindelse.velgmiljo('prodles')
            else: 
                print( "Forstod ikke parameter:", args[0])
                print("Lovlige valg: utv, test eller prod")
        
        # if not silent: 
        # print( "Bruker ", self.apiurl)
     
            
class nvdbFagdata(nvdbVegnett): 
    """Klasse for spørringer mot NVDB ang en spesifikk objekttype. 
    Jobber dynamisk mot NVDB api for å hente statistikk, laste ned data etc.
    Holder alle parametre som inngår i dialogen med NVDB api. 

    Grovt sett skal vi ha disse komponentene / funksjonene: 
        - Enkle metoder for å sette søkekriterier
        (geografisk filter, egenskapsfilter m.m.) 

        - Enkle metoder for å hente, lagre og inspisere alle NVDB fagdata
        som tilfreddstiller søkekriteriene. 
        
        - Smart utnyttelse av NVDB api'ets pagineringsfunksjon. 
            - Liste med objekter man kan iterere over
            - Hent neste "batch" med objekter 
            - Hent hvert enkelt objekt

        - Statistikk for dette søket  

    n = nvdb() # Tomt objekt, klart til å få verdi
    n = nvdb(45) # Objekttypen er nå satt lik 45 (Bomstasjon) 
    n.addfilter_egenskap( '1820>=20') 
    
    # EKSEMPEL: Iterer over alle bomstasjoner
    n = nvdbFagdata(45) 
    bomst = n.nesteForekomst()
    while bomst: 
        print bomst['id']  # Gjør noe spennende
        bomst = n.nesteForekomst()

    """
    
    
    
    def __init__( self, objTypeID, miljo=None):


        self.headers =   { 'accept' : 'application/vnd.vegvesen.nvdb-v3-rev1+json', 
                        'X-Client' : 'nvdbapi.py',
                        'X-Kontaktperson' : 'Anonymous'}
    
        self.paginering = { 'antall'         : 1000,     # Hvor mange obj vi henter samtidig.
                            
                            'hvilken'       : 0,    # iterasjon 
                                                    # i det lokale datasettet 
                                                    # Dvs i+1 til 
                                                    # array self.data['objekter'] 
                                                    # 
                            'meredata'      : True, # Gjetning på om vi kan hente mere data
                            'initielt'      : True, # Initiell ladning av datasett
                            'dummy'         : False # For jukse-bruk av søkeobjektet
                } 
    
        self.data = { 'objekter' : []}
        self.apiurl = 'https://www.vegvesen.no/nvdb/api/v3/'

        self.objektTypeId = None
        self.objektTypeDef = None
        self.antall = None
        self.strekningslengde = None
        self.geofilter = {}
        self.egenskapsfilter = {}
        self.overlappfilter = {} 
        self.forbindelse = apiforbindelse.apiforbindelse()
        if not miljo: 
            miljo = 'prod'
        self.miljo( miljo)
        self.forbindelse.velgmiljo( 'prodles')

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

    def statistikk(self): 
        if self.objektTypeId: 
        
            parametre = deepcopy( self.allfilters() )
            
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


    def info(self): 
        if self.objektTypeId: 
            print( 'ObjektType:', 
                str(self.objektTypeId), self.objektTypeDef['navn'] )
    
        else: 
            print( 'Ikke definert noen objekttype ennå') 
            print( 'Bruk: x = nvdbFagdatID) eller\n', ' x = nvdbFagdata()\n', 
                    'x.objektType(ID)\n', 
                    'hvor ID er objekttypens ID, eks bomstasjon = 45\n\n') 
    
        print( 'Filtere')
        print( json.dumps( self.allfilters(), indent=4))
        print( 'Parametre som styrer responsen:' ) 
        print( json.dumps( self.respons, indent=4))
        print( 'Statistikk') 
        print( json.dumps( self.statistikk(), indent = 4))


    def egenskaper(self, *arg):
        """Skriver ut definisjonen av angitt egenskapstype (ID, heltall). 
        Hvis ingen ID oppgis skriver vi ut en liste med ID, navn og type
        for alle egenskapstyper for denne objekttypen. 
        """

        if len(arg) == 0: 
            for eg in self.objektTypeDef['egenskapstyper']:
                print( eg['id'], eg['navn'], eg['datatype_tekst'] )
                
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
        
        
    def allfilters( self): 
        """Returns a dict with all current filters""" 
        return merge_dicts( self.geofilter, self.egenskapsfilter, 
                        self.overlappfilter) 
        
    def addfilter_overlapp( self, *arg): 
        """Get or set overlapp filters to your search. 
        Input argument is a text string with overlapp ilters, which is added to 
        existing filter. 
        NB! If you want to add to an EXISTING filter, care must be taken to 
        construct valid expressions using AND, OR and (if needed) parantheses. 

        
        See 
        https://www.vegvesen.no/nvdb/apidokumentasjon/#/parameter/overlappfilter
        for explanation. 
        
        Example 
        p = nvdb.nvdbFagdata(570) # Trafikkulykke
        p.addfilter_overlapp( '67'  ) # Trafikkulykke in tunnels (tunnelløp)
        p.addfilter_overlapp( '105(2021=2738)'  ) # Ulykke where speed limit =80
        
        p.addfilter_overlapp( '' ) # Clears all values
        
        addfilter_overlapp with no arguments returns the current filter. 
        
        Input empty string to clear the filter
        
        """ 
        
        
        if len( arg) == 1 and arg[0]: 
            self.overlappfilter.update( { 'overlapp' : arg[0] } ) 
        elif len(arg) == 1 and not arg[0]: 
            self.overlappfilter = {} 
        else:
            return self.overlappfilter

        
    def addfilter_egenskap( self, *arg): 
        """Get or set property filters (egenskapsfilter) to your search. 
        Input argument is a text string with property filters, which is added to 
        existing filter. 
        NB! If you want to add to an EXISTING filter, care must be taken to 
        construct valid expressions using AND, OR and (if needed) parantheses. 

        
        See 
        https://www.vegvesen.no/nvdb/apidokumentasjon/#/parameter/egenskapsfilter
        for explanation. 
        
        Example 
        p = nvdb.nvdbFagdata(45)
        p.addfilter_egenskap( '1820=20'  ) # takst = 20 kr
        p.addfilter_egenskap( 'OR 1820=50'  ) # is now "1820=20 OR 1820=50"
        
        p.addfilter_egenskap( '' ) # Clears all values
        
        addfilter_egenskap with no arguments returns the current filter. 
        
        Input empty string to clear the filter
        
        """ 
        
        
        if len( arg) == 1 and arg[0]: 
            self.egenskapsfilter.update( { 'egenskap' : arg[0] } ) 
            
            # Warning users about a bug in NVDB api
            if '*' in arg[0]:
                warn( "Warning - \nbug in NVDB api for wildcard (*) text" + \
                        "matching.\n" +  
                        "You'll probably find ZERO features with this filter") 
            
        elif len(arg) == 1 and not arg[0]: 
            self.egenskapsfilter = {} 
        else:
            return self.egenskapsfilter

    def nesteNvdbFagObjekt( self ): 
        fagdata = self.nesteForekomst()
        if fagdata: 
            fagobj = nvdbFagObjekt(fagdata)
            return( fagobj)
        else: 
            return None
        
    def to_records(self, vegsegmenter=True, relasjoner=False, geometri=False, debug=False ): 
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

        NB! Når vi returnerer individuelle vegsegmenter tar vi med vegsegmenter gyldige i dag,
        dvs åpen sluttdato.

        Paramter relasjoner=False: Tar ikke med liste over relasjoner til andre objekter

        Parameter geometri=False: Tar ikke med s.k. egengeometri(er)

        """

        mydata = []
        if not self.antall: 
            self.statistikk()

        if self.antall and self.antall > 10000: 
            print( 'Eksport av', self.antall, 'objekter kommer til å ta tid...')

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
            if 'geometri' in feat.keys():

                meta = { }
                
                meta['objekttype']  = feat['metadata']['type']['id']
                meta['nvdbId'] = feat['id']
                meta['versjon'] = feat['metadata']['versjon']
                # meta['metadata'] = feat['metadata']

                egenskaper = egenskaper2records( feat['egenskaper'], relasjoner=relasjoner, geometri=geometri )
                egenskaper = merge_dicts( meta, egenskaper)

                if vegsegmenter: 
                    for seg in feat['vegsegmenter']:
                        if not 'sluttdato' in seg.keys():
                            s2 = {  'veglenkesekvensid' : seg['veglenkesekvensid'], 
                                    'startposisjon'     : seg['startposisjon'], 
                                    'sluttposisjon'     : seg['sluttposisjon'], 
                                    'lengde'            : seg['lengde'],
                                    'detaljnivå'        : seg['detaljnivå'],
                                    'typeVeg'           : seg['typeVeg'],
                                    'kommune'           : seg['kommune'], 
                                    'fylke'             : seg['fylke'],
                                    'vref'              : seg['vegsystemreferanse']['kortform']   }

                            delkeys = [ 'strekning', 'kryssdel', 'sideanlegg']
                            for hvaslag in delkeys: 
                                if  hvaslag in seg['vegsystemreferanse'].keys(): 
                                    s2['trafikantgruppe'] = seg['vegsystemreferanse'][hvaslag]['trafikantgruppe']
                                
                            s2['geometri'] = seg['geometri']['wkt']
                            egenskaper_kopi = deepcopy( egenskaper )
                            egenskaper_kopi = merge_dicts( egenskaper_kopi, s2)
                            mydata.append( egenskaper_kopi )
                else: 
                    egenskaper['vegsystemreferanser'] = ','.join([ d['kortform'] for d in feat['lokasjon']['vegsystemreferanser'] ] )
                    egenskaper['stedfestinger']       = ','.join([ d['kortform'] for d in feat['lokasjon']['stedfestinger'] ] )
                    egenskaper['vegsegmenter']        = feat['vegsegmenter']
                    if 'geometri' in feat.keys():
                        egenskaper['geometri']  = feat['geometri']['wkt']
                    egenskaper['lengde'] = feat['lokasjon']['lengde']
                    mydata.append( egenskaper )

            else: 
                nvdbid_manglergeom.append( feat['id'])

            feat = self.nesteForekomst()

        if len( nvdbid_manglergeom ) > 0: 
            print( 'Manglende geometri-element for', len( nvdbid_manglergeom), 'vegobjekter fra dette søket')
            print( json.dumps( self.allfilters(), indent=4)  )
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
        """ 
        egenskap = self.egenskap( id_or_navn, empty=empty)
        if egenskap and egenskap != empty: 
            return egenskap['verdi']
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
        if isinstance( relasjon, six.string_types) and relasjon.isdigit():
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
            
        elif isinstance( relasjon, six.string_types):
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
            
            
def finnid(objektid, kunvegnett=False, kunfagdata=False, miljo=False): 
    """Henter NVDB objekt (enten veglenke eller fagdata) ut fra objektID.
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

def egenskaper2records( egenskaper, relasjoner=False, geometri=False ):
    """
    Oversetter liste med egenskapverdier til dictionary med struktur 
        "egenskapnavn" : Verdi

    Relasjoner til andre NVDB-objekt er en egenskap, det også - men i mange
    sammenghenger er du ikke så veldig interessert i disse. egenskaper=False 
    filtrerer vekk relasjonene. 

    Geometri-egenskap(er), såkalt egengeometri, er også av variabel interesse. 
    geometri=True tar med egengeometri-egenskapene. 
    """
    data = {}

    for eg in egenskaper: 
        if eg['id'] < 100000 or relasjoner: 

            if geometri or not 'geometri' in eg['navn'].lower(): 
                data[eg['navn']] = eg['verdi']
        

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
