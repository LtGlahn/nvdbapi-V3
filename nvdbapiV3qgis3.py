"""
Klasser og funksjoner for å føye NVDB vegnett og fagdata til QGIS 3


"""
from qgis.core import QgsProject,  QgsVectorLayer, QgsFeature, QgsGeometry, QgsPoint, QgsLineString
from nvdbapiv3 import nvdbVegnett, nvdbFagdata, nvdbFagObjekt, finnid
from copy import deepcopy
import pdb


class memlayerwrap(): 
    """
    Wrapper rundt QGIS memorylayer. Blir først synlig i QGIS når du føyer til features. 
    
    Tanken er å ha en smidig håndtering av all den mangfoldighet av geometrityper du finner i NVDB. 
    Et NVDB-objekt kan være POINT, LINESTRING, MULTILINESTRING eller POLYGON (og kanskje litt mer). 
	Og data kan være en blanding av 2D og 3D koordinater. Og du vet aldri hva du får før du leser inn data.
    
    Derfor oppretter midlertidig en gjeng med tomme lag, en per aktuell geometritype og 2D/3D. 
	Data føyes til riktig lag. Etterpå legger vi ikke-tomme lag til QGIS kartet. 
    """
    def __init__(self, geomtype, egenskapdef, navn) : 
        self.active = False
        self.geomtype = geomtype
        self.layer = QgsVectorLayer(geomtype + '?crs=epsg:25833&index=yes&' + egenskapdef, navn, 'memory')
        
    def addFeature(self, egenskaper, qgisgeom):
        if not self.active:
            QgsProject.instance().addMapLayer(self.layer)
            self.layer.startEditing() 
            self.active = True 
        
        feat = QgsFeature()    
        feat.setAttributes( egenskaper )        
        feat.setGeometry( qgisgeom )
            
        success = self.layer.addFeature( feat )
        if not success: 
            print( "Klarte ikke føye til feature") 
            print( 'egenskaper:', egenskaper ) 
            print( 'geometri', qgisgeom ) 
        
        
        return( success ) 
        
    def ferdig( self): 
        if self.active: 
            self.layer.updateExtents() 
            self.layer.commitChanges()
            self.active = False
        
        
def lagQgisDakat(  sokeobjekt):
    """
    Lager attributt-definisjon for QGIS objekter ihht datakatalogen
    
    
    
    TODO: 
        DOKUMENTASJON
        fraDato, sistmodifisert skal være QGIS datoer, ikke tekst
        Behov for å fjerne visse tegn fra egenskapsnavn som QGIS bruker?
            f.eks &, : ?             
    
    """
    # Liste med ID'er for egenskapstypene for denne objekttypen  
    egIds = [] 
    # Liste med QGIS datatyper. Kort liste med metadata først, deretter matcher listen med egenskapstyper. 
    qgisEg = ['field=nvdbid:int', 'versjon:int', 'fraDato:string', 'sistmodifisert:string' ]

    for eg in sokeobjekt.objektTypeDef['egenskapstyper']: 
        egIds.append( eg['id'] ) 
        qgisEg.append( egenskaptype2qgis( eg) ) 
        
    # Føyer på placeholder for vegsystemreferanse: 
    qgisEg.append( 'vegsystemreferanse:string')

    # Føyer på placeholder for stedfesting
    qgisEg.append( 'stedfesting:string')


    qgisDakat = '&field='.join( qgisEg )
    
    return egIds, qgisEg, qgisDakat
        
def egenskaptype2qgis( egenskaptype): 
    """
    Omsetter en enkelt NVDB datakatalog egenskapdefinisjon til QGIS lagdefinisjon-streng

    Kan raffineres til flere datatyper. Noen aktuelle varianter
    
    #Tekst - Eksempel: Strindheimtunnelen
    #Tall - Eksempel: 86
    #Flyttall - Eksempel: 86.0
    #Kortdato - Eksempel: Måned-dag, 01-01
    #Dato - Eksempel: År-Måned-dag, 2015-01-01
    #Klokkeslett - Eksempel: 13:37
    #Geometri - Geometrirepresentasjon
    #Struktur - Verdi sammensatt av flere verdier
    #Binærobjekt - Eksempel: Et dokument eller et bilde
    #Boolean - True eller false
    #Liste - En liste av objekter

    """
    defstring = egenskaptype['navn']
    if 'Tall' in egenskaptype['egenskapstype']:
        if 'desimaler' in egenskaptype.keys() and egenskaptype['desimaler'] > 0:  
            defstring += ':double'
        else: 
            defstring += ':int' 
    elif 'Dato' == egenskaptype['egenskapstype']:
        defstring += ':date'  
    else: 
        defstring += ':string' 
    
    return defstring 
    
    
def nvdbFeat2qgisProperties( mittobj, egIds): 
    """
    Omsetter egenskapsverdiene pluss utvalgte metadata fra et 
    NVDB fagobjekt til en liste med QGIS verdier. 
    """ 
    qgisprops = [ mittobj.id, mittobj.metadata['versjon'], 
                 mittobj.metadata['startdato'] ] 
                 
    if 'sist_modifisert' in mittobj.metadata:
        qgisprops.append( mittobj.metadata['sist_modifisert'] )
    else: 
        qgisprops.append( mittobj.metadata['startdato'] + 'T00:00:00' ) 
    
    for eg in egIds: 
        
        qgisprops.append( mittobj.egenskapverdi(eg))
    
    return qgisprops


def nvdb2kart( nvdbref, iface, kunfagdata=True, kunvegnett=False, 
            miljo='prod',lagnavn=None, **kwargs):
    """
    Legger noe fra NVDB til kartflaten. Dette kan være en ID 
    til nvdb veglenke(r) eller  fagobjekt, eller et søkeobjekt 
    (nvdbFagdata eller nvdbVegnett). Et søkeobjekt vil bli avgrenset
    til QGIS kartflate. (Hvis dette ikke er ønsket - send direkte 
    til funksjonen nvdb2qgis) 
    
    Nøkkelordene kunfagdata, kunvegnett og miljø sendes til funksjonen
    nvdbapi.finnid.
    
    Resten av nøkkeordene sendes til funksjonen nvdbsok2qgis, og er 
    dokumentert der. 
    """

    # Konverterer string => int
    if isinstance(nvdbref, str): 
        try: 
            nvdbref = int(nvdbref) 
        except ValueError: 
            pass
            
    
    
    if (isinstance( nvdbref, nvdbFagdata) or \
                                    isinstance( nvdbref, nvdbVegnett)): 
             
        ext = iface.mapCanvas().extent()

        kartutsnitt = str(ext.xMinimum()) + ',' + \
            str(ext.yMinimum()) + ',' + str(ext.xMaximum()) + \
            ',' + str(ext.yMaximum()) 
        nvdbref.filter( { 'kartutsnitt' : kartutsnitt }) 
        
        nvdbsok2qgis( nvdbref, **kwargs )
        
    elif isinstance( nvdbref, int): 
        
        fag = finnid( nvdbref, kunfagdata=kunfagdata, 
            kunvegnett=kunvegnett, miljo=miljo)  
        
        if fag: 
            if isinstance( fag, dict) and 'id' in fag.keys():
                sokeobj = nvdbFagdata( fag['metadata']['type']['id'] ) 
                sokeobj.data['objekter'].append( fag) 
                sokeobj.antall = 1
                
                if not lagnavn: 
                    lagnavn = str(fag['metadata']['type']['id']) + \
                                '_' + str( nvdbref) 
            
            elif isinstance( fag, list) and len(fag) > 0 and \
            isinstance( fag[0], dict) and 'veglenkesekvensid' in fag[0].keys():
                
                sokeobj = nvdbVegnett()
                sokeobj.data['objekter'] = fag
                sokeobj.antall = len( fag) 
 
                lagnavn = 'veglenke_' + str( nvdbref) 
 
            else: 
                print( "fant ingen data???", str(nvdbref) )
                print( fag )
                return
            
            sokeobj.paginering['dummy'] = True
            sokeobj.paginering['hvilken'] = 0
            
            # Sender til kartet
            nvdbsok2qgis( sokeobj, lagnavn=lagnavn, **kwargs)  
        
    else: 
        print( "kjente ikke igjen", nvdbref, 
                        "som NVDB referanse eller søkeobjekt") 
        


def nvdbsok2qgis( sokeobjekt, lagnavn=None, 
            geometritype='beste', inkludervegnett='beste', debug=False): 
    """   
    Vil ta et søkeobjekt fra  nvdbapi-v2 biblioteket (nvdbFagdata eller 
    nvdbVegnett) og hente tilhørende data fra NVDB-api V2. 
        
    Arguments: 
        sokeobjekt: Søkeobjekt fra nvdbapi.nvdbVegnett eller
                                                    nvdbapi.nvdbFagdata

    Keywords: 
        lagnavn=None Navn på kartlagetlaget 
            (default: "Vegnett" eller objekttypenavn )
        
        kartflate=True | False Bruk QGis kartflate som boundingBox for 
            å avgrense søket geografisk DERSOM søket ikke allerede er
            avgrenset på et område (fylke, kommune, kontraktsområde, 
            region) 
            NB! Hvis søkeobjektet allere er avgrenset til et område 
            (fylke, kommune, riksvegrute, kontraktsområde) så vil kartflaten ha 
            null betydning. 
        
        geometritype=None eller en av ['egen', 'vegnett', 'flate', 'linje',  
                                                    'punkt', 'alle', 'vegkart' ]
            Detaljstyring av hvilken egeongeometri-variant som 
            foretrekkes. Defaultverdien None returnerer den mest 
            "verdifulle" geometritypen som finnes
            etter den samme prioriteringen som Vegkart-visningen: 
                1. Egengeometri, flate
                2. Egengeometri, linje
                3. Egengeometri, punkt
                4. Vegnettgeometri
            'alle' betyr at vi viser ALLE egengeometriene til objektet 
            pluss vegnettsgeometri (hvis da ikke dette overstyres med 
            valget inkludervegnett='aldri')

            valget 'vegkart' betyr at vi benytter data fra objektets "geometri"-element, 
            dvs samme visning som Vegkart. Logikken med prioritering av geometrityper i rekkefølgen 
            egengeometri, flate,  -linje, -punkt og vegnettgeometri er den samme. Forskjellen er at 
            abstrakte strekningsobjekt (fartsgrense, bruksklasse) ofte vil ha en blanding av multi- og 
            single linestring. Dette blir to separate lag i QGIS-kartflaten. Fordelen er at et objekt 
            vil ha en og kun en geometrirepresentasjon. Alternativet 'beste' eller 'vegnett' vil representere
            NVDB-objektet som et eller mange geografiske features i kartflaten, alt ettersom hvor mange 
            vegsegmenter objekter er fordelt over.  
                
        inkludervegnett='beste' | 'alltid' | 'aldri' | 'multi' 
            Default='beste' betyr at vi kun viser vegnettsgeometri hvis det
                    ikke finnes egengeometri. 
                    (Tilsvarer geometritype="beste") 
            'alltid' :  Vis ALLTID vegnettsgeometri i tillegg til 
                        evt egeomgeometri(er) 
            'aldri'  :  Vis aldri vegnettsgeometri 
                        dette betyr at objektet kun vises hvis det 
                        har egengeometri
 
        Noen av nøkkelordkombinasjonene kan altså 
        gi 0, 1 eller mange  visninger av samme objekt. Det vil si at 
        samme objekt blir til 0, 1, eller flere forekomster i Qgis.
         
        Et objekt sine geometri-representasjoner kan også havne i ulike 
        tabeller: Vi kan ikke blande f.eks. 2D og 3D, eller punkt, linje
        og flate i samme Qgis tabell (jeg har iallfall ikke funnet 
        ut hvordan). 

    """ 
    
    # Kortform geometritype 
    gt = geometritype
    
    if debug: 
        print( "Her skal det debugges, ja")
    
    # Sjekker input data    
    gtyper = [ 'flate', 'linje', 'punkt', 'vegnett', 'alle', 'beste', 'vegkart' ]
    if gt and isinstance(gt, str ) and gt.lower() not in gtyper: 
        print( 'nvdb2kart: Ukjent geometritype angitt:', gt, 
            'skal være en av:', gtyper) 
        print( 'nvdb2kart: Setter geometritype=beste') 
        gt = 'beste'
    
    if isinstance( sokeobjekt, nvdbFagdata): 
        
        if debug: 
            print( 'nvdbFagdata, geometritype=', gt) 

        # Bruker datakatalog-navnet om ikke annet er angitt: 
        if not lagnavn: 
            lagnavn = sokeobjekt.objektTypeDef['navn']

        # Datakatalogdiefinisjon ihtt Qgis-terminologi 
        (egIds, qgisEg, qgisDakat ) = lagQgisDakat(sokeobjekt)
        
        punktlag = memlayerwrap( 'Pointz',           qgisDakat, str(lagnavn))
        punktlag2d = memlayerwrap( 'Point',           qgisDakat, str(lagnavn) +'_2d')
        multipunktlag = memlayerwrap( 'MultiPoint',           qgisDakat, str(lagnavn) + '_multi' )
        linjelag2d = memlayerwrap( 'Linestring', qgisDakat, str(lagnavn)+'_2d') 
        linjelag = memlayerwrap( 'Linestringz', qgisDakat, str(lagnavn)) 
        multilinjelag2d = memlayerwrap( 'MultiLinestring', qgisDakat, str(lagnavn) + '_multiline2d' ) 
        multilinjelag = memlayerwrap( 'MultiLinestringz', qgisDakat, str(lagnavn) + '_multiline' ) 
        flatelag = memlayerwrap( 'Polygon',         qgisDakat, str(lagnavn))         
        flatelag3d = memlayerwrap( 'Polygonz',         qgisDakat, str(lagnavn) + '_3d' )         
        multiflatelag = memlayerwrap( 'MultiPolygon',         qgisDakat, str(lagnavn) + '_multiPoly') 
        collectionlag = memlayerwrap( 'GeometryCollection',         qgisDakat, str(lagnavn) + '_geomcollection') 
    
        mittobj = sokeobjekt.nesteNvdbFagObjekt()
        count = 0 
        while mittobj: 
            count += 1
            if count % 500 == 0 or count in [1, 10, 20, 50, 100]: 
                print( 'Lagt til ', count, 'av', sokeobjekt.antall, 'nvdb objekt i kartlag', lagnavn) 

            segmentcount = 0 
            # Qgis attributter = utvalgte metadata + egenskapverdier etter datakatalogen 
            egenskaper = nvdbFeat2qgisProperties( mittobj, egIds ) 
            
            # Vi kan ha flere geometrivisninger samtidig. 
            # Løkke for å løpe gjennom dem. 
            # Brukes også for å få med alle individuelle vegsegmenter. 
            mygeoms = []

            # Flagg for å holde styr på hvordan det går med forsøk på å vise 
            # finne alle ønskede geometrivarianter
            beste_gt_suksess = False
            
            # Finner navn på geometri-egenskap. Gode gamle "Geometri, Flate" er ikke
            # enerådende og skuddsikker lenger... f.eks. har 943 "Geometri_flate" 
            flatenavn = 'Geometri, flate'
            linjenavn = 'Geometri, linje' 
            punktnavn = 'Geometri, punkt'
            
            for eg in mittobj.egenskaper: 
                if 'geometri' in eg['navn'].lower() and 'flate' in eg['navn'].lower():
                    flatenavn = eg['navn']
                if 'geometri' in eg['navn'].lower() and 'linje' in eg['navn'].lower():
                    linjenavn = eg['navn']
                if 'geometri' in eg['navn'].lower() and 'punkt' in eg['navn'].lower():
                    punktnavn = eg['navn']


            flategeom = mittobj.egenskapverdi( flatenavn)
            linjegeom = mittobj.egenskapverdi( linjenavn)
            punktgeom = mittobj.egenskapverdi( punktnavn)

            # Datastruktur (liste) for vegsystemreferanse og stedfesting
            vrefliste   = [ ]
            stedfesting = [ ]
            
                          
            if gt in [ 'alle', 'flate', 'beste' ]: 
                if flategeom: 
                    mygeoms.append( QgsGeometry.fromWkt(flategeom)) 
                    beste_gt_suksess = True

                if debug:
                    print( mittobj.id, "punkt", "\n\t", punktgeom, 
                            "\n\t", mygeoms[-1].asWkt()[0:100])
                
            if (gt == 'alle') or (gt == 'linje') or \
                        (gt ==  'beste' and not beste_gt_suksess): 
                if linjegeom: 
                    mygeoms.append(QgsGeometry.fromWkt(linjegeom)) 
                    beste_gt_suksess = True 

                if debug:
                    print( mittobj.id, "linje", "\n\t", punktgeom, 
                            "\n\t", mygeoms[-1].asWkt()[0:100])


            if (gt == 'alle') or (gt == 'punkt') or \
                        (gt == 'beste' and not beste_gt_suksess): 
                if punktgeom: 
                    mygeoms.append( QgsGeometry.fromWkt(punktgeom)) 
                    beste_gt_suksess = True
            
                if debug:
                    print( mittobj.id, "punkt", "\n\t", punktgeom, 
                            "\n\t", mygeoms[-1].asWkt()[0:100])

            if gt == 'vegkart': 
                mygeoms.append( QgsGeometry.fromWkt( mittobj.geometri['wkt'] ) )  
                beste_gt_suksess = True
            
            # Skal vi vise vegnettsgeometri? Itererer i så fall 
            # over alle vegnett-geometrier 
            if (gt == 'vegnett') or \
                    (inkludervegnett == 'alltid') or \
                    (gt == 'beste' and not beste_gt_suksess and \
                                        inkludervegnett != 'aldri'):  
                
                if debug: 
                    print( mittobj.id, "Henter vegnettsgeometri") 
                for segment in mittobj.vegsegmenter: 
                    # Tar kun med vegsegmenter gyldige i dag:
                    if 'geometri' in segment.keys() and not 'sluttdato' in segment.keys():
                        # TODO - legge inn historikkstøtte! 

                        mygeoms.append( QgsGeometry.fromWkt(
                                            segment['geometri']['wkt'] ))

                        if 'vegsystemreferanse' in segment.keys() and 'kortform' in segment['vegsystemreferanse'].keys(): 
                            vrefliste.append( segment['vegsystemreferanse']['kortform'])
                        else: 
                            vrefliste.append( 'MANGLER VEGSYSTEMREFERANSE')

                        stedfeststring = 'Mangler??'
                        if 'relativPosisjon' in segment.keys() and 'veglenkesekvensid' in segment.keys():
                            stedfeststring = str(  segment['relativPosisjon'] ) + '@' + str( segment['veglenkesekvensid'] )
                        elif 'startposisjon' in segment.keys() and 'sluttposisjon' in segment.keys() and 'veglenkesekvensid' in segment.keys():
                            stedfeststring =  str(  segment['startposisjon'] ) + '-' + str(  segment['sluttposisjon'] ) + '@' + str( segment['veglenkesekvensid'] )

                        stedfesting.append( stedfeststring )

            else: 
                # Føyer til vegsystem-referanse 
                allevref = ','.join( [ v['kortform'] for v in mittobj.lokasjon['vegsystemreferanser' ] if 'kortform' in v ] )
                if allevref: 
                    vrefliste.append( allevref )
                else: 
                    vrefliste.append( 'MANGLER vegsystemreferanse')

                # Føyer til stedfesting 
                stedfesting.append( 'Kun for vegsegmenter')

           # Advarsel 
            if len( mygeoms ) == 0:
               print( 'Fant ingen geometri nvdbId', mittobj.id, 
               'geometritype=', gt, 'inkludervegnett=', inkludervegnett) 
 
            # Legger alle geometri-representasjonene i Qgis kart
            for geomcount, mygeom in enumerate(mygeoms):                       
            
                allwkt = mygeom.asWkt().lower()
                mylist = allwkt.split()
                mywkt = mylist[0]
                if debug: 
                    print( "WKT med små bokstaver:",  mywkt) 

                segmentegenskaper = deepcopy( egenskaper ) 
                segmentegenskaper.append(  vrefliste[geomcount] )
                segmentegenskaper.append( stedfesting[geomcount] )

                if 'pointz' == mywkt: 
                    punktlag.addFeature( segmentegenskaper, mygeom )
                elif 'point' == mywkt: 
                    punktlag2d.addFeature( segmentegenskaper, mygeom )
                elif 'multipoint' == mywkt: 
                    multipunktlag.addFeature( segmentegenskaper, mygeom)            
                elif 'linestringz' == mywkt: 
                    linjelag.addFeature( segmentegenskaper, mygeom)
                elif 'linestring' == mywkt: 
                    linjelag2d.addFeature( segmentegenskaper, mygeom)
                elif 'multilinestringz' == mywkt: 
                    multilinjelag.addFeature( segmentegenskaper, mygeom)            
                elif 'multilinestring' == mywkt: 
                    multilinjelag2d.addFeature( segmentegenskaper, mygeom)            
                elif 'polygonz' == mywkt:
                    flatelag3d.addFeature( segmentegenskaper, mygeom) 
                elif 'polygon' == mywkt:
                    flatelag.addFeature( segmentegenskaper, mygeom) 
                elif 'multipolygon' == mywkt:
                    multiflatelag.addFeature( segmentegenskaper, mygeom) 
                elif 'featurecollection' == mywkt:
                    collectionlag.addFeature( segmentegenskaper, mygeom) 
                else:
                    print( mittobj.id, 'Ukjent geometritype:', mywkt)
                
            # Slutt while-løkke. Ferdig med ett objekt, henter det neste 
            mittobj = sokeobjekt.nesteNvdbFagObjekt()


        # Tomme lag forsvinner, resten havner i Qgis kartlagsliste og kart
        punktlag.ferdig()
        punktlag2d.ferdig()
        linjelag.ferdig()
        linjelag2d.ferdig()
        flatelag.ferdig()     
        flatelag3d.ferdig()     
        multipunktlag.ferdig()
        multilinjelag2d.ferdig()
        multilinjelag.ferdig()
        multiflatelag.ferdig()
        multilinjelag2d
        collectionlag.ferdig()

    ##################################################
    ### 
    ### NVDB Veglenkers
    ####
    elif isinstance( sokeobjekt, nvdbVegnett): 

        # Kaller kartlaget vegnett om ikke annet er angitt: 
        if not lagnavn: 
            lagnavn = 'Vegnett'
      

        # Egenskaper for vegnett
        egNavnDef = [   { "veglenkesekvensid" : 'int'},
                        { "startdato" : 'date' }, # Spesialbehandling, metadata-element
                        { "sluttdato" : 'date' }, # Spesialbehandling, metadata-elemept
                        { "kortform_lenkepos": "string" },
                        { "startposisjon" : 'double' },
                        { "sluttposisjon" : 'double' },
                        { "veglenkenummer": "int" },
                        { "segmentnummer": "int" },
                        { "startnode": "string" },
                        { "sluttnode": "string" },
                        { "referanse": "string" },
                        { "type": "string" },
                        { "detaljnivå": "string" },
                        { "typeVeg": "string" },
                        { "feltoversikt": "string" }, # NB! Spesialbehandling! Liste => tekst
                        { "kjøreretning": "string"},  # Utleder kjøreretning relativt til lenkeretning ut fra feltoversikt
                        { "lengde": "double" },
                        { "fylke": "int" },
                        { "kommune": "int" }
                    ]

        vegref_vegsystemDef = [   
                        { "vegrefkort": "string" }, # Spesialbehandling 
                        { "vegkategori": "string" }, 
                        { "fase": "string" }, 
                        { "nummer": "int" }
                    ]
 

        vegref_strekningDef = [   
                        { "trafikantgruppe": "string" }, 
                        { "strekning": "int" }, 
                        { "delstrekning": "int" }, 
                        { "arm": "string" }, # Spesialbehandling True / False
                        { "adskilte_løp": "string" }, 
                        { "fra_meter": "int" }, 
                        { "til_meter": "int" }, 
                        { "retning": "string" } 
                    ]


         
        # Konstruerer Qgis egenskapsdefinisjon 
        vegnettEgenskaper = ''
        for egliste in [ egNavnDef, vegref_vegsystemDef, vegref_strekningDef ]: 
            for egenskap in egliste: 
                myKey = list(egenskap.keys())[0]
                vegnettEgenskaper +=  '&field=' +                     \
                                        myKey +  ':' + str(egenskap[myKey])

        # Fjerner den første ampersanden 
        vegnettEgenskaper = vegnettEgenskaper[1:]
   
        # Lager arbeidslag 
        punktlag = memlayerwrap( 'Pointz',           
                            vegnettEgenskaper, str(lagnavn)+'_punkt')
        linjelag = memlayerwrap( 'Linestringz', 
                                        vegnettEgenskaper, str(lagnavn)) 
        linjelag2d = memlayerwrap( 'Linestring', 
                                vegnettEgenskaper, str(lagnavn) + '2d' ) 
        multilinjelag = memlayerwrap( 'MultiLinestringz', 
                            vegnettEgenskaper, str(lagnavn) + '_multi' ) 
        multilinjelag2d = memlayerwrap( 'MultiLinestring', 
                          vegnettEgenskaper, str(lagnavn) + '_multi2d' ) 
        collectionlag = memlayerwrap( 'GeometryCollection',   
                    vegnettEgenskaper, str(lagnavn) + '_geomcollection') 

        mittobj = sokeobjekt.nesteForekomst()
        count = 0 
        while mittobj: 
            count += 1
            if count % 500 == 0 or count in [1, 10, 20, 50, 100]: 
                print( 'Lagt til ', count,  
                            'veglenker i kartlag', lagnavn) 

            nycount = 0 
            # Legger til egenskapverdier fra den første listen: 
            egVerdier = []
            for egenskap in egNavnDef:
                egNavn = list( egenskap.keys())[0]
                if egNavn == 'kortform_veglenke': 
                    egVerdier.append( mittobj['vegsystemref']['kortform'] )
                elif egNavn == "startdato":
                    egVerdier.append( mittobj['metadata']['startdato'] )
                elif egNavn == "sluttdato" and 'sluttdato' in mittobj['metadata'].keys():
                    egVerdier.append( mittobj['metadata']['sluttdato'] )
                elif egNavn == "feltoversikt" and egNavn in mittobj.keys():
                    egVerdier.append( ', '.join(  mittobj['feltoversikt'] ) )
                elif egNavn in mittobj.keys(): 
                    egVerdier.append( mittobj[egNavn]) 
                else: 
                    egVerdier.append( None ) 
                                        
            # Legger til egenskapverdier fra vegsystem
            for egenskap in vegref_vegsystemDef: 
                egNavn = list( egenskap.keys())[0]
                if egNavn == 'vegrefkort' and 'vegsystemreferanse' in mittobj.keys() and  'kortform' in mittobj['vegsystemreferanse'].keys(): 
                    egVerdier.append( mittobj['vegsystemreferanse']['kortform']) 
                elif 'vegsystem' in mittobj['vegsystemreferanse'].keys() and egNavn in mittobj['vegsystemreferanse']['vegsystem'].keys(): 
                    egVerdier.append( mittobj['vegsystemreferanse']['vegsystem'][egNavn]) 
                else: 
                    egVerdier.append( None ) 

            # Legger til egenskapverdier fra vegsystemreferanse-strekning
            for egenskap in vegref_strekningDef: 
                egNavn = list( egenskap.keys())[0]
                if egNavn == 'arm' and 'strekning' in mittobj['vegsystemreferanse'] and 'arm' in mittobj['vegsystemreferanse']['strekning'].keys():
                    egVerdier.append( str( mittobj['vegsystemreferanse']['strekning']['arm'] ) )
                elif egNavn == 'arm' and 'kryssystem' in mittobj['vegsystemreferanse'].keys() and 'arm' in mittobj['vegsystemreferanse']['kryssystem'].keys(): 
                    egVerdier.append( str( mittobj['vegsystemreferanse']['kryssystem']['arm'] ) ) 
                elif egNavn == 'arm' and 'sideanlegg' in mittobj['vegsystemreferanse'].keys() and 'arm' in mittobj['vegsystemreferanse']['sideanlegg'].keys(): 
                    egVerdier.append( str(  mittobj['vegsystemreferanse']['sideanlegg']['arm'] ) ) 
                elif 'strekning' in mittobj['vegsystemreferanse'].keys() and egNavn in mittobj['vegsystemreferanse']['strekning'].keys(): 
                    egVerdier.append( mittobj['vegsystemreferanse']['strekning'][egNavn]) 
                elif 'kryssystem' in mittobj['vegsystemreferanse'].keys() and egNavn in mittobj['vegsystemreferanse']['kryssystem'].keys(): 
                    egVerdier.append( mittobj['vegsystemreferanse']['kryssystem'][egNavn]) 
                elif 'sideanlegg' in mittobj['vegsystemreferanse'].keys() and egNavn in mittobj['vegsystemreferanse']['sideanlegg'].keys(): 
                    egVerdier.append( mittobj['vegsystemreferanse']['sideanlegg'][egNavn]) 
                else: 
                    egVerdier.append( None ) 

            # Geometri
            mygeom = QgsGeometry.fromWkt( mittobj['geometri']['wkt'])
            mywkt = mygeom.asWkt().lower()
            
            if 'pointz' in mywkt: 
                punktlag.addFeature( egVerdier, mygeom )
            elif 'linestringz' in mywkt: 
                linjelag.addFeature( egVerdier, mygeom)
            elif 'linestring' in mywkt: 
                linjelag2d.addFeature( egVerdier, mygeom)
            elif 'multilinestringz' in mywkt: 
                multilinjelag.addFeature( egVerdier, mygeom)            
            elif 'multilinestring' in mywkt: 
                multilinjelag2d.addFeature( egVerdier, mygeom)            
            elif 'featurecollection' in mywkt:
                collectionlag.addFeature( egVerdier, mygeom) 
            else:
                print( mittobj['kortform'], 'Ukjent geometritype:', mywkt)

            # Ferdig med ett veglenke-objekt, klart for det neste
            mittobj = sokeobjekt.nesteForekomst()

        # Tomme lag forsvinner, resten havner i Qgis kartlagsliste og kartflate
        punktlag.ferdig()
        linjelag.ferdig()
        linjelag2d.ferdig()
        multilinjelag.ferdig()
        multilinjelag2d.ferdig()
        collectionlag.ferdig()


