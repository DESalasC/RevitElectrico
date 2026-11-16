# -*- coding: utf-8 -*-
"""Arregla el título del visor 3D."""
p = r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\ruteo\visor_3d.py"
s = open(p, encoding="utf-8").read()
viejo = '''        titulo = (
            "%s · %s · %s · %d cables · %.2f m"
            + (" · RED %s" if t.red else "")
            + (" · EN REVISION" if en_revision else "")
        ) % (
            t.id, t.servicio, t.diametro_pulgadas, t.cables, t.largo_m,
            html.escape(t.red) if t.red else ""
        )
'''
nuevo = '''        titulo_plano = (
            "%s · %s · %s · %d cables · %.2f m"
            % (t.id, t.servicio, t.diametro_pulgadas, t.cables, t.largo_m)
        )
        if t.red:
            titulo_plano += " · RED %s" % html.escape(t.red)
        if en_revision:
            titulo_plano += " · EN REVISION"
'''
assert viejo in s, "bloque viejo no encontrado"
s = s.replace(viejo, nuevo)
open(p, "w", encoding="utf-8").write(s)
print("REPLACEMENT OK")
