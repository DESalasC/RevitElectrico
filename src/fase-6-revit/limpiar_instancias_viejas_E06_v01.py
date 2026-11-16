# -*- coding: utf-8 -*-
# limpiar_instancias_viejas_E06_v01.py
# Borra instancias eléctricas viejas (v07 y anteriores) del Apartamento E06 / Piso 5
# que quedaron con LevelId = -1 y Z incorrecta.
#
# Criterios de eliminación:
#   - Categoría: Lighting Fixtures o Electrical Fixtures
#   - LevelId = -1 (sin nivel asignado) O Z muy cercano a 0 m
#   - Dentro del rango XY del apartamento E06 (con offset aplicado)
#
# Copiar y pegar en consola IronPython de pyRevit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\limpiar_instancias_viejas_E06_v01.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   limpiar_instancias_viejas_E06(doc)

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory
)
from System import Int64

SCRIPT_VERSION = "limpiar_instancias_viejas_E06_v01-2026-11-12"

def _ft_a_m(ft):
    return ft / 3.280839895

def _m_a_ft(m):
    return m * 3.280839895

# Rango XY del apartamento E06 (metros, con offset DXF->Revit ya aplicado)
# Valores observados en el inventario: X aprox 0.5-5.0, Y aprox 15.0-18.0
# Usamos margen amplio para no dejar ninguna vieja.
E06_X_MIN = -2.0
E06_X_MAX = 8.0
E06_Y_MIN = 13.0
E06_Y_MAX = 20.0

def limpiar_instancias_viejas_E06(doc):
    print("=" * 70)
    print("LIMPIEZA DE INSTANCIAS VIEJAS - APARTAMENTO E06 / PISO 5")
    print("Script: {}".format(SCRIPT_VERSION))
    print("Documento: {}".format(doc.Title))
    print("=" * 70)

    x_min_ft = _m_a_ft(E06_X_MIN)
    x_max_ft = _m_a_ft(E06_X_MAX)
    y_min_ft = _m_a_ft(E06_Y_MIN)
    y_max_ft = _m_a_ft(E06_Y_MAX)
    z_max_ft = _m_a_ft(0.5)  # Z menor a 0.5 m sospechosa (lámparas viejas en suelo)

    # Categorías eléctricas
    cat_lighting = ElementCategoryFilter(BuiltInCategory.OST_LightingFixtures)
    cat_electrical = ElementCategoryFilter(BuiltInCategory.OST_ElectricalFixtures)

    candidatos = []
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            cat_id = fi.Category.Id.IntegerValue if fi.Category else -1
            es_electrica = False
            try:
                if cat_id == int(BuiltInCategory.OST_LightingFixtures):
                    es_electrica = True
                elif cat_id == int(BuiltInCategory.OST_ElectricalFixtures):
                    es_electrica = True
            except Exception:
                es_electrica = False
            if not es_electrica:
                continue

            loc = fi.Location
            if loc is None or not hasattr(loc, 'Point'):
                continue
            p = loc.Point

            # Filtro por rango XY de E06
            if not (x_min_ft <= p.X <= x_max_ft and y_min_ft <= p.Y <= y_max_ft):
                continue

            # Criterio 1: LevelId = -1 (sin nivel)
            nivel_invalido = (fi.LevelId is None) or (fi.LevelId.IntegerValue == -1)

            # Criterio 2: Z muy cercano a 0 m (lámparas viejas en el suelo)
            z_cerca_cero = abs(p.Z) < z_max_ft

            if nivel_invalido or z_cerca_cero:
                candidatos.append({
                    "id": fi.Id.IntegerValue,
                    "nombre": fi.Name if hasattr(fi, 'Name') else '?',
                    "categoria": fi.Category.Name if fi.Category else '?',
                    "nivel_id": fi.LevelId.IntegerValue if fi.LevelId else -1,
                    "x_m": round(_ft_a_m(p.X), 4),
                    "y_m": round(_ft_a_m(p.Y), 4),
                    "z_m": round(_ft_a_m(p.Z), 4),
                })
        except Exception:
            continue

    print("Instancias candidatas a eliminar: {}".format(len(candidatos)))
    for c in candidatos:
        print("  ID={} | Cat={} | LevelId={} | XYZ(m)=({:.4f}, {:.4f}, {:.4f})".format(
            c["id"], c["categoria"], c["nivel_id"], c["x_m"], c["y_m"], c["z_m"]))

    if len(candidatos) == 0:
        print("\nNo se encontraron instancias viejas. Nada que eliminar.")
        return 0

    # Eliminar en una transacción
    from Autodesk.Revit.DB import Transaction
    t = Transaction(doc, "Eliminar instancias viejas E06 Piso 5")
    t.Start()
    eliminadas = 0
    try:
        for c in candidatos:
            try:
                doc.Delete(ElementId(Int64(c["id"])))
                eliminadas += 1
            except Exception as exc:
                print("  ERROR eliminando ID {}: {}".format(c["id"], exc))
        t.Commit()
    except Exception as exc:
        t.RollBack()
        print("ERROR en transacción de eliminación: {}".format(exc))
        return 0

    print("\nInstancias eliminadas: {}".format(eliminadas))
    print("=" * 70)
    return eliminadas


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        limpiar_instancias_viejas_E06(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\limpiar_instancias_viejas_E06_v01.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  limpiar_instancias_viejas_E06(doc)')
