# Overlapp langs vegnettet

NVDB har tre - 3 - parametre som beskriver posisjon og utbredelse langs vegnettet: 

  * Lineære posisjoner langs veglenkesekvens
  * Geografiske koordinater
  * Vegsystemreferanse med meterverdier 

Alle tre systemene kan brukes til å finne overlapp og manglende overlapp mellom to NVDB datasett. Utfordringen er 
å lage metoder der resultatet blir riktig for _alle tre parametrene samtidig_. 

Gullstandarden er selvsagt å finne overlapp basert på veglenkeposisjoner, og det er den metoden vi forfølger her. Posisjon
på veglenke oppgis alltid med 8 desimaler etter komma, noe som tilsvarer 0.1mm hvis veglenkesekvensen er 10km lang. 

Geografiske koordinater kan selvsagt brukes, det er massevis av standard funksjonalitet i GIS verktøy som kan brukes til å 
finne romlige relasjoner. 

Vegsystemreferansen den mest upresise av de tre (nærmeste hele meter), og den er i tillegg ferskvare: Vegreferanser kan og vil 
endre verdi i takt med at vegnettet utvikler seg. Når det er sagt - analyser basert på hele meter fra vegsystemreferansen 
funker helt greit til sitt bruk, innafor sin "hele meter" presisjon såfremt datasettene har samme tidsstempel 
(evt at man har stålkontroll på at vegsystemreferansen ikke har endret seg mellom datauttakene). **Antagelsen om at 
vegreferansesystemet ikke endres har skapt utrolig mye kluss opp igjennom for utallige analyser og sammenstillinger.**

# Utfordringer med lineære referanser fra NVDB i python

En ekstra utfordring med NVDB veglenkesekvenser er at vi ikke har _*hele* veglenkesekvensen tilgjengelig som en sammenhengende bit (LinesString) 
som starter med posisjon 0 og slutter i posisjon 1. For noen av veglenkesekvensene er deler satt historisk. 
Joda, det kunne la seg gjøre å rekonstruere den orginale veglenkesekvensen ut fra historiske data, men det er tidkrevende og plundrete. 

En annen utfordring er at LES ikke gir ut koordinatstreng med _measure_ verdier - LineString(x0 y0 z0 M0, x1 y1 z1 M1, ...), der den fjerde verdien (M) angir hvilken veglenkeposisjon som gjelder for de geografiske koordinatene (x,y,z). I så fall 
er det jo grei sak å interpolere mellom de to koordinatpunktene som ligger nærmest den ønskede veglenkeposisjonen.  

Men med disse begrensingene så var det begrenset med metoder for manipulering av lineære referanser og geometri i de pythonbibliotekene jeg har undersøkt. Jeg 
prøvde metoden der vi laget en lineær mapping mellom fysiske meter og de veglenkeposisjonene vi har i start og slutt av segmentet vårt: 
```python
# Lengde i meter y= f(x) = a*x som funksjon av veglenkeposisjon x langs dette segmentet
# der x er innafor intervallet [startposisjon, sluttposisjon ]
a = mygeom.length / (sluttposisjon -  startposisjon)
L = a * nyposisjon 
# startposisjon <= nyposisjon <= sluttposisjon 
# Avstanden L kan nå brukes til å klippe geometrien nygeom med vår egenskrevne funksjon shapelycut, 
# som klipper geometrier i to i et punkt L meter fra starten  
```

Metoden her fungerte, men ble altfor upresist: Geometrien vår kan være mellom 1m og flere titalls kilometer 
(teoretisk), og denne lengden skal så deles på en differanse i veglenkeposisjon som kan være ørliten. 
Dette er et uheldig delestykke, rent numerisk. 

> I stedet så bruker vi det faktum at vi IKKE skal ikke "klippe" geometrien i en vilkårlig posisjon: 
> Vår metode skal "klippe" slik at vår overlapp (og de bitene som ikke overlapper) stemmer eksakt med
> utstrekningen til inngangsdataene.  Vår "klipping" vil derfor alltid skje eksakt på start eller slutt
> i ett av ett av segmentene i inngangsdataene. Alt vi trenger gjøre er å ta vare på og utnytte denne 
> informasjonen, så unngår vi den upresise omregningen over. 

Så dermed lager vi en oppslagsnøkkel (dictionary) mellom veglenkeposisjon og geografiske punkt for 
start og slutt på alle segmenter langs en veglenkesekvens. 

```python
# Anta at data = liste med (shapely-LineString-geometri, startposisjon, sluttposisjon) langs samme veglenkesekvens
# Vi aner foreløpig ikke hvor vi skal "klippe", men tar vare på informasjon om hvilket 
# koordinat som gjelder for hver eneste start- og sluttposisjon 

from shapely import Point 
geomPunktVpos = { }
for myLine in data:
    mygeom        = myLine[0]           # Shapely LineString - objekt
    startposisjon = myLine[1]
    sluttposisjon = myLine[2] 
    geomPunktVpos[startposisjon] = Point( mygeom.coords[0] ) # Shapely punkt-geometri objekt
    geomPunktVpos[sluttposisjon] = Point( mygeom.coords[1] ) # Shapely punkt-geometri objekt

# Nå har vi en oppslagsnøkkel mellom alle potensielle "klippepunkter" og tilhørende geometrisk punkt (shapely)
# Via litt finregning finner vi de veglenkeposisjoner som gir oss overlapp og anti-overlapp ("til overs", left join)
# Så nå kan vi sende en presis geografisk posisjon til vår modifiserte shapelycut - funksjon.
```

Tilsvarende metode brukes også for å få riktig meterverdi på vegsystemreferansen: Vi lager oppslagsnøkkel (dictionary) mellom veglenkeposisjon og hele meter, og bruker denne for å sikre at vi får rett meter i sluttresultatet 
