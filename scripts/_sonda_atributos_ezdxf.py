# -*- coding: utf-8 -*-
"""Lectura directa del DXF con ezdxf: busca tags de atributo y texto en bloques INSERT."""
import sys
import ezdxf

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf"
doc = ezdxf.readfile(RUTA)
msp = doc.modelspace()

tags_vistos = set()
insert_con_atrib = 0
ejemplos = []

for entidad in msp:
    if entidad.dxftype() != "INSERT":
        continue
    try:
        if getattr(entidad, "has_attrib", False) and entidad.has_attrib:
            insert_con_atrib += 1
            for attrib in entidad.attribs:
                tag = attrib.dxf.tag
                texto = attrib.dxf.text or ""
                tags_vistos.add(tag)
                if len(ejemplos) < 15:
                    ejemplos.append((entidad.dxf.handle, entidad.dxf.name, tag, texto[:60]))
    except Exception as e:
        print("Error INSERT %s: %s" % (entidad.dxf.handle, e))

print("INSERTs con atributos:", insert_con_atrib)
print("Tags de atributo distintos:", sorted(tags_vistos))
print("\nEjemplos:")
for h, nombre, tag, texto in ejemplos:
    print("  handle=%s bloque=%s tag=%s texto=%r" % (h, nombre, tag, texto))
