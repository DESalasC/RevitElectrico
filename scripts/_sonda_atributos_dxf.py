# -*- coding: utf-8 -*-
"""Sonda rápida de atributos de bloques INSERT en el DXF de F 02."""
import sys
sys.path.insert(0, r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\ruteo")
from dxf_lector import leer_dxf
from config import cargar_config

cfg = cargar_config(
    r"D:\Work\PROJECTS\RevitElectrico\config\ruteo_config_v04.json",
    r"D:\Work\PROJECTS\RevitElectrico",
)

contenido = leer_dxf(
    r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf",
    capas_tuberia=["ELEC-LIGHT-PIPE", "ELEC-POWER- PIPE"],
    capas_dispositivo=["ELEC-APPL-ILUM", "ELEC-APPL-TOMAS", "ELEC-POWER-PANEL", "ELEC-Data-Service"],
    leer_atributos=True,
)

print("=== DISPOSITIVOS con atributos (primeros 10) ===")
cont = 0
for disp in contenido.dispositivos:
    if disp.atributos:
        cont += 1
        print("handle=%s nombre=%s capa=%s" % (disp.handle, disp.nombre, disp.capa))
        for k, v in disp.atributos.items():
            print("    %s = %r" % (k, v))
        if cont >= 10:
            break
print("Dispositivos con atributos (primeros 10 mostrados): %d totales" % cont)

print("\n=== MARCADORES con atributos (primeros 10) ===")
cont2 = 0
for marc in contenido.marcadores:
    if marc.atributos:
        cont2 += 1
        print("handle=%s nombre=%s cables=%d" % (marc.handle, marc.nombre, marc.cables))
        for k, v in marc.atributos.items():
            print("    %s = %r" % (k, v))
        if cont2 >= 10:
            break
print("Marcadores con atributos: %d totales" % cont2)

print("\n=== Tags de atributo vistos (todos) ===")
tags = set()
for disp in contenido.dispositivos:
    tags.update(disp.atributos.keys())
for marc in contenido.marcadores:
    tags.update(marc.atributos.keys())
print(sorted(tags))

print("\n=== Dispositivos totales:", len(contenido.dispositivos))
print("=== Marcadores totales:", len(contenido.marcadores))
print("=== Polilineas totales:", len(contenido.polilineas))
