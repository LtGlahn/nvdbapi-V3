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

# Installer og kom i gang

Søk og datanedlasting med `nvdbapi-v3` og spørringer mot NVDB api LES med `apiforbindelse` er publisert som en [pypi-modul](https://pypi.org/project/nvdbapi-v3/), og kan installeres med

```
pip install nvdbapi-v3
```

Merk bindestreken! Etter installasjon må du importere `nvdbapiv3`, uten bindestrek. Eksempel:

```
import nvdbapiv3
sokeobjekt = nvdbapiv3.nvdbFagdata( 45)
liste_med_dict = sokeobjekt.to_records()
```


Men - dette reposet https://github.com/LtGlahn/nvdbapi-V3 inneholder også en ganske mye kode for dataanalyse, bearbeiding etc. Dette er IKKE tatt med i pypi-modulen. Noe av grunnen er at dataanalytikere liker å velge verktøy selv. I tillegg reduserer vi risiko for versjonskonflikt drastisk ved at pypi-modulen har færrest mulig avhengigheter ut over standardbiblioteket til python - og installasjonen med pip går veldig mye kjappere. Så dersom du synes koden min for GIS-analyser er nyttig så må du [laste ned reposet](https://github.com/LtGlahn/nvdbapi-V3) og så installere f.eks [geopandas](https://geopandas.org/en/stable/) på egen hånd. 

# Prinsipper 

1. Et _*søkeobjekt*_ håndterer all mikk-makk rundt spørringer mot NVDB api, paginering etc. 
1. Vi har to typer søkeobjekter
    * nvdbVegnett - henter vegnett (lenksekvenser og tilhørende lenker) 
    * nvdbFagdata - henter en av de 400 fagdatatypene vi har definert i [NVDB datakatalog](https://datakatalogen.vegdata.no/)
1. Søkeobjektene har funksjoner for å avgrense søk, og hente ut alle data som tilfredssstiller søket. 
1. Søkeobjektet har funksjonen `to_records()` som gjør om NVDB-data til dictionaries i liste, velegnet for import til f.eks pandas. 
    * Denne funksjonen har noen 
valgmuligheter mhp håndtering av geometri (vegnettsgeometri, dvs senterline versus fysisk plassering i terreng) som det kan være verdt å lese seg opp på. 
1. Fra søkeobjektet kan du iterere over alle NVDB-objekter som tilfredsstiller søket ditt: 
    1. Enten som JSON-objekt [rett fra NVDB api](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid_ "Vegobjekter i NVDB api")
    2. Eller som et _*nvdbFagObjekt*_, som har en del fiffige funksjoner for å hente ut egenskapverdier m.m. 
1. I tillegg til søkeobjekten har vi en del hjelpefunksjoner
   1. finnid: Henter vegobjekt og/eller lenkesekvens med angitt ID
   2. nvdbfagdata2records: Flater ut NVDB-vegobjekt (direkte fra NVDB api) til enklere (forutsigbar) dictionary-struktur
   3. egenskaper2records: Oversetter liste med egenskapverdier til dictionary 

## Pandas og geopandas 

Analysebiblioteket [Pandas](https://pandas.pydata.org/), med den kartorienterte lillebroren [GeoPandas](https://geopandas.org/), er blitt _de facto_ standard analysebibliotek innafor python. Se punktet om metoden `.to_records()`, som er laget nettopp for å gjøre det enkelt å importere NVDB-søk til pandas. 

## Jeg vil ha NVDB-data på geojson format

Se [dette eksemplet](https://gist.github.com/LtGlahn/5a6993ee4d36e675fa74f5a6d6d61b01)
   
## nvdbVegnett 

Søkeobjekt for å hente segmentert vegnett fra NVDB api. 

## nvdbFagdata(objektTypeId) 

Søkeobjekt for å hente fagdata (ikke vegnett, men øvrige data om vegen). Totalt har vi definert i underkant av 400 ulike objekttyper
i [datakatalogen](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid___vegobjektid_). 

nvdbFagdata utvider klassen nvdbVegnett, og arver metoder og egenskaper fra denne. 

argumentet objektTypeID (heltall) angir hvilke objekttype vi jobber med, definert i [datakatalogen](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/openapi/#/Vegobjekter/get_vegobjekter__vegobjekttypeid___vegobjektid_)

# Felles metoder for nvdbVegnett og nvdbFagdata

### Dokumentasjon - docstring finnes! 

Alle klasser og funksjoner er dokumentert med docstring, som kan fås fram med attributten `.__doc`

```python
import nvdbapiv3 
print( nvdbapiv3.nvdbFagdata.to_records.__doc__ )

sokeobjekt = nvdbapiv3.nvdbFagdata(45)
print( sokeobjekt.to_records.__doc__ )
```

Ipython-brukere er selvsagt kjent med `?` - syntaksen, som gir deg signaturen pluss docstring: 

```python
import nvdbapiv3
?nvdbapiv3.nvdbFagdata.to_records # Kun for ipython

sokeobjekt = nvdbapiv3.nvdbFagdata(45)
?søkeobjekt.to_records  # Kun for ipython 
```


---
### to.records()

Lagrer data som en liste med dictionaries. Spiller veldig fint sammen med analysebiblioteket pandas, der du enkelt kan konvertere et søkeobjekt til 
pandas dataframe med kommandoen

```python 
import pandas as pd
myDf = pd.DataFrame( mittSøkeObjekt.to_records())
```

Pandas kan igjen konverteres til geodataframe. Aller først må du opprette en ny geometrikolonne med [shapely](https://shapely.readthedocs.io/) - objekter. Erfaringsmessig er det lurt at geometrikolonnen kolonnen heter _geometry_, uten at dette er et offisielt krav. 

```python
import geopandas as gpd
from shapely import wkt
myDf['geometry'] = myDf['geometri].apply( wkt.loads )
myGDF = gpd.GeoDataFrame( myDf, geometry='geometry', crs=5973 )
```

> Hva er geometri? 

NVDB fagdata kan ha en eller to kilder til geometri:
  * Vegnettet - dvs senterlinje veg for den biten av vegnett som objektet er tilknyttet. Punkt eller linje, evt multilinje (MultiLineString). 
  * Objektets _egengeometri_, som viser fysisk plassering av vegutstyr i terreng evt på eller nær veg. Noen objekttyper, slik som for eksempel trær, tillater flere geometrivarianter (punkt, linje, flate) samtidig. 

Standardinnstillingen for `to_records()` er å gi deg geometri for vegnettet `(geometri=False)`, og denne igjen er delt opp i ett eller flere vegsegmenter `(vegsegmenter=True)`. Noen ganger er behovet motsatt: 

```python 
import nvdbapiv3 
sok = nvdbapiv3.nvdbFagdata( 45 ) # søkeobjekt for bomstasjoner 
data = sok.to_records( vegsegmenter=False, geometri=True )
```
Som da gir deg s.k. _egengeometri_ for NVDB-objekter, såfremt den finnes. Noen objekter mangler data for egengeometri, og da hentes geometri fra vegtilknytning. 

Med unntak av standardinnstillingene `(vegsegmenter=True, geometri=False)`  så er du **aldri garantert at søket ditt returnerer samme geometritype**. Noen objekttyper, f.eks. trær, kan ha flere typer egengeometri (både flate, linje og punkt). Eller hvis objektet mangler egengeometri så returneres vegnettsgeometrien. 

---

### refresh() 

Sletter alle nedlastede data, og nullstiller telleverket i paginering. 

---
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
----
### nesteForekomst()

Gir deg ett NVDB objekt (vegnett eller fagdata), i henhold til dine søkekriterier (filtre). Alle detaljer med datanedlasting fra API håndteres internt. 


```python
sokeObj = nvdbFagdata(807) # Døgnhvileplass
ettNvdbObj = v.nesteForekomst()
while ettNvdbObj: 
	print ettNvdbObj['id']
	ettNvdbObj = sokeObj.nesteForekomst()
```

I stedet for _nesteForekomst_ - logikken har vi nå støtte for de generelle python-metodene for å iterere over søkeobjektet.  (__next__, __iter__). Vi anbefaler å bruke de generelle python-metodene:

```
for ettNvdbObj in sokeObj: 
    print ettNvdbObj['id']
```

Takk til [Francesco Frassinelli](https://github.com/frafra), som tok initiativ til denne forbedringen. 
---
### info()

Skriver til konsoll alle filtere, pagineringsdetaljer, antall objekter i arbeidsminnet. For `nvdbFagdata` henter vi også statistikk fra NVDB api om antall treff og lengde for dette søket.  

---
# Flere metoder for nvdbFagdata

### nesteNvdbFagObjekt() 

Objektorientert tilnærming - returnerer neste forekomst av NVDB objektet som en instans av
klassen [nvdbFagObjekt](https://github.com/LtGlahn/nvdbapi-V2#nvdbfagobjekt)

---
### statistikk()

Spør NVDB api hvor mange forekomster som finnes med angitte filtre. Returnerer dict med antall treff 
og  strekningslengde (antall meter). Strekningslengde er 0 for punktobjekter. 

---
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

---
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

---
### wkt 

Returnerer koordinatene til objektets geometri som [Well Known Text](https://en.wikipedia.org/wiki/Well-known_text)

---
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
 
