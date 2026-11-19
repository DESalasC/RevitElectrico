# -*- coding: utf-8 -*-
"""
ejemplo_colocacion_face_based.py
================================
Ejemplo de uso de MiAddin.dll desde IronPython (pyRevit) para colocar
familias face-based usando la sobrecarga correcta de NewFamilyInstance.

Reemplaza al script v69 que fallaba con:
    "Reference direction is parallel to face normal"

Diferencia clave:
    v69 usaba: doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
               (sobrecarga XYZ,XYZ - da error si direction es paralelo a normal)
    v70 usa:   MiAddin.Placer.PlaceFaceBased(doc, face_ref, uv, param, sym)
               (sobrecarga UV,double - determinista, no requiere direction)

Requisitos previos:
    1. Compilar MiAddin.dll (ver README.md en esta misma carpeta).
    2. Colocar MiAddin.dll en una ruta accesible (ej: D:\\Work\\PROJECTS\\RevitElectrico\\bin\\).
    3. Revit 2026 abierto con el documento STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt.
    4. pyRevit Python Shell ejecutando IronPython 2.7.

Ejecucion (en pyRevit Python Shell dentro de Revit 2026):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\ejemplo_colocacion_face_based.py").read())
    colocar_F01_con_wrapper(doc, plan_json=r"data\\plan_F01_v01.json")
"""

import os
import sys
import math
import json

# --- Cargar el wrapper via loader robusto -----------------------------------
# MiAddinLoader usa clr.AddReferenceByPath(ruta_absoluta), que es lo que
# realmente funciona desde IronPython 2.7. NO usar clr.AddReference("name")
# porque lanza: "Could not add reference to assembly MiAddin".
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit"
_LOADER = os.path.join(_HERE, "MiAddinLoader.py")
if not os.path.exists(_LOADER):
    _LOADER = os.path.join(os.environ.get("REVITELECTRICO_ROOT",
                                          r"D:\Work\PROJECTS\RevitElectrico"),
                          "src", "fase-6-revit", "MiAddinLoader.py")
exec(open(_LOADER).read())
# Ahora `Placer` esta disponible en el scope global.

# Tipos Revit (cargados por pyRevit)
from Autodesk.Revit.DB import (  # noqa: E402
    Transaction,
    FilteredElementCollector,
    FamilySymbol,
    Wall,
    Ceiling,
    Reference,
    XYZ,
    UV,
    ElementId,
    BuiltInCategory,
)


# --- Helpers (mismos del script v68, conservados) ---------------------------

def _obtener_faces_muro(wall):
    """Devuelve lista de (face, normal) de un muro (caras verticales)."""
    from Autodesk.Revit.DB import Options
    opt = Options()
    geom = wall.get_Geometry(opt)
    caras = []
    for obj in geom:
        if obj.GetType().Name == "Solid":
            for f in obj.Faces:
                try:
                    n = f.Normal
                    # Solo caras verticales (no top/bottom)
                    if abs(n.Z) < 0.9:
                        caras.append((f, n))
                except Exception:
                    continue
    return caras


def _encontrar_cara_cercana(faces, punto):
    """De una lista de (face, normal), devuelve la mas cercana al punto XYZ."""
    mejor_face = None
    mejor_d = 1e9
    for f, n in faces:
        try:
            r = f.Project(punto)
            if r is not None and r.XYZPoint is not None:
                p = r.XYZPoint
                d = math.sqrt(
                    (p.X - punto.X) ** 2 +
                    (p.Y - punto.Y) ** 2 +
                    (p.Z - punto.Z) ** 2
                )
                if d < mejor_d:
                    mejor_d = d
                    mejor_face = f
        except Exception:
            continue
    return mejor_face, mejor_d


def _obtener_muro_por_punto(doc, punto, max_dist=0.5):
    """Encuentra el muro mas cercano al punto XY dado (distancia horizontal)."""
    collector = FilteredElementCollector(doc).OfClass(Wall)
    mejor = None
    mejor_d = max_dist
    for w in collector:
        try:
            loc = w.Location
            if loc.GetType().Name == "LocationCurve":
                curva = loc.Curve
                # Proyectar punto sobre la curva
                r = curva.Project(punto)
                if r is not None and r.XYZPoint is not None:
                    p = r.XYZPoint
                    d = math.sqrt(
                        (p.X - punto.X) ** 2 + (p.Y - punto.Y) ** 2
                    )
                    if d < mejor_d:
                        mejor_d = d
                        mejor = w
        except Exception:
            continue
    return mejor, mejor_d


def _activar_symbol(symbol):
    """Activa el FamilySymbol si no lo esta."""
    if not symbol.IsActive:
        symbol.Activate()


# --- Funcion principal: colocacion con wrapper C# -----------------------------

def colocar_uno(doc, dispositivo):
    """
    Coloca UN dispositivo face-based usando MiAddin.Placer.

    dispositivo: dict con claves
        - placement_pt: [x, y, z] en metros (coordenadas Revit)
        - family_name: str (ej: "M_Toma doble")
        - symbol_name: str (ej: "Standard")
        - rotation_deg: float (no usado aqui; la rotacion se aplica despues)

    Devuelve: dict con
        - ok: bool
        - element_id: int o None
        - error: str o None
        - metodo: "MiAddin.PlaceFaceBased"
    """
    p = dispositivo["placement_pt"]
    punto = XYZ(p[0], p[1], p[2])

    # 1. Encontrar muro host cercano
    muro, dist_muro = _obtener_muro_por_punto(doc, punto)
    if muro is None:
        return {"ok": False, "element_id": None,
                "error": "Muro no encontrado cerca del punto", "metodo": "MiAddin"}

    # 2. Obtener faces verticales del muro
    faces = _obtener_faces_muro(muro)
    if not faces:
        return {"ok": False, "element_id": None,
                "error": "Muro sin faces verticales", "metodo": "MiAddin"}

    # 3. Encontrar la cara mas cercana al punto
    face, dist_face = _encontrar_cara_cercana(faces, punto)
    if face is None:
        return {"ok": False, "element_id": None,
                "error": "Ninguna face proyecta el punto", "metodo": "MiAddin"}

    # 4. Obtener el FamilySymbol
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_ElectricalFixtures))
    sym = None
    for s in col:
        if (s.Family.Name == dispositivo["family_name"] and
                s.Name == dispositivo.get("symbol_name", "Standard")):
            sym = s
            break
    if sym is None:
        return {"ok": False, "element_id": None,
                "error": "FamilySymbol no encontrado: {} / {}".format(
                    dispositivo["family_name"],
                    dispositivo.get("symbol_name", "Standard")),
                "metodo": "MiAddin"}

    # 5. Activar symbol
    _activar_symbol(sym)

    # 6. Diagnostico previo (opcional)
    diag = Placer.DiagnoseSymbol(sym)
    print "  Diag:", diag

    # 7. Colocar via wrapper C# (UNA linea, sin error direction vector)
    try:
        inst = Placer.PlaceFaceBasedAtPoint(doc, face, punto, 0.0, sym)
        if inst is None:
            return {"ok": False, "element_id": None,
                    "error": "Wrapper devolvio null", "metodo": "MiAddin"}

        # 8. Aplicar rotacion final alrededor del eje Z (igual que v69)
        rot_deg = dispositivo.get("rotation_deg", 0.0)
        if abs(rot_deg) > 0.1:
            from Autodesk.Revit.DB import Line, LocationPoint
            loc = inst.Location
            if isinstance(loc, LocationPoint):
                p_loc = loc.Point
                axis = Line.CreateBound(
                    p_loc,
                    XYZ(p_loc.X, p_loc.Y, p_loc.Z + 1.0)
                )
                loc.Rotate(axis, math.radians(rot_deg))

        return {"ok": True, "element_id": inst.Id.IntegerValue,
                "error": None, "metodo": "MiAddin"}

    except Exception as ex:
        return {"ok": False, "element_id": None,
                "error": str(ex), "metodo": "MiAddin"}


def colocar_F01_con_wrapper(doc, plan_json="data\\plan_F01_v01.json",
                            json_out="data\\reporte_colocacion_F01_v70.json"):
    """
    Coloca masivamente los 35 dispositivos del F01 usando MiAddin.dll.
    Reemplaza a colocacion_masiva_F01_v69.py.

    Devuelve: dict resumen {ok, errores, ids}
    """
    root = os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico")
    plan_path = plan_json if os.path.isabs(plan_json) else os.path.join(root, plan_json)
    out_path = json_out if os.path.isabs(json_out) else os.path.join(root, json_out)

    print "Wrapper version:", Placer.Version()
    print "Leyendo plan:", plan_path

    with open(plan_path, "r") as f:
        plan = json.load(f)

    dispositivos = plan.get("dispositivos", plan) if isinstance(plan, dict) else plan
    print "Total dispositivos a colocar:", len(dispositivos)

    resultados = []
    ok_count = 0
    err_count = 0

    t = Transaction(doc, "Colocar F01 con MiAddin wrapper v70")
    t.Start()

    try:
        for i, d in enumerate(dispositivos):
            print "[{}/{}] {} - {}".format(
                i + 1, len(dispositivos),
                d.get("family_name", "?"),
                d.get("id_bloque", "?"))
            r = colocar_uno(doc, d)
            resultados.append({
                "idx": i,
                "id_bloque": d.get("id_bloque"),
                "family_name": d.get("family_name"),
                "ok": r["ok"],
                "element_id": r["element_id"],
                "error": r["error"],
                "metodo": r["metodo"],
            })
            if r["ok"]:
                ok_count += 1
            else:
                err_count += 1
                print "  ERROR:", r["error"]

        t.Commit()
        print "Transaccion commited."
    except Exception as ex:
        t.RollBack()
        print "ROLLBACK por excepcion:", str(ex)
        raise

    resumen = {
        "total": len(dispositivos),
        "ok": ok_count,
        "errores": err_count,
        "metodo": "MiAddin.Placer.PlaceFaceBasedAtPoint",
        "resultados": resultados,
    }

    with open(out_path, "w") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)

    print "OK:", ok_count, "/ Errores:", err_count
    print "Reporte:", out_path
    return resumen


# --- Hook para ejecucion directa ---------------------------------------------
if __name__ == "__main__":
    # En pyRevit Python Shell, 'doc' esta disponible globalmente.
    # Si no, obtener del uidoc:
    try:
        doc  # noqa: F821
    except NameError:
        from pyrevit import revit
        doc = revit.doc

    colocar_F01_con_wrapper(doc)
