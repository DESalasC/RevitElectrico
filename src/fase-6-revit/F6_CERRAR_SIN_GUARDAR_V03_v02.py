# -*- coding: utf-8 -*-
"""F6_CERRAR_SIN_GUARDAR_V03_v02.py - Programa el cierre de V03 en el proximo Idling.

El agente envuelve el script en una transaccion, por lo que Close(False) directo
falla. Este script registra un manejador de Idling que cierra el documento una
vez que el agente termina.

Accion autorizada por el usuario el 2026-11-08 22:22.

Ultimos tres cambios
--------------------
1. 2026-11-08 v02: cierre diferido por Idling (v01 fallaba dentro de la transaccion).
2. 2026-11-08: autorizado explicitamente por el usuario.
3. Heredado: sin registro previo disponible.
"""


def _cerrar(sender, args):
    try:
        __revit__.Idling -= _cerrar  # noqa: F821
    except Exception:
        pass
    try:
        d = __revit__.ActiveUIDocument.Document  # noqa: F821
        if d is not None and "V03" in d.Title:
            print("Idling: cerrando sin guardar " + d.Title)
            d.Close(False)
            print("Idling: documento cerrado.")
    except Exception as ex:
        print("Idling error: " + str(ex))


try:
    __revit__.Idling += _cerrar  # noqa: F821
    print("Cierre programado para el proximo Idling.")
except Exception as ex:
    print("No se pudo registrar Idling: " + str(ex))
