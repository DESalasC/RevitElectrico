# -*- coding: utf-8 -*-
"""Valida los SVG embebidos de los visores 2D y 3D."""
import os
import re
import xml.etree.ElementTree as ET

ARCHIVOS = [
    r"D:\Work\PROJECTS\RevitElectrico\data\visor_ruteo_F02_v04.html",
    r"D:\Work\PROJECTS\RevitElectrico\data\visor_3d_ruteo_F02_v04.html",
    r"D:\Work\PROJECTS\RevitElectrico\data\visor_3d_ruteo_E05_v02.html",
]

NS = "{http://www.w3.org/2000/svg}"

def buscar(root, etiqueta):
    encontrados = root.findall(".//" + NS + etiqueta)
    if not encontrados:
        encontrados = root.findall(".//" + etiqueta)
    return encontrados

for ruta in ARCHIVOS:
    nombre = os.path.basename(ruta)
    if not os.path.exists(ruta):
        print("%-38s NO EXISTE" % nombre)
        continue
    texto = open(ruta, encoding="utf-8").read()
    m = re.search(r"<svg id=\"svg\".*?</svg>", texto, re.S)
    if not m:
        print("%-38s SIN SVG" % nombre)
        continue
    try:
        root = ET.fromstring(m.group(0))
    except Exception as exc:
        print("%-38s SVG INVALIDO: %s" % (nombre, exc))
        continue
    paths = buscar(root, "path")
    revision = [p for p in paths if p.get("data-revision") == "1"]
    redes = sorted({p.get("data-red") for p in paths if p.get("data-red")})
    print("%-38s SVG VALIDO" % nombre)
    print("   viewBox=%s" % root.get("viewBox"))
    print("   paths=%d (revision=%d) redes=%s" % (len(paths), len(revision), redes))
