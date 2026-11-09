# -*- coding: utf-8 -*-
"""
REVIT_CONEXION_VALIDA_v01.py — Validación de conexión directa con Revit
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6

Valida que se puede conectar a una instancia de Revit ejecutándose
y contar elementos por categoría usando pyRevit + Revit API.

NOTA (IronPython 2.7): no usar f-strings, type hints, ni requests/bs4.
Usar .format() y concatenación de strings.

USO (desde dentro de Revit con pyRevit):
  pyrevit run REVIT_CONEXION_VALIDA_v01.py

O desde RevitPythonShell dentro de Revit.


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    ElementCategoryFilter,
)

# pyRevit provee __revit__ como UIApplication.
app = __revit__.Application
uidoc = __revit__.ActiveUIDocument

# Intentar obtener documento activo. En el contexto de `pyrevit run`,
# ActiveUIDocument puede ser None aunque haya un documento abierto.
# En ese caso, usamos el primer documento de la colección app.Documents.
doc = None
if uidoc is not None:
    doc = uidoc.Document
else:
    try:
        docs = app.Documents
        if docs is not None and docs.Size > 0:
            doc = docs.get_Item(0)
    except Exception:
        doc = None

# Nombres de categorías BuiltInCategory a intentar (eléctricas y de modelo).
# Se usan con getattr para evitar fallar si una categoría no existe en la
# versión de Revit instalada.
NOMBRES_CATEGORIAS_ELECTRICAS = [
    "OST_ElectricalEquipment",
    "OST_LightingFixtures",
    "OST_ElectricalPanel",
    "OST_ElectricalCircuit",
    "OST_Conduit",
    "OST_CableTray",
    "OST_Switches",
    "OST_ElectricalFixture",
]

NOMBRES_CATEGORIAS_MODELO = [
    "OST_Walls",
    "OST_Floors",
    "OST_Ceilings",
    "OST_StructuralColumns",
    "OST_StructuralFraming",
]


def _obtener_categoria(nombre):
    """Intenta obtener una BuiltInCategory por nombre; devuelve None si no existe."""
    try:
        return getattr(BuiltInCategory, nombre)
    except AttributeError:
        return None


def contar_por_categoria(doc, nombres_categorias):
    """Cuenta elementos por nombre de BuiltInCategory en el documento activo."""
    resultados = {}
    for nombre in nombres_categorias:
        bic = _obtener_categoria(nombre)
        if bic is None:
            resultados[nombre] = "CATEGORIA_NO_DISPONIBLE"
            continue
        try:
            filtro = ElementCategoryFilter(bic)
            collector = FilteredElementCollector(doc)
            collector.WherePasses(filtro)
            # Excluir elementos de tipo (solo instancias)
            elementos = []
            for e in collector.ToElements():
                if not e.IsElementType:
                    elementos.append(e)
            resultados[nombre] = len(elementos)
        except Exception as exc:
            resultados[nombre] = "ERROR: " + str(exc)
    return resultados


def main():
    print("=" * 60)
    print("VALIDACIÓN DE CONEXIÓN CON REVIT — RevitElectrico")
    print("=" * 60)
    print("Aplicación Revit: {}".format(app))
    print("Versión: {}".format(app.VersionNumber))

    if doc is None:
        print()
        print("ADVERTENCIA: No hay un documento de Revit activo abierto.")
        print("La conexión con Revit funciona, pero no hay modelo cargado.")
        print("Abra un archivo .rvt en Revit y vuelva a ejecutar este script.")
        print("=" * 60)
        print("Conexión con Revit: PARCIAL (sin documento activo)")
        return {
            "conectado": True,
            "documento_activo": False,
            "version": app.VersionNumber,
        }

    print("Documento: {}".format(doc.Title))
    print("Ruta: {}".format(doc.PathName))
    print("Unidades: {}".format(doc.GetUnits()))
    print()

    print("--- Elementos eléctricos ---")
    electricos = contar_por_categoria(doc, NOMBRES_CATEGORIAS_ELECTRICAS)
    for nombre, conteo in electricos.items():
        print("  {:28s}: {}".format(nombre, conteo))

    print()
    print("--- Elementos de modelo BIM ---")
    modelo = contar_por_categoria(doc, NOMBRES_CATEGORIAS_MODELO)
    for nombre, conteo in modelo.items():
        print("  {:28s}: {}".format(nombre, conteo))

    total_electricos = 0
    for v in electricos.values():
        if isinstance(v, int):
            total_electricos += v

    total_modelo = 0
    for v in modelo.values():
        if isinstance(v, int):
            total_modelo += v

    print()
    print("=" * 60)
    print("TOTAL elementos eléctricos: {}".format(total_electricos))
    print("TOTAL elementos de modelo:  {}".format(total_modelo))
    print("=" * 60)
    print("Conexión con Revit: EXITOSA")

    return {
        "conectado": True,
        "documento_activo": True,
        "documento": doc.Title,
        "electricos": electricos,
        "modelo": modelo,
        "total_electricos": total_electricos,
        "total_modelo": total_modelo,
    }


if __name__ == "__main__":
    resultado = main()
