# -*- coding: utf-8 -*-
"""F6_CERRAR_SIN_GUARDAR_V03_v01.py - Cierra el documento V03 descartando cambios.

Accion autorizada por el usuario el 2026-11-08 22:22.
Documento: E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt
No guarda. Solo cierra.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Cierre sin guardar para restaurar respaldo.
2. 2026-11-08: autorizado explicitamente por el usuario.
3. Heredado: sin registro previo disponible.
"""
from Autodesk.Revit.DB import FilteredElementCollector

app = __revit__  # noqa: F821
docs = list(app.Application.Documents)
objetivo = None
for d in docs:
    try:
        if "V03" in d.Title:
            objetivo = d
            break
    except Exception:
        pass

if objetivo is None:
    print("No se encontro documento V03 abierto.")
else:
    print("Cerrando sin guardar: " + objetivo.Title)
    objetivo.Close(False)
    print("Documento cerrado.")
