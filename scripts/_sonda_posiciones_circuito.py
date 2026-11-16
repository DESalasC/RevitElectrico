# -*- coding: utf-8 -*-
"""Sonda de posiciones de textos de circuito en Elec-Power-Iden vs dispositivos y polilineas."""
import ezdxf

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf"
doc = ezdxf.readfile(RUTA)
msp = doc.modelspace()

print("=== Textos en Elec-Power-Iden con coordenadas ===")
for entidad in msp:
    if entidad.dxftype() == "TEXT" and entidad.dxf.layer == "Elec-Power-Iden":
        p = entidad.dxf.insert
        print("  texto=%r insert=(%.3f, %.3f, %.3f)" % (entidad.dxf.text, p.x, p.y, p.z))

print("\n=== Dispositivos INSERT con coordenadas (tomadas y iluminacion) ===")
for entidad in msp:
    if entidad.dxftype() == "INSERT" and entidad.dxf.layer in ("ELEC-APPL-TOMAS", "ELEC-APPL-ILUM", "ELEC-Data-Service"):
        p = entidad.dxf.insert
        print("  %-28s capa=%-20s insert=(%.3f, %.3f)" % (entidad.dxf.name, entidad.dxf.layer, p.x, p.y))

print("\n=== Polilineas de tuberia (resumen) ===")
for entidad in msp:
    if entidad.dxftype() == "LWPOLYLINE" and entidad.dxf.layer in ("ELEC-LIGHT-PIPE", "ELEC-POWER- PIPE"):
        pts = entidad.get_points()
        p0 = pts[0]; p1 = pts[-1]
        print("  capa=%-18s handle=%-6s pts=%d inicio=(%.2f,%.2f) fin=(%.2f,%.2f)" %
              (entidad.dxf.layer, entidad.dxf.handle, len(pts), p0[0], p0[1], p1[0], p1[1]))
