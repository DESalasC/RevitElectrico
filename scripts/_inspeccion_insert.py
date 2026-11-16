# -*- coding: utf-8 -*-
"""Inspeccion profunda de un INSERT con atributos en el DXF de F 02."""
import ezdxf

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf"
doc = ezdxf.readfile(RUTA)
msp = doc.modelspace()

cont = 0
for entidad in msp:
    if entidad.dxftype() != "INSERT":
        continue
    try:
        if not getattr(entidad, "has_attrib", False) or not entidad.has_attrib:
            continue
    except Exception:
        continue

    cont += 1
    if cont > 3:
        break

    print("=== INSERT handle=%s nombre=%s ===" % (entidad.dxf.handle, entidad.dxf.name))
    print("   insert.xyz=%s" % (entidad.dxf.insert,))
    print("   has_attrib=%s" % entidad.has_attrib)
    try:
        attribs = list(entidad.attribs)
        print("   num attribs=%d" % len(attribs))
    except Exception as e:
        print("   ERROR listando attribs: %s" % e)
        continue
    for attrib in attribs:
        print("   attrib tag=%r text=%r prompt=%r def=%r layer=%s"
              % (attrib.dxf.tag, attrib.dxf.text, attrib.dxf.prompt,
                 attrib.dxf.text if hasattr(attrib.dxf, "text") else "?",
                 attrib.dxf.layer))
        print("      dxf attrs keys sample:", [k for k in attrib.dxf.__dict__.keys() if not k.startswith("_")][:12])

print("\nTotal INSERTs con has_attrib True:", cont)
