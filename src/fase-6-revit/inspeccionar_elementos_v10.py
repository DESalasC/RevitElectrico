# -*- coding: utf-8 -*-
# INSPECCIONAR_ELEMENTOS_v10.py
# Inspecciona ElementIDs específicos dentro de Revit para ver qué hay realmente en el modelo.
# Copiar y pegar en la consola IronPython de pyRevit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\inspeccionar_elementos_v10.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   inspeccionar_elementos(doc, [5695307, 5695284])

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory
)
from System import Int64

def _m_a_ft(m):
    return m * 3.280839895


def _ft_a_m(ft):
    return ft / 3.280839895


def inspeccionar_elementos(doc, ids):
    print("=" * 70)
    print("INSPECCIÓN DE ELEMENTOS EN MODELO REVIT")
    print("Documento: {}".format(doc.Title))
    print("=" * 70)
    for eid_int in ids:
        eid = ElementId(Int64(eid_int))
        elem = doc.GetElement(eid)
        if elem is None:
            print("\nElementID {}: NO EXISTE en el documento".format(eid_int))
            continue
        print("\n--- ElementID {} ---".format(eid_int))
        print("  Nombre tipo: {}".format(elem.Name if hasattr(elem, 'Name') else '(sin nombre)'))
        print("  Categoría: {}".format(elem.Category.Name if elem.Category else 'Sin categoría'))
        try:
            print("  Nivel: {}".format(elem.Level.Name if elem.Level else 'Sin nivel'))
        except Exception:
            print("  Nivel: (no accesible)")
        try:
            print("  LevelId: {}".format(elem.LevelId))
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
        # Si es FamilyInstance, mostrar información adicional
        if isinstance(elem, FamilyInstance):
            try:
                print("  Es FamilyInstance: Sí")
                print("  Familia símbolo: {}".format(elem.Symbol.Name if elem.Symbol else 'N/A'))
                print("  Familia: {}".format(elem.Symbol.Family.Name if elem.Symbol and elem.Symbol.Family else 'N/A'))
                try:
                    print("  Host: {}".format(elem.Host.Id if elem.Host else 'Sin host'))
                except Exception:
                    print("  Host: (no accesible)")
            except Exception as exc:
                print("  Datos FamilyInstance: (error: {})".format(exc))
    print("\n" + "=" * 70)
    print("FIN DE INSPECCIÓN")
    print("=" * 70)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        inspeccionar_elementos(doc, [5695307, 5695284])
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\inspeccionar_elementos_v10.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  inspeccionar_elementos(doc, [5695307, 5695284])')
