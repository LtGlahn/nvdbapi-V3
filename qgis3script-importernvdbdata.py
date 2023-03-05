# -*- coding: utf-8 -*-
"""
Script for å interaktivt legge til NVDB-vegnett og fagdata via python 
kommandolinje i QGIS. Se dokumentasjon på bruk av nvdbapi - funskjoner på
https://github.com/LtGlahn/nvdbapi-V3


Legg dette scriptet et sted hvor det er lettvint 
å finne fra QGIS. F.eks. C:/Users/<dittbrukernavn>. 

EKSEMPLER

#Vegnett europaveger Trondheim kommune
v = nvdbVegnett()
v.addfilter_geo({ 'kommune' : 1601, 'vegreferanse' : 'E' })" ) 
nvdbsok2qgis( v, lagnavn='Europaveger Trondheim') 

# Vegnett innenfor kartutsnitt
v = nvdbVegnett()
nvdb2kart( v, iface) 


# Bomstasjoner
b = nvdbFagdata(45)
nvdbsok2qgis( b) 

# Søk etter fartsgrenser innenfor kartflaten, legg til 
f = nvdbFagdata(105)
nvdb2kart( f, iface)

# Søk etter kjent objektID, legg til kartflaten
nvdb2kart( 572672190, iface )

"""
import sys


#########################################################33
##
## Endre stien til den mappen der du har lastet ned dette 
## reposet https://github.com/LtGlahn/nvdbapi-V3 
## 
## Merk at hvis du laster ned repos som zip-fil og høyrekikker->Pakk ut alle
## så vil stien være NEDLASTING\\nvdbapi-V3-master\\nvdbapi-V3-master
## 

# nvdblibrary = 'C:/Data/leveranser/nvdbapi-V3'
nvdblibrary = 'C:\\Users\\jajens\Downloads\\nvdbapi-V3-master\\nvdbapi-V3-master'
# nvdblibrary = 'C:\Users\<DITT BRUKERNAVN>\Downloads\\nvdbapi-V3-master\\nvdbapi-V3-master'
# nvdblibrary = '/home/jan/Documents/jobb/nvdbapi-V3'


## Hvis vi ikke klarer å importere nvdbapiv3 så prøver vi å føye
## mappen nvdblibrary til søkestien. 
try: 
    import nvdbapiv3
except ModuleNotFoundError:
    print( "Fant ikke nvdbapiv3 i sys.path, legger til mappen", nvdblibrary)
    sys.path.append( nvdblibrary ) 
    
    try: 
        import nvdbapiv3
    except ModuleNotFoundError as e:
        print( "\nImport av nvdbapiv3 feiler for", nvdblibrary  )
        raise ModuleNotFoundError( "==> Variabel nvdblibrary skal peke til mappen https://github.com/LtGlahn/nvdbapi-V3  <==" )
            
    else: 
        print( "SUKSESS - kan importere nvdbapiv3 etter at vi la til", nvdblibrary, "i sys.path" )
else:
    print( "HURRA - vi kan importere nvdbapiv3 " ) 

## Her importerer vi de funksjonene vi trenger 
from nvdbapiv3 import nvdbFagdata, nvdbVegnett
from nvdbapiV3qgis3 import  nvdb2kart, nvdbsok2qgis, url2kart, nvdb2kartListe

## Bruk linjene nedenfor for debugging
## Funksjonskallene på python-konsollet i QGIS blir da
## 
##      >>> sok = nvdbapiv3.nvdbFagdata(86)
##      >>> nvdbapiV3qgis3.nvdb2kart( sok, iface )
## 
# import importlib
# import nvdbapiV3qgis3
# import nvdbapiv3  
# importlib.reload(nvdbapiV3qgis3 )
# importlib.reload(nvdbapiv3   )


