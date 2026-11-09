
# -*- coding: utf-8 -*-
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    Options,
    Solid,
    BooleanOperationsUtils,
    ModificationOutsideTransactionException,
)
import json
import os


def _solido_elemento(elemento, doc):
    """Obtiene el solido de geometria de un elemento.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
    try:
        opt = Options()
        opt.ComputeReferences = True
        opt.DetailLevel = 1  # Fine
        geo = elemento.get_Geometry(opt)
        if geo is None:
            return None
        for obj in geo:
            if isinstance(obj, Solid):
                if obj.Volume > 0:
                    return obj
            # También revisar GeometryInstance
            try:
                from Autodesk.Revit.DB import GeometryInstance
                if isinstance(obj, GeometryInstance):
                    geo_inst = obj.GetInstanceGeometry()
                    if geo_inst:
                        for o2 in geo_inst:
                            if isinstance(o2, Solid) and o2.Volume > 0:
                                return o2
            except Exception:
                pass
    except Exception:
        pass
    return None


def _hay_choque(solido_a, solido_b, tolerancia_mm=0.0):
    """Verifica si dos solidos se intersectan."""
    try:
        if solido_a is None or solido_b is None:
            return False
        resultado = BooleanOperationsUtils.ExecuteBooleanOperation(
            solido_a, solido_b, 0  # 0 = Union, but we check volume change
        )
        # Mejor: verificar si el volumen de interseccion es > 0
        interseccion = BooleanOperationsUtils.ExecuteBooleanOperation(
            solido_a, solido_b, 2  # 2 = Intersect
        )
        if interseccion is not None and interseccion.Volume > 0.0001:
            return True
    except Exception:
        pass
    return False


def clash_deteccion(doc, json_out=None):
    print("CLASH DETECTION - REVIT 2026")
    print("=" * 60)

    # Recopilar elementos por categoria
    categorias = {
        "electrico": BuiltInCategory.OST_Conduit,
        "hvac": BuiltInCategory.OST_DuctCurves,
        "plomeria": BuiltInCategory.OST_PipeCurves,
        "estructura": BuiltInCategory.OST_StructuralFraming,
    }

    elementos_por_cat = {}
    for nombre, bic in categorias.items():
        try:
            elems = FilteredElementCollector(doc).OfCategory(bic).ToElements()
            elementos_por_cat[nombre] = elems
            print("{:12s} - {:4d} elementos".format(nombre, len(elems)))
        except Exception as exc:
            print("{:12s} - ERROR: {}".format(nombre, exc))
            elementos_por_cat[nombre] = []

    print("=" * 60)

    # Obtener solidos para cada elemento
    solidos = {}
    for nombre, elems in elementos_por_cat.items():
        solidos[nombre] = {}
        for e in elems:
            s = _solido_elemento(e, doc)
            if s is not None:
                solidos[nombre][e.Id.ToString()] = {"elemento": e, "solido": s}

    # Pares a verificar (electrico vs otros)
    pares = [
        ("electrico", "hvac"),
        ("electrico", "plomeria"),
        ("electrico", "estructura"),
    ]

    choques = []
    total_verificados = 0

    for cat_a, cat_b in pares:
        print("\nVerificando {} vs {}...".format(cat_a, cat_b))
        for id_a, info_a in solidos.get(cat_a, {}).items():
            for id_b, info_b in solidos.get(cat_b, {}).items():
                total_verificados += 1
                if _hay_choque(info_a["solido"], info_b["solido"]):
                    choque = {
                        "categoria_a": cat_a,
                        "elemento_a": id_a,
                        "nombre_a": _nombre_elemento(info_a["elemento"]),
                        "categoria_b": cat_b,
                        "elemento_b": id_b,
                        "nombre_b": _nombre_elemento(info_b["elemento"]),
                    }
                    choques.append(choque)
                    print("  CHOQUE: {} ({}) vs {} ({})".format(
                        id_a, choque["nombre_a"], id_b, choque["nombre_b"]))

    print("\n" + "=" * 60)
    print("Total pares verificados: {}".format(total_verificados))
    print("Choques encontrados: {}".format(len(choques)))
    print("=" * 60)

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "total_pares_verificados": total_verificados,
                "choques_encontrados": len(choques),
                "choques": choques,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return choques


def _nombre_elemento(elemento):
    try:
        n = elemento.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = elemento.get_Parameter(
            __import__("Autodesk.Revit.DB", fromlist=["BuiltInParameter"]).BuiltInParameter.ALL_MODEL_TYPE_NAME
        )
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"

