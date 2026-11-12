# -*- coding: utf-8 -*-
# RE_VERIFICAR_XY_E06_v01.py
# Verifica, solo por coordenadas {x,y}, qué dispositivos del inventario E06
# coinciden con instancias existentes en SinNivel, y cuáles no.
# SOLO LECTURA: no crea, ni borra, ni modifica nada en Revit.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_VERIFICAR_XY_E06_v01.py")
#   verificar_xy_e06(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
import json, math, os

FEET_PER_METER = 3.280839895
TOLERANCIA_M = 0.10


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _m(ft):
    return ft / FEET_PER_METER


def obtener_nivel_nombre(doc, fi):
    try:
        lid = fi.LevelId
        if lid and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel:
                return nivel.Name
    except Exception:
        pass
    return "SinNivel"


def obtener_nombre_categoria(elemento):
    try:
        cat = elemento.Category
        if cat:
            return cat.Name
    except Exception:
        pass
    return "SinCategoria"


def cargar_inventario_e06(path):
    with open(path, "r") as f:
        datos = json.load(f)
    dispositivos = datos["dispositivos"]
    # Calcular XY en metros Revit aplicando offset DXF->Revit E06
    offset_x = 2.3682
    offset_y = 9.6937
    for disp in dispositivos:
        disp["x_revit_m"] = disp["x"] + offset_x
        disp["y_revit_m"] = disp["y"] + offset_y
    return dispositivos


def distancia_xy_m(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)


def verificar_xy_e06(doc, inventario_path=None, nivel_sin_nivel_only=True):
    print("=== RE_VERIFICAR_XY_E06_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA (no se modifica nada)")

    if inventario_path is None:
        inventario_path = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"

    # 1. Cargar inventario E06 con XY en metros Revit
    dispositivos_e06 = cargar_inventario_e06(inventario_path)
    print("Dispositivos en inventario E06: {}".format(len(dispositivos_e06)))

    # 2. Recopilar instancias existentes (todas, o solo SinNivel si se pide)
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    existentes = []

    for fi in collector:
        try:
            if fi is None:
                continue
            loc = fi.Location
            punto = None
            if loc and hasattr(loc, "Point"):
                punto = loc.Point
            if punto is None:
                continue

            nivel_nombre = obtener_nivel_nombre(doc, fi)
            if nivel_sin_nivel_only and nivel_nombre != "SinNivel":
                continue

            nombre_familia = ""
            try:
                nombre_familia = fi.Symbol.Family.Name
            except Exception:
                nombre_familia = "Desconocida"

            cat_name = obtener_nombre_categoria(fi)

            existentes.append({
                "id": _eid(fi.Id),
                "familia": nombre_familia,
                "categoria": cat_name,
                "nivel": nivel_nombre,
                "x_ft": punto.X,
                "y_ft": punto.Y,
                "z_ft": punto.Z,
                "x_m": _m(punto.X),
                "y_m": _m(punto.Y),
                "z_m": _m(punto.Z),
            })
        except Exception:
            continue

    print("Instancias existentes en nivel SinNivel: {}".format(len(existentes)))

    # 3. Matching por XY con tolerancia
    coincidencias = []   # E06 dispositivo -> existente SinNivel cercano
    no_coinciden_e06 = []  # E06 dispositivos sin match en SinNivel
    existentes_no_e06 = [] # Existentes SinNivel sin match en E06

    usados_existentes = set()

    for disp in dispositivos_e06:
        mejor = None
        mejor_dist = None
        for ex in existentes:
            if ex["id"] in usados_existentes:
                continue
            d = distancia_xy_m(
                disp["x_revit_m"], disp["y_revit_m"],
                ex["x_m"], ex["y_m"],
            )
            if d <= TOLERANCIA_M and (mejor_dist is None or d < mejor_dist):
                mejor = ex
                mejor_dist = d

        if mejor is not None:
            usados_existentes.add(mejor["id"])
            coincidencias.append({
                "e06_nombre": disp["nombre"],
                "e06_handle": disp.get("handle", ""),
                "e06_x_m": round(disp["x_revit_m"], 4),
                "e06_y_m": round(disp["y_revit_m"], 4),
                "e06_z_absoluto_m": round(13.22 + disp["altura_nominal_m"], 4),
                "existe_id": mejor["id"],
                "existe_familia": mejor["familia"],
                "existe_categoria": mejor["categoria"],
                "existe_x_m": round(mejor["x_m"], 4),
                "existe_y_m": round(mejor["y_m"], 4),
                "existe_z_m": round(mejor["z_m"], 4),
                "dist_xy_m": round(mejor_dist, 4),
                "accion_sugerida": "RELEVELAR_A_PISO_5" if abs(mejor["z_m"] - (13.22 + disp["altura_nominal_m"])) > 0.10 else "YA_EN_PISO_5",
            })
        else:
            no_coinciden_e06.append({
                "e06_nombre": disp["nombre"],
                "e06_handle": disp.get("handle", ""),
                "e06_x_m": round(disp["x_revit_m"], 4),
                "e06_y_m": round(disp["y_revit_m"], 4),
                "e06_z_absoluto_m": round(13.22 + disp["altura_nominal_m"], 4),
            })

    for ex in existentes:
        if ex["id"] not in usados_existentes:
            existentes_no_e06.append({
                "existe_id": ex["id"],
                "existe_familia": ex["familia"],
                "existe_categoria": ex["categoria"],
                "existe_x_m": round(ex["x_m"], 4),
                "existe_y_m": round(ex["y_m"], 4),
                "existe_z_m": round(ex["z_m"], 4),
            })

    # 4. Reporte
    print("\n--- RESULTADOS ---")
    print("Coincidencias XY (E06 <-> SinNivel): {}".format(len(coincidencias)))
    print("E06 sin coincidencia en SinNivel: {}".format(len(no_coinciden_e06)))
    print("Existentes SinNivel sin coincidencia E06 (probablemente F01/F02/otros): {}".format(len(existentes_no_e06)))

    print("\n--- Coincidencias (candidatos a relevelar a Piso 5) ---")
    for c in coincidencias:
        print("  E06={} | Existe ID={} Familia={} | dist_xy={}m | Existe Z={}m | E06 Z_abs={}m | {}".format(
            c["e06_nombre"], c["existe_id"], c["existe_familia"],
            c["dist_xy_m"], c["existe_z_m"], c["e06_z_absoluto_m"], c["accion_sugerida"],
        ))

    print("\n--- E06 sin coincidencia (faltan por crear en Piso 5) ---")
    for d in no_coinciden_e06:
        print("  {} | X={}m Y={}m Z_abs={}m".format(
            d["e06_nombre"], d["e06_x_m"], d["e06_y_m"], d["e06_z_absoluto_m"],
        ))

    print("\n--- Existentes SinNivel NO de E06 (NO TOCAR - probablemente F01/F02) ---")
    for e in existentes_no_e06[:50]:
        print("  ID={} Familia={} X={}m Y={}m Z={}m".format(
            e["existe_id"], e["existe_familia"], e["existe_x_m"], e["existe_y_m"], e["existe_z_m"],
        ))
    if len(existentes_no_e06) > 50:
        print("  ... y {} más".format(len(existentes_no_e06) - 50))

    return {
        "coincidencias": coincidencias,
        "no_coinciden_e06": no_coinciden_e06,
        "existentes_no_e06": existentes_no_e06,
    }


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        verificar_xy_e06(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
