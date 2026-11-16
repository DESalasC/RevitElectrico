# -*- coding: utf-8 -*-
# INSPECCIONAR_ELEMENTOS_v11.py
# Inspecciona ElementIDs específicos dentro de Revit, mostrando UniqueId,
# categoria, nivel, posicion XYZ, host y familia/simbolo.
# Copiar y pegar en la consola IronPython de pyRevit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\inspeccionar_elementos_v11.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   inspeccionar_elementos(doc, [5695293, 5695308])

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory
)
from System import Int64

SCRIPT_VERSION = "inspeccionar_elementos_v11-2026-11-12"


def _ft_a_m(ft):
    return ft / 3.280839895


def inspeccionar_elementos(doc, ids):
    print("=" * 80)
    print("INSPECCIÓN DE ELEMENTOS EN MODELO REVIT")
    print("Script: {}".format(SCRIPT_VERSION))
    print("Documento: {}".format(doc.Title))
    print("Fecha y hora: 2026-11-12 18:46")
    print("=" * 80)
    for eid_int in ids:
        eid = ElementId(Int64(eid_int))
        elem = doc.GetElement(eid)
        if elem is None:
            print("\nElementID {}: NO EXISTE en el documento".format(eid_int))
            continue
        print("\n--- ElementID {} ---".format(eid_int))
        print("  UniqueId: {}".format(elem.UniqueId))
        print("  Nombre tipo: {}".format(elem.Name if hasattr(elem, 'Name') else '(sin nombre)'))
        print("  Categoría: {}".format(elem.Category.Name if elem.Category else 'Sin categoría'))
        try:
            print("  Nivel: {}".format(elem.Level.Name if elem.Level else 'Sin nivel'))
        except Exception:
            print("  Nivel: (no accesible)")
        try:
            print("  LevelId: {}".format(elem.LevelId.IntegerValue if elem.LevelId else -1))
        except Exception:
            print("  LevelId: (no accesible)")
        try:
            loc = elem.Location
            if loc is not None and hasattr(loc, 'Point'):
                p = loc.Point
                print("  Posición XYZ (ft): ({:.4f}, {:.4f}, {:.4f})".format(p.X, p.Y, p.Z))
                print("  Posición XYZ (m):  ({:.4f}, {:.4f}, {:.4f})".format(
                    _ft_a_m(p.X), _ft_a_m(p.Y), _ft_a_m(p.Z)))
            else:
                print("  Posición: (sin Location.Point)")
        except Exception as exc:
            print("  Posición: (error: {})".format(exc))
        if isinstance(elem, FamilyInstance):
            try:
                print("  Es FamilyInstance: Sí")
                print("  Familia símbolo: {}".format(elem.Symbol.Name if elem.Symbol else 'N/A'))
                print("  Familia: {}".format(elem.Symbol.Family.Name if elem.Symbol and elem.Symbol.Family else 'N/A'))
                try:
                    print("  Host: {}".format(elem.Host.Id.IntegerValue if elem.Host else 'Sin host'))
                    if elem.Host is not None:
                        print("  Host UniqueId: {}".format(elem.Host.UniqueId))
                        print("  Host Categoría: {}".format(elem.Host.Category.Name if elem.Host.Category else 'N/A'))
                except Exception:
                    print("  Host: (no accesible)")
                # Parámetros compartidos de trazabilidad
                try:
                    param_lote = elem.LookupParameter("RevitElectrico_Lote")
                    if param_lote is not None:
                        print("  Parámetro lote: {}".format(param_lote.AsString() if param_lote.AsString() else '(vacío)'))
                    else:
                        print("  Parámetro lote: (no existe en este elemento)")
                except Exception:
                    pass
            except Exception as exc:
                print("  Datos FamilyInstance: (error: {})".format(exc))
    print("\n" + "=" * 80)
    print("FIN DE INSPECCIÓN")
    print("=" * 80)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        inspeccionar_elementos(doc, [5695293, 5695308])
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\inspeccionar_elementos_v11.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  inspeccionar_elementos(doc, [5695293, 5695308])')
