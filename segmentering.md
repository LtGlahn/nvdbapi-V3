# Segmentering 

For oss NVDB-nerder betyr _segmentering_ kunsten å lage et pent og ryddig vegnettsdatasett utav et mangfoldig datagrunnlag der dataene har ulik utstrekning langs vegnettet. Figuren under viser et eksempel på hvordan det kan se ut: Vi har en vegstrekning der vi har data for fartsgrense og trafikkmengde (ÅDT) - og en bit av strekningen har også et gjerde. 

![Bildet viser fartsgrense, trafikkmengde og et gjerde med ulik utstrekning på vegnettet](./pic/segmentering1.png)

En segmenteringsprosess vil først "klippe opp" datasett basert på alle start- og sluttpunkt som finnes i de ulike datasettene:

![Bildet viser klippeprosess for data med ulik utstrekning langs vegnettet](./pic/segmentering2.png)

Og de "oppklippede" bitene kan så settes sammen til små segmenter.  

![Bildet viser hvordan vi kombinerer alle data i form av mange små segmenter](./pic/segmentering3.png)

I  eksemplet vårt startet vi med en sammenhengende bit for vegnettet pluss to fartsgrenser, to trafikkmengde-objekter og ett gjerde - og sluttresultatet blir fem segmenter (korte biter). Hver eneste av disse bitene har nå informasjon om vegnettet, trafikkmengde, fartsgrense og gjerder (selv gjerdet kun finnes på én av bitene så vil de fire andre bitene ha informasjon om at det IKKE finnes gjerder på strekningen). 

# Våre inngangsdata

Metoden `segmentering.py` jobber med strekningsdata, det vil si data som har en utstrekning langs vegnettet, ikke data som kun er stedfestet i et punkt på vegnettet _(slike data kan du enkelt stedfeste på segmenteringsresultatet etterpå, her kommer det sikkert noen kodeeksempler etter hvert)_. 

Som inngangsdata bruker vi [geoddataframes](https://geopandas.org)  slik de blir laget av [nvdbapiv3](https://github.com/LtGlahn/nvdbapi-V3) - biblioteket, som igjen henter såkalt "segmentert vegnett" og segmenterte fagdata fra [NVDB api LES](https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon). Segmentering i NVDB api LES betyr at NVDB-data blir segmentert på kontraktsområde, kommune, vegsystemreferanse, riksvegrute (og et par andre ting). Dette har noen fordeler, blant annet at hvert segment i inngangsdataene er pent strukturert og har 1:1 forhold mellom geometri, vegsystemreferanse og lineære posisjoner. 

Vår rutine bruker lineære posisjoner på veglenkesekvens til å regne ut bruddpunkter og sette dem sammen til små segmenter. Vi legger vekt på at sluttresultatet skal være samsvar mellom geometri (koordinater) og lineær utstrekning, og med riktig vegreferanse med meterverdi (såfremt kolonnen `vref` finnes i inngangsdataene). Inngangsdata kan selvsagt komme fra en annen kilde enn NVDB såfremt du har koblet data til NVDB vegnett og du må ha følgende egenskaper (kolonner): 

| Egenskapsnavn | Innhold | 
|:---------------|:--------|
| veglenkesekvensid |  Id til NVDB veglenkesekvens |
| startposisjon | Flyttall med 8 desimalers presisjon, starten på utbredelsen langs veglenkesekvensid | 
| sluttposisjon | Flyttall med 8 desimalers presisjon, starten på utbredelsen langs veglenkesekvensid | 
| geometry | [shapely](https://shapely.readthedocs.io/) LineString geometrisk objekt |
| vref | _**Kan sløyfes**_, tekststreng med vegsystemreferanse på formatet `RV2 S2D1 m300-1200` | 

Øvrige egenskapsnavn vil bli videreført til analysen (parameter `glemNvdbDetaljer=True` vil ignorere en del typiske NVDB-egenskaper som sjelden tilfører verdi, slik som _Prosjektreferanse, Eier_ etc). Men som hovedregel er det lurt at du kun sender inn de dataverdiene som har relevans, dvs dem som er angitt over pluss de egenskapene du ønsker å ha i sluttresultatet. Tilsvarende er det ditt ansvar å sørge for  

# Metodikk 

Vi har dårlig erfaring med å klippe geometri basert på flyttalsoperasjoner basert på forholdet mellom veglenkeposisjoner og geometrisk lengde: Det blir for upresist. I stedet utnytter vi at selve klippeprosessen jo baserer seg på presist definerte start- og sluttpunkt for de datasettene som inngår: 

![Bildet viser klippeprosess for data med ulik utstrekning langs vegnettet](./pic/segmentering2.png)

Hvert "kuttpunkt" i dette steget av segmenteringsprosessen har en presist definert geometri lik eksakt første (eller siste) punkt på den linja som starter (evt slutter) i dette punktet på vegnettet. Via operasjonen på shapely-objektet `geometry.coords[0]` eller `geometry.coords[-1]` får vi tilgang til dette koordinatpunktet. Alt vi trenger å gjøre er å lagre informasjonen som en dictionary (oppslagstabell) for hver eneste veglenkeposisjon i datagrunnlaget: 

```python
from shapely import Point 
vpos = {} # Dictionary med geometri for veglenkeposisjoner
for enBitAv in inngangsdata: 
    vpos[ enBitAv['fraposisjon']] = Point( enBitAv['geometry'].coords[0] )
    vpos[ enBitAv['tilposisjon']] = Point( enBitAv['geometry'].coords[-1] )    
```

Dette geometriske punktet inngår så i "klippe"-operasjonene som vi gjør på vegnettsgeometrien (shapely LineString, med metoden `shapelycut` fra [github/LtGlahn/overlapp.py](https://github.com/LtGlahn/nvdbapi-V3/blob/master/overlapp.md#user-content-hvorfor-har-vi-en-egen-funksjon-shapelycut-) )

Samme logikk brukes for å holde styr på riktige meterverdier til vegsystemreferansen (gitt at kolonnen `vref` med vegsystemreferanser finnes i data for vegnettet): Vi lager en dictionary der vi kan gjøre oppslag på veglenkeposisjon (flyttall) og få riktig meterverdi. 

# Bitene blir for korte

Enhver segmenteringsprosess vil møte problemet med at to datasett _*nesten*_ har perfekt overlapp. Nedenfor er det illustret ved at fartsgrense endres fra 60 til 50 i _*nesten*_ samme punkt på vegnettet som der ÅDT-verdiene endres fra 5000 til 4000 kjt/døgn. Denne _*nesten perfekte*_ overlappen blir til et veldig kort segment - hvilket gir oss to problemener: 
  1. det er dårlig datakvalitet å ha veldig korte biter
  1. rent teknisk kan ultrakorte biter gi crash eller feilmelding i en del analyse- og kartprogramvare _(en variant er jo at ultrakorte linjestykker blir omgjort til punkt, men det kan gi trøbbel senere i analyseløpya)_.    

![Bildet viser hvordan to datasett med nesten perfekt overlapp gir ekstremt korte segmenter](./pic/segmentering4.png)

Vår håndtering av dette problemet består i at vi analyserer vår datastruktur med "kuttpunkt" (`vpos`-dictionary) og "hopper over" de kuttpunktene som ellers ville gitt  segmenter kortere enn parameter  `minsteLengde`, som har defaultverdi = 0.1, dvs 10cm. 

> Håndtering av minstelengde er den mest komplekse delen av vår kode, ca 80 kodelinjer som tygger seg gjennom alle mulige kuttpunkt med flere pekere (indekser) å holde styr på. 
>
> Disse indeksene representerer to segmenter: `arbeidssegment1` (som vi vet er lengre enn minstelengde fordi vi konstruerte den slik!) og `arbeissegment2` (som vi gjør gradvis større inntil den oppnår minstelengde). Når vi kommer dit at `arbeissegment2 > minsteLengde` så lagrer vi kuttpunktene som definerer `arbeidssegment1`, setter `arbeidssegment1 = arbeidssegment2` og starter på et nytt `arbeidssegment2`. Gjenta inntil vi når enden av den vegnettsbiten vi itererer over.  Pluss litt logikk som sikrer at vegnettsbiten ikke blir kortere hvis det er et mulig bruddpunkt helt i start eller slutt av vegnettsbiten. 

