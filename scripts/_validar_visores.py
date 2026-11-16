# -*- coding: utf-8 -*-
"""Valida que el SVG embebido en los visores sea XML bien formado y tenga contenido."""
import os
import re
import xml.etree.ElementTree as ET

ARCHIVOS = [
    r"D:\Work\PROJECTS\RevitElectrico\data\visor_ruteo_F02_v03.html",
    r"D:\Work\PROJECTS\RevitElectrico\data\visor_ruteo_E05_v01.html",
]

NS = "{http://www.w3.org/2000/svg}"


def _buscar(root, etiqueta):
    """Busca con y sin namespace (el SVG puede venir con o sin xmlns)."""
    encontrados = root.findall(".//" + NS + etiqueta)
    if not encontrados:
        encontrados = root.findall(".//" + etiqueta)
    return encontrados

for ruta in ARCHIVOS:
    nombre = os.path.basename(ruta)
    if not os.path.exists(ruta):
        print("%-32s NO EXISTE" % nombre)
        continue
    texto = open(ruta, encoding="utf-8").read()
    m = re.search(r"<svg id=\"svg\".*?</svg>", texto, re.S)
    if not m:
        print("%-32s SIN SVG" % nombre)
        continue
    try:
        root = ET.fromstring(m.group(0))
    except Exception as exc:
        print("%-32s SVG INVALIDO: %s" % (nombre, exc))
        continue
    paths = _buscar(root, "path")
    circles = _buscar(root, "circle")
    rects = _buscar(root, "rect")
    polys = _buscar(root, "polygon")
    revision = [p for p in paths if p.get("data-revision") == "1"]
    print("%-32s SVG VALIDO" % nombre)
    print("   viewBox=%s" % root.get("viewBox"))
    print("   paths=%d (revision=%d) circles=%d rects=%d polygons=%d"
          % (len(paths), len(revision), len(circles), len(rects), len(polys)))
    servicios = sorted({p.get("data-servicio") for p in paths if p.get("data-servicio")})
    print("   servicios dibujados: %s" % servicios)
