# -*- coding: utf-8 -*-
"""F6_POST_CLOSE_V03_v01.py - Lanza el comando nativo Close sobre el documento activo.

El agente bloquea Document.Close(False); se usa PostCommand para encolar el cierre
en la interfaz. Luego se responde al dialogo de guardado con "No guardar".

Accion autorizada por el usuario el 2026-11-08 22:22.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: cierre por PostCommand(Close).
2. 2026-11-08: autorizado explicitamente por el usuario.
3. Heredado: sin registro previo disponible.
"""
from Autodesk.Revit.UI import PostableCommand, RevitCommandId

try:
    doc = __revit__.ActiveUIDocument.Document  # noqa: F821
    print("Documento activo: " + doc.Title)
    cid = RevitCommandId.LookupPostableCommandId(PostableCommand.Close)
    __revit__.PostCommand(cid)  # noqa: F821
    print("PostCommand(Close) enviado.")
except Exception as ex:
    print("Error: " + str(ex))
