# -*- coding: utf-8 -*-
"""
F6_VERIFICAR_DISPOSITIVOS_E06_v01.py
====================================
Verificador INDEPENDIENTE y de SOLO LECTURA para el apartamento E06 del Piso 5.

No crea, no mueve, no borra, no abre transaccion. Solo lee y reporta la verdad
del modelo tal como esta, para poder comparar contra cualquier reporte de script.

USO EN LA CONSOLA pyRevit DE REVIT
----------------------------------
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\F6_VERIFICAR_DISPOSITIVOS_E06_v01.py").read())

SALIDA
------
D:\\Work\\PROJECTS\\RevitElectrico\\data\\verificacion_E06_estado_real.json

QUE MIDE POR CADA ELEMENTO
--------------------------
  z_abs_m          -> Location.Point.Z convertido a metros (LA VERDAD GEOMETRICA)
  level_nombre     -> nombre del Level asociado al elemento
  level_elev_m     -> elevacion de ese Level en metros
  elevation_m      -> parametro "Elevation from Level" en metros (si aplica)
  offset_host_m    -> parametro "Offset from Host" en metros (si aplica)
  cumple_z         -> True si |z_abs_m - z_objetivo| <= tolerancia

INTERPRETACION CLAVE
---------------------
Si offset_host_m es correcto pero z_abs_m es 0.00, el elemento esta restringido
a un host y su Z no es absoluta: esa es exactamente la falla que hay que evitar.
Si level_elev_m + elevation_m != z_abs_m, el elemento no esta donde dice el nivel.
"""

import clr
import json
import os
import datetime

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

_DB = __import__("Autodesk.Revit.DB", fromlist=["*"])

XYZ = _DB.XYZ
FilteredElementCollector = _DB.FilteredElementCollector
FamilyInstance = _DB.FamilyInstance
Level = _DB.Level
BuiltInParameter = _DB.BuiltInParameter

SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\verificacion_E06_estado_real.json"
DATASET_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\E06_dispositivos_para_crear.json"

NIVEL_NOMBRE = "Piso 5"
LOTE_PARAM = "RevitElectrico_Lote"
LOTE_GUID = "46c3f138-025d-47d4-b24a-41cd21181a58"
TOL_M = 0.01
FT_PER_M = 3.280839895

# Ventana XY del apartamento E06 (margen de 20 cm sobre el dataset)
XY_MIN_X = 0.35
XY_MAX_X = 6.75
XY_MIN_Y = 9.30
XY_MAX_Y = 17.45


def ft2m(ft):
    return ft / FT_PER_M


def eid_int(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        pass
    try:
        return int(eid)
    except Exception:
        return int(str(eid))


def leer_parametro_m(fi, bip):
    """Lee un parametro de longitud y lo devuelve en metros, o None."""
    try:
        p = fi.get_Parameter(bip)
        if p is None:
            return None
        v = p.AsDouble()
        if v is None:
            return None
        return ft2m(v)
    except Exception:
        return None


def leer_parametro_str(fi, bip):
    try:
        p = fi.get_Parameter(bip)
        if p is None:
            return None
        v = p.AsString()
        return v
    except Exception:
        return None


def cargar_objetivos():
    if not os.path.exists(DATASET_JSON):
        return []
    with open(DATASET_JSON, "r") as f:
        ds = json.load(f)
    return ds.get("dispositivos", [])


def verificar_e06(doc):
    salida = {
        "script": "F6_VERIFICAR_DISPOSITIVOS_E06_v01",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": None,
        "ruta": None,
        "nivel_esperado": NIVEL_NOMBRE,
        "lote_guid": LOTE_GUID,
        "tol_m": TOL_M,
        "ventana_xy": [XY_MIN_X, XY_MAX_X, XY_MIN_Y, XY_MAX_Y],
        "total_en_ventana": 0,
        "total_con_guid_lote": 0,
        "total_con_parametro": 0,
        "por_categoria": {},
        "por_z_absoluta": {},
        "elementos": [],
    }

    try:
        salida["documento"] = doc.Title
        salida["ruta"] = doc.PathName
    except Exception:
        pass

    print("")
    print("=" * 96)
    print(" VERIFICACION E06 - SOLO LECTURA")
    print("=" * 96)
    print(" Documento : %s" % salida["documento"])
    print(" Ruta      : %s" % salida["ruta"])
    print("")

    # Nivel de referencia
    nivel_ref = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name == NIVEL_NOMBRE:
            nivel_ref = lv
            break
    if nivel_ref is not None:
        print(" Nivel '%s': id=%d elev=%.4f m" % (NIVEL_NOMBRE, eid_int(nivel_ref.Id), ft2m(nivel_ref.Elevation)))
    else:
        print(" [AVISO] Nivel '%s' NO encontrado en el documento." % NIVEL_NOMBRE)
    print("")

    # Mapa de niveles para no consultar el documento en cada elemento
    niveles = {}
    for lv in FilteredElementCollector(doc).OfClass(Level):
        niveles[eid_int(lv.Id)] = (lv.Name, ft2m(lv.Elevation))

    objetivos = cargar_objetivos()
    print(" Objetivos del dataset: %d" % len(objetivos))
    print("")

    encabezado = "%4s %-22s %-20s %8s %8s %9s %9s %6s" % (
        "#", "categoria", "familia", "z_abs", "level", "elev_lvl", "off_host", "guid")
    print(encabezado)
    print("-" * 96)

    idx = 0
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if loc is None or not hasattr(loc, "Point"):
                continue
            p = loc.Point
            xm = ft2m(p.X)
            ym = ft2m(p.Y)
            if not (XY_MIN_X <= xm <= XY_MAX_X and XY_MIN_Y <= ym <= XY_MAX_Y):
                continue
        except Exception:
            continue

        idx += 1

        cat = ""
        try:
            cat = fi.Category.Name if fi.Category else ""
        except Exception:
            pass

        fam = ""
        tipo = ""
        try:
            fam = fi.Family.Name if fi.Family else ""
            tipo = fi.Symbol.Name if fi.Symbol else ""
        except Exception:
            pass

        z_abs = ft2m(p.Z)

        # Level del elemento
        level_nombre = ""
        level_elev = None
        try:
            lid = eid_int(fi.LevelId)
            if lid in niveles:
                level_nombre, level_elev = niveles[lid]
        except Exception:
            pass

        elevation_m = leer_parametro_m(fi, BuiltInParameter.INSTANCE_ELEVATION_PARAM)
        offset_host_m = leer_parametro_m(fi, BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)

        # GUID del lote
        guid = None
        tiene_param = False
        try:
            prm = fi.LookupParameter(LOTE_PARAM)
            if prm is not None:
                tiene_param = True
                try:
                    guid = prm.AsString()
                except Exception:
                    guid = None
        except Exception:
            pass

        if tiene_param:
            salida["total_con_parametro"] += 1
        if guid == LOTE_GUID:
            salida["total_con_guid_lote"] += 1

        salida["por_categoria"][cat] = salida["por_categoria"].get(cat, 0) + 1
        zk = "%.2f" % z_abs
        salida["por_z_absoluta"][zk] = salida["por_z_absoluta"].get(zk, 0) + 1

        salida["elementos"].append({
            "n": idx,
            "element_id": eid_int(fi.Id),
            "unique_id": str(fi.UniqueId),
            "categoria": cat,
            "familia": fam,
            "tipo": tipo,
            "x_m": round(xm, 4),
            "y_m": round(ym, 4),
            "z_abs_m": round(z_abs, 4),
            "level_nombre": level_nombre,
            "level_elev_m": round(level_elev, 4) if level_elev is not None else None,
            "elevation_m": round(elevation_m, 4) if elevation_m is not None else None,
            "offset_host_m": round(offset_host_m, 4) if offset_host_m is not None else None,
            "tiene_parametro_lote": tiene_param,
            "guid_lote": guid,
        })

        print("%4d %-22s %-20s %8.3f %8s %9s %9s %6s" % (
            idx,
            cat[:22],
            fam[:20],
            z_abs,
            (level_nombre or "-")[:8],
            ("%.2f" % level_elev) if level_elev is not None else "-",
            ("%.2f" % offset_host_m) if offset_host_m is not None else "-",
            "SI" if guid == LOTE_GUID else ("--" if tiene_param else "no"),
        ))

    salida["total_en_ventana"] = idx

    print("-" * 96)
    print("")
    print(" RESUMEN")
    print("   elementos en ventana E06 : %d" % salida["total_en_ventana"])
    print("   con parametro '%s' : %d" % (LOTE_PARAM, salida["total_con_parametro"]))
    print("   con GUID del lote        : %d" % salida["total_con_guid_lote"])
    print("")
    print(" Distribucion por categoria:")
    for k in sorted(salida["por_categoria"].keys()):
        print("   %-30s %d" % (k or "(sin categoria)", salida["por_categoria"][k]))
    print("")
    print(" Distribucion por Z absoluta (m):")
    for k in sorted(salida["por_z_absoluta"].keys()):
        print("   z=%8s  -> %d elementos" % (k, salida["por_z_absoluta"][k]))
    print("")

    # Comparacion contra objetivos
    if objetivos:
        print(" COMPARACION CONTRA OBJETIVOS DEL DATASET")
        print("   (se empareja por X/Y con tolerancia de 5 cm)")
        aciertos = 0
        for obj in objetivos:
            mejor = None
            mejor_d = 0.05
            for el in salida["elementos"]:
                d = ((el["x_m"] - obj["x_m"]) ** 2 + (el["y_m"] - obj["y_m"]) ** 2) ** 0.5
                if d < mejor_d:
                    mejor_d = d
                    mejor = el
            if mejor is None:
                continue
            if abs(mejor["z_abs_m"] - obj["z_abs_m"]) <= TOL_M:
                aciertos += 1
        salida["objetivos_cumplidos"] = aciertos
        salida["objetivos_totales"] = len(objetivos)
        print("   objetivos con Z correcta: %d / %d" % (aciertos, len(objetivos)))
        print("")

    try:
        carpeta = os.path.dirname(SALIDA_JSON)
        if carpeta and not os.path.exists(carpeta):
            os.makedirs(carpeta)
        with open(SALIDA_JSON, "w") as f:
            json.dump(salida, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(" JSON: %s" % SALIDA_JSON)
    except Exception as exc:
        print(" [ERROR] No se pudo escribir JSON: %s" % str(exc)[:200])

    print("")
    return salida


if __name__ == "__main__" or True:
    try:
        _doc = __revit__.ActiveUIDocument.Document
    except Exception:
        _doc = None
    if _doc is not None:
        verificar_e06(_doc)
    else:
        print("[F6] Ejecuta esto dentro de la consola pyRevit de Revit.")
