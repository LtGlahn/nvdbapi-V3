# Segmentering 

For oss NVDB-nerder betyr _segmentering_ kunsten å lage et pent og ryddig vegnettsdatasett utav et mangfoldig datagrunnlag med veldig variabel utstrekning langs vegnettet. Figuren under viser hvordan fartsgrense og  trafikkemngde (ÅDT) kan variere langs en strekning - og en bit av strekningen har også et gjerde. 

![Bildet viser fartsgrense, trafikkmengde og et gjerde med ulik utstrekning på vegnettet](./pic/segmentering1.png)

En segmenteringsprosess vil først "klippe opp" datasett basert på alle start- og sluttpunkt som finnes i de ulike datasettene 

![Bildet viser klippeprosess for data med ulik utstrekning langs vegnettet](./pic/segmentering2.png)

Og de "oppklippede" bitene kan så settes sammen til små segmenter.  

![Bildet viser hvordan vi kombinerer alle data i form av mange små segmenter](./pic/segmentering3.png)

I  eksemplet vårt startet vi med en sammenhengende bit for vegnettet pluss to fartsgrenser, to trafikkmengde-objekter og ett gjerde - og sluttresultatet blir fem segmenter (korte biter). Hver eneste av disse bitene har nå informasjon om vegnettet, trafikkmengde, fartsgrense og gjerder (selv gjerdet kun finnes på én av bitene så vil de fire andre bitene ha informasjon om at det IKKE finnes gjerder på strekningen). 

# Våre inngangsdata

Metoden `segmentering.py` jobber med strekningsdata, det vil si data som har en utstrekning langs vegnettet, ikke data som kun er stedfestet i et punkt på vegnettet (slike data kan du enkelt stedfeste på segmenteringsresultatet etterpå, her kommer det sikkert noen kodeeksempler etter hvert). Som inngangsdata bruker vi [geoddataframes](https://geopandas.org)  slik de blir laget av [nvdbapiv3](https://github.com/LtGlahn/nvdbapi-V3) - biblioteket, som igjen henter såkalt "segmentert vegnett" og segmenterte fagdata fra [NVDB api LES](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon). Segmentering i NVDB api LES betyr at NVDB-data blir segmentert på kontraktsområde, kommune, vegsystemreferanse, riksvegrute (og et par andre ting). Dette har noen fordeler, blant annet at hvert segment i inngangsdataene er pent strukturert og har 1:1 forhold mellom geometri, vegsystemreferanse og lineære posisjoner. 

Vår rutine bruker informasjon om posisjon på veglenkesekvens pluss geometri til å regne ut overlapp. Med på kjøpet får du også riktig vegreferanse med meterverdi (såfremt kolonnen `vref` finnes i inngangsdataene). Inngangsdata kan selvsagt komme fra en annen kilde enn NVDB såfremt du har koblet data til NVDB vegnett og du må ha følgende egenskaper (kolonner): 

| Egenskapsnavn | Innhold | 
|:---------------|:--------|
| veglenkesekvensid |  Id til NVDB veglenkesekvens |
| startposisjon | Flyttall med 8 desimalers presisjon, starten på utbredelsen langs veglenkesekvensid | 
| sluttposisjon | Flyttall med 8 desimalers presisjon, starten på utbredelsen langs veglenkesekvensid | 
| geometry | [shapely](https://shapely.readthedocs.io/) LineString geometrisk objekt |
| vref | _**Kan sløyfes**_, tekststreng med vegsystemreferanse på formatet `RV2 S2D1 m300-1200` | 

Øvrige egenskapsnavn vil bli videreført til analysen (parameter `glemNvdbDetaljer=True` vil ignorere en del typiske NVDB-egenskaper som sjelden tilfører verdi, slik som _Prosjektreferanse, Eier_ etc). Men hovedregelen er at du bør derfor filtrere ut de egenskapsnavnene som ikke har betydning for deg og ditt bruksområde. 

# Metodikk 

Vi har dårlig erfaring med å klippe geometri basert på flyttalsoperasjoner basert på forholdet mellom veglenkeposisjoner og geometrisk lengde: Det blir for upresist. I stedet utnytter vi at selve klippeprosessen jo baserer seg på presist definerte start- og sluttpunkt for de datasettene som inngår: 

![Bildet viser klippeprosess for data med ulik utstrekning langs vegnettet](./pic/segmentering2.png)

Hvert "kuttpunkt" i dette steget av segmenteringsprosessen har en presist definert geometri lik eksakt første (eller siste) punkt på den linja som starter (evt slutter) i dette punktet på vegnettet. Via operasjonen på shapely-objektet `geometry.coords[0]` eller `geometry.coords[-1]` får vi tilgang til dette koordinatpunktet. Alt vi trenger å gjøre er å lagre informasjonen som en dictionary (oppslagstabell) for hver eneste veglenkeposisjon i datagrunnlaget: 

```python
from shapely import Point 
vpos = { } # Dictionary med geometri for veglenkeposisjoner
for enBitAv in inngangsdata: 
    vpos[ enBitAv['fraposisjon']] = Point( enBitAv['geometry'].coords[0] )
    vpos[ enBitAv['tilposisjon']] = Point( enBitAv['geometry'].coords[-1] )    
```

Dette geometriske punktet inngår så i "klippe"-operasjonene som vi gjør på vegnettsgeometrien (shapely LineString, med metoden `shapelycut` fra [github/LtGlahn/overlapp.py](https://github.com/LtGlahn/nvdbapi-V3/blob/master/overlapp.md#user-content-hvorfor-har-vi-en-egen-funksjon-shapelycut-) )

Samme logikk brukes for å holde styr på riktige meterverdier til vegsystemreferansen (gitt at kolonnen `vref` med vegsystemreferanser finnes i data for vegnettet). 

# Bitene blir for korte

Enhver segmenteringsprosess vil møte problemet med at to datasett _*nesten*_ har perfekt overlapp. Nedenfor er det illustret ved at fartsgrense endres fra 60 til 50 i _*nesten*_ samme punkt på vegnettet som der ÅDT-verdiene endres fra 5000 til 4000 kjt/døgn. Denne _*nesten perfekte*_ overlappen blir til et veldig kort segment - hvilket gir oss to problemener: 1) det er dårlig datakvalitet å ha veldig korte biter, 2) rent teknisk vil ultrakorte biter gi feilmelding i mye analyse- og kartprogramvare (et ekstremt kort linjestykke kollapser til et punkt, eller kartprogrammet av andre grunner ikke klarer håndtere så korte linjestykker).    

![Bildet viser hvordan to datasett med nesten perfekt overlapp gir ekstremt korte segmenter](./pic/segmentering4.png)

Vår håndtering av dette problemet består i at vi analyserer vår datastruktur med "kuttpunkt" (`vpos`-dictionary) og "hopper over" de kuttpunktene som ville gi altfor korte segmenter (parameterstyrt via nøkkelord `minsteLengde=0.1` med defaultverdi = 10cm). Dette er den mest komplekse delen av vår kode, med flere pekere (indekser) som tygger seg gjennom alle mulige kuttpunkt og "hopper over" dem som ellers ville gitt segmenter kortere enn minsteLengde. 