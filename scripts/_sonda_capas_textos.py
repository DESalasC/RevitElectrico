# -*- coding: utf-8 -*-
"""Sonda de capas y entidades de texto en el DXF de F 02 para buscar informacion de circuito/red."""
import ezdxf
from collections import Counter

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf"
doc = ezdxf.readfile(RUTA)
msp = doc.modelspace()

capas = Counter()
textos = []
for entidad in msp:
    capa = entidad.dxf.layer
    capas[capa] += 1
    tipo = entidad.dxftype()
    if tipo in ("TEXT", "MTEXT"):
        try:
            texto = entidad.dxf.text if tipo == "TEXT" else entidad.text
        except Exception:
            texto = str(entidad)
        if texto and texto.strip():
            textos.append((tipo, entidad.dxf.layer, texto.strip()[:80]))

print("=== Capas (top 30) ===")
for c, n in capas.most_common(30):
    print("  %dx  %s" % (n, c))
print("Total capas:", len(capas))

print("\n=== Textos / MTEXT (primeros 30) ===")
for t, l, txt in textos[:30]:
    print("  [%s] %s = %r" % (t, l, txt))
print("Total textos:", len(textos))
