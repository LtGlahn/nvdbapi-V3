 # Jobb interaktivt mot NVDB api V3

Jobb interaktivt og objektorientert mot NVDB api V3! 

Les først gjennom [https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/)
for nyttige tips og innblikk i logikken. 

Rutinene håndterer all kommunikasjon mot NVDB API, inklusive paginering (d.v.s. vi henter passe
store "bøtter" med data av gangen) Du føyer til dine egne søkefiltere, og du kan sjekke antall 
treff før du laster ned data. 

Vi oppforder alle til å gi oss relevant kontaktinfo i form av http headere 
X-Client og X-Kontaktperson. Dermed har vi bedre statistikk over hvem som bruker API'et til hva, 
og kan også nå ut til brukerne ved problemer. Denne informasjonen lese fra fila 
*nvdbapi-clientinfo.json*; bruk gjerne malen  *nvdbapi-clientinfo-template.json* som utgangspunkt. 

Hovedrutinen *nvdbapiv3.py* er skrevet i python3, men burde også fungere med python 2 (dog med litt mindre god håndtering av norske tegn). 

# Prinsipper 

1. Et _*søkeobjekt*_ håndterer all mikk-makk rundt spørringer mot NVDB api, paginering etc. 
1. Vi har to typer søkeobjekter
    * nvdbVegnett - henter vegnett (lenksekvenser og tilhørende lenker) 
    * nvdbFagdata - henter en av de 400 fagdatatypene vi har definert i [NVDB datakatalog](https://datakatalogen.vegdata.no/)
2. Søkeobjektene har funksjoner for å avgrense søk, og hente ut alle data som tilfredssstiller søket. 
3. Noen funksjoner _(f.eks. nvdb2geojson)_ tar et slik søkeobjekt og transformerer til andre datastrukturer, tabulære data m.m.
4. Fra søkeobjektet kan du iterere over alle NVDB-objekter som tilfredsstiller søket ditt: 
    1. Enten som JSON-objekt [rett fra NVDB api](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid_ "Vegobjekter i NVDB api")
    2. Eller som et _*nvdbFagObjekt*_, som har en del fiffige funksjoner for å hente ut egenskapverdier m.m. 
7. I tillegg til søkeobjekten har vi en del hjelpefunksjoner
   1. finnid: Henter vegobjekt og/eller lenkesekvens med angitt ID
   2. nvdbfagdata2records: Flater ut NVDB-vegobjekt (direkte fra NVDB api) til enklere (forutsigbar) dictionary-struktur
   3. egenskaper2records: Oversetter liste med egenskapverdier til dictionary 
   
## nvdbVegnett 

Søkeobjekt for å hente segmentert vegnett fra NVDB api. 

## nvdbFagdata(objektTypeId) 

Søkeobjekt for å hente fagdata (ikke vegnett, men øvrige data om vegen). Totalt har vi definert i underkant av 400 ulike objekttyper
i [datakatalogen](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid___vegobjektid_). 

nvdbFagdata utvider klassen nvdbVegnett, og arver metoder og egenskaper fra denne. 

argumentet objektTypeID (heltall) angir hvilke objekttype vi jobber med, definert i [datakatalogen](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid___vegobjektid_)

# Felles metoder for nvdbVegnett og nvdbFagdata


### refresh() 

Sletter alle nedlastede data, og nullstiller telleverket i paginering. 

### filter( FILTERARG )

FILTERARG er en python dictionary med relevante filtre. Søkeobjektene `nvdbVegnett` og `nvdbFagdata` støtter begge geografiske filtre (fylke, kommune, kartutsnitt, vegsystemreferanse), men kun `nvdbFagdata` har avanserte egenskapsfilter og overlappfilter. Og `nvdbVegnett` støtter en del filter som kun er relevant for vegnett (typeeveg, adskilte løp etc). 
Se [dokumentasjon NVDB api V3](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegnett/get_vegnett_veglenkesekvenser_segmentert)


Eksempel

```
v = nvdbVegnett()
v.filter( { 'kommune' : 5001 } )
v.filter( { 'vegsystemreferanse' : 'ev6s76d1' } )
# Filteret har nå verdien { 'vegsystemreferanse' : 'ev6s76d1', 'kommune' : 5001 }
```

### nesteForekomst()

Gir deg ett NVDB objekt (vegnett eller fagdata), i henhold til dine søkekriterier (filtre). Alle detaljer med datanedlasting fra API håndteres internt. 


```
v = nvdbFagdata(807) # Døgnhvileplass
p = v.nesteForekomst()
while p: 
	print o['id']
	o = v.nesteForekomst()
```


### nestePaginering()

Bruker paginering til å neste "bøtte" med data fra NVDB forekomst, i henhold 
til alle dine søkekriterier (filtre). 

Returerer True hvis dette ga gyldige data, og False når vi har hentet alle objektene. 

Du må selv kopiere data over fra listen *data\[\'objekter\'\]*

 
```
p = nvdbFagdata( 809) # Døgnhvileplass 
p.paginering['antall'] = 3 # Jukser litt med antall forekomster per bøtte. 
TF = p.nestePaginering()
minliste = []
while TF: 
    minliste.extend( p.data['objekter'] )
	TF = p.nestePaginering()
```

### info()

Skriver til konsoll alle filtere, pagineringsdetaljer, antall objekter i arbeidsminnet. For `nvdbFagdata` henter vi også statistikk fra NVDB api om antall treff og lengde for dette søket.  

# Flere metoder for nvdbFagdata

### nesteNvdbFagObjekt() 

Objektorientert tilnærming - returnerer neste forekomst av NVDB objektet som en instans av
klassen [nvdbFagObjekt](https://github.com/LtGlahn/nvdbapi-V2#nvdbfagobjekt)


### statistikk()

Spør NVDB api hvor mange forekomster som finnes med angitte filtre. Returnerer dict med antall treff 
og  strekningslengde (antall meter). Strekningslengde er 0 for punktobjekter. 


### egenskaper( egenskapsTypeID):

Skriver ut definisjonen av angitt egenskapstype (ID, heltall). 
Hvis ingen ID oppgis skriver vi ut en liste med ID, navn og type
for alle egenskapstyper for denne objekttypen. 

I stedet for ID (heltall) kan du også oppgi en tekststreng som sjekkes mot 
navnet på egenskapstypene. 

Denne funksjonen er nyttig for å finne riktig verdi på egenskap- og overlappfiltere. 
```
p = nvdbFagdata( 809) # Døgnhvileplass 
p.egenskaper()
p.egenskaper(9270) # Vaskeplass for trailere
p.egenskaper( 'ask') # Fritekst-søk, matcher ID 9270
```

# Eksempler, avanserte søk med nvdbFagdata 

Søk etter NVDB fagdata (vegobjekter) har en del avanserte muligheter. 

### Søk etter egenskapverdi 

Tekststreng med filtre for egenskapsverdier. Se dokumentasjon for [egenskapsfiltre](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#operations-Vegobjekter-get_vegobjekter__vegobjekttypeid_)

```
p = nvdbFagdata( 809) # Døgnhvileplass 
p.filter( {  'egenskap': '9246=12886 AND 9273=12940') 
p.filter()
>>  {'egenskap': '9246=12886 AND 9273=12940'} 
p.filter( '' ) # Nullstiller alle filtre. 
```

### Overlappsøk  

Henter fagdata som overlapper med annen objekttype (og denne kan evt også ha eget filter). Se dokumentasjon for [overlappfilter](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#operations-Vegobjekter-get_vegobjekter__vegobjekttypeid_)

```
u = nvdbFagdata(570) # Trafikkulykker
u.filter( { 'overlapp' : '105(2021=2738)' }) #  Trafikkulykker med fartsgrense = 80 km/t
```

TODO: Sjekk ut syntaks for overlapp mot flere objekttyper samtidig. 


# Egenskaper nvdbVegnett og nvdbFagdata

| Variabel | Verdi |
|---------|--------|
| data | Holder nedlastede data (i listen *objekter*) og metadata |
| filter | Holder alle filtre |
| headers | http headere som følger alle kall mot API | 
| sisteanrop | Siste kall som gikk mot NVDB API |
| objektTypeID | ID til objekttypen (ikke nvdbVegnett) |
| objektTypeDef | Datakatalogdefinisjon for objekttypen (ikke nvdbVegnett) |
|antall | Antall objekter i NVDB som tilfredsstiller kriteriene, hentes fra statistikkspørring mot API (ikke nvdbVegnett) |
| strekningslengde | Total lengde på objektene i NVDB som tilfredsstiller søkekriteriene, hentes fra statistikkspørring mot API (ikke nvdbVegnett) |

# nvdbFagObjekt

Klasse for objektorientert behandling av fagdata. Har for eksempel gode metoder for å 
spørre etter egenskapverdier. 

### egenskap( id_or_navn, empty=None)

Returnerer egenskapstype (dataverdi pluss metadata). Via nøkkelordet empty kan man angi ønsket retur hvis egenskapen ikke finnes. 

Argumentet _id_or_navn_ kan være heltall (datakatalog ID, mest skuddsikkert) eller (deler av) navnet på egenskapstypen. 

### egenskapverdi( id_or_navn, empty=None)

Som funksjonen "egenskap", men returnerer kun egenskapsverdien (selve dataverdien). 

eksempel:
```python
tunnellop = nvdbapi.nvdbFagdata(67)
ettLop = tunnellop.nesteNvdbFagObjekt()

# Henter egenskapen "Navn" for dette tunnelløpet
ettLop.egenskap('Navn')

# Henter kun egenskapsverdien 
ettLop.egenskapsverdi( 'Navn' )

# Bruker datakatalog ID i stedet for navn (mer skuddsikkert)
ettLop.egenskapsverdi( 1081 )

# Forkortelser eller deler av egenskapsnavnet er OK 
#(merk: Ingen sjekk på om frasen matcher flere egenskapsnavn, du får det første treffet)
ettLop.egenskap('MERK') # Gir første case *in*sensitive treff på frasen "merk" i egenskapsnavnet. 

# Angi at du vil ha tom streng (""), ikke None hvis egenskapstypen ikke finnes
# (Nei, vi sjekker ikke om dette er en lovlig egenskap for denne objekttypen etter datakatalogen)
tomStreng = ettLop.egenskapsverdi( 'finnes ikke', empty='')

```
### enumverdi( _id_or_navn, empty=None)
Som funksjonen "egenskapsverdi", men returnerer enmu_id - ikke dataverdien. Vil returnere None (eller din "empty"-verdi) 
hvis du bruker funksjonen på egenskaper som IKKE er enum (flervalg,tekst eller flervalg, tall). 

### wkt 

Returnerer koordinatene til objektets geometri som [Well Known Text](https://en.wikipedia.org/wiki/Well-known_text)

### relasjon(relasjon=None)

Returnerer en liste med alle relasjoner (default, uten argumenter), eller 
med nøkkelordet _relasjon=verdi_ returneres en liste med subsett
av relasjoner. Mulige verdier for nøkkeord _relasjon_ er _barn_, _foreldre_, 
_egenskapsID_ eller _egenskapsnavn_ til din favoritt objekttype. 

eksempel: 


```python
tunnellop = nvdbapi.nvdbFagdata(67)
ettLop = tunnellop.nesteNvdbFagObjekt()

# Henter mor-tunnellen, 3 ulike metoder
mor = ettLop.relasjon(relasjon='foreldre')
mor = ettLop.relasjon(relasjon='Tunnel')
mor = ettLop.relasjon(relasjon='581')

# Henter datterobjekt Tunnelportal, 
tp = ettlop.relasjon(relasjon='Tunnelport') # Delvis match
tp = ettlop.relasjon(relasjon='Tunnelportal') # Eksakt match
tp = ettlop.relasjon(relasjon=69)

# henter alle barn 
barn = ettlop.relasjon(relasjon='barn')

```
# finnid - finn fagdata eller vegnett ut fra NVDB Id

Hjelpefunksjonen ```finnid(objektid)``` søker etter NVDB objekter og lenkesekvens med angitt objektid. 

```
fart = nvdbapi.finnid(85288328, kunfagdata=True) # python-dict
fartobj = nvdbFagObjekt(fart)   # Objektorientert representasjon, se definisjonen nvdbFagobjekt


v = nvdbapi.finnid(521218, kunvegnett=True)   # Liste med lenker som finnes på lenkesekvens 521218
```

For fagdata returneres en DICT for angjeldende objekt. Denne kan gjøres om til et nvdbFagObjekt. 

For vegnett returneres en liste med de veglenke-delene som inngår i denne lenkesekvensen.  
 
