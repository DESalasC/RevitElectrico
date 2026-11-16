# -*- coding: utf-8 -*-
"""Lista nombres de bloque INSERT distintos y sus conteos en el DXF de F 02."""
import ezdxf
from collections import Counter

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf"
doc = ezdxf.readfile(RUTA)
msp = doc.modelspace()

nombres = Counter()
for entidad in msp:
    if entidad.dxftype() == "INSERT":
        nombres[entidad.dxf.name or "(sin nombre)"] += 1

print("Total INSERTs:", sum(nombres.values()))
print("Nombres distintos:", len(nombres))
for nombre, cnt in nombres.most_common(40):
    print("  %dx  %s" % (cnt, nombre))
