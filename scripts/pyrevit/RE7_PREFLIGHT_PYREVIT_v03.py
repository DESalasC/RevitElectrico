# -*- coding: utf-8 -*-
"""
RE7_PREFLIGHT_PYREVIT_v03.py
Etapa 0 del ruteo F7: reporte de SOLO LECTURA del modelo Revit para validar
antes de crear conduits. NO abre transaccion, NO modifica el documento.

Escribe siempre un log en data/f7_preflight_pyrevit.log y un reporte JSON en
data/f7_preflight_v03.json, aunque la consola no muestre nada.

La escritura del JSON usa System.IO.File.WriteAllText (.NET) para evitar
problemas de códec de IronPython al escribir en disco.

Uso (dentro de Revit 2026, consola de comandos / Python Shell / canal MCP):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\scripts\\pyrevit\\RE7_PREFLIGHT_PYREVIT_v03.py").read())

REVITELECTRICO_ROOT es opcional: si no esta definida se usa
D:\\Work\\PROJECTS\\RevitElectrico.
"""
import datetime
import json
import os
import sys
import traceback

VERSION = "v03"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

IMPORT_ERROR = None
try:
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        BuiltInCategory,
        ElementId,
        FilteredElementCollector,
        Level,
        LocationCurve,
        LocationPoint,
        XYZ,
    )
    from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
    from System import Int64
except Exception:
    IMPORT_ERROR = traceback.format_exc()


def _raiz():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return DEFAULT_ROOT


def _ruta_log():
    candidatos = [os.path.join(_raiz(), "data"),
                  os.environ.get("TEMP", "."),
                  "."]
    for d in candidatos:
        try:
            if not os.path.exists(d):
                os.makedirs(d)
            return os.path.join(d, "f7_preflight_pyrevit.log")
        except Exception:
            continue
    return "f7_preflight_pyrevit.log"


LOG_PATH = _ruta_log()


def _clean_reporte(v):
    """Limpia caracteres no-ASCII de cualquier string del reporte para que
    json.dumps(ensure_ascii=True) no falle en IronPython (cp1252)."""
    if isinstance(v, str):
        return "".join(ch if ord(ch) < 128 else "?" for ch in v)
    if isinstance(v, dict):
        return {_clean_reporte(k): _clean_reporte(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_clean_reporte(x) for x in v]
    return v


def log(msg):
    """Imprime y ademas persiste la linea, sin poder fallar."""
    try:
        print(msg)
    except Exception:
        pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        f = open(LOG_PATH, "ab")
        f.write((str(msg) + "\n").encode("utf-8", "replace"))
        f.close()
    except Exception:
        pass


def escribir_reporte_salida(raiz, reporte):
    """Escribe el reporte JSON siempre, aunque sea parcial o de error.

    Usa System.IO.File.WriteAllText (.NET) para evitar el códec de Python.
    """
    destinos = []
    try:
        d = os.path.join(raiz, "data")
        if not os.path.exists(d):
            os.makedirs(d)
        destinos.append(os.path.join(d, "f7_preflight_v03.json"))
    except Exception:
        pass
    try:
        destinos.append(os.path.join(os.environ.get("TEMP", "."), "f7_preflight_v03.json"))
    except Exception:
        pass
    contenido = json.dumps(_clean_reporte(reporte), ensure_ascii=True, indent=2)
    for salida in destinos:
        try:
            try:
                from System import IO
                IO.File.WriteAllText(salida, contenido, System.Text.Encoding.UTF8)
            except Exception:
                f = open(salida, "wb")
                f.write(contenido.encode("utf-8"))
                f.close()
            log("Reporte guardado en: {}".format(salida))
            return salida
        except Exception as e:
            log("ERROR al escribir {}: {}".format(salida, e))
    return None


def obtener_doc():
    """Intenta obtener el documento activo de Revit desde varios contextos."""
    try:
        app = __revit__
        doc = app.ActiveUIDocument.Document
        log("P3 documento via __revit__.ActiveUIDocument")
        return doc
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        doc = getattr(_revit, "doc", None)
        if doc is not None:
            log("P3 documento via pyrevit.revit.doc")
            return doc
    except Exception:
        pass
    try:
        import clr as _clr
        _clr.AddReference("RevitServices")
        from RevitServices.Persistence import DocumentManager
        inst = DocumentManager.Instance
        if inst is not None and inst.CurrentDBDocument is not None:
            log("P3 documento via RevitServices.DocumentManager")
            return inst.CurrentDBDocument
    except Exception:
        pass
    return None


def nombre_tipo(elemento):
    try:
        p = elemento.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and not p.IsReadOnly:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    try:
        return elemento.Name
    except Exception:
        return ""


def id_de(elemento):
    eid_val = elemento.Id
    if hasattr(eid_val, "IntegerValue"):
        return int(eid_val.IntegerValue)
    return int(eid_val.Value)


def punto_de(inst):
    """Devuelve (punto, centro_bbox) en pies de Revit, o (None, None)."""
    punto = None
    try:
        loc = inst.Location
        if isinstance(loc, LocationPoint):
            punto = loc.Point
        elif isinstance(loc, LocationCurve):
            punto = loc.Curve.GetEndPoint(0)
    except Exception:
        punto = None
    centro = None
    try:
        bb = inst.get_BoundingBox(None)
        if bb is not None:
            cmin = bb.Min
            cmax = bb.Max
            centro = XYZ(
                (cmin.X + cmax.X) / 2.0,
                (cmin.Y + cmax.Y) / 2.0,
                (cmin.Z + cmax.Z) / 2.0,
            )
    except Exception:
        centro = None
    return punto, centro


def ft_a_mm(p):
    if p is None:
        return None
    return [round(p.X * FT_A_MM, 3), round(p.Y * FT_A_MM, 3), round(p.Z * FT_A_MM, 3)]


def recolectar_niveles(doc):
    out = []
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        out.append({
            "id": id_de(lvl),
            "nombre": lvl.Name,
            "elevacion_ft": round(lvl.Elevation, 4),
            "elevacion_mm": round(lvl.Elevation * FT_A_MM, 3),
        })
    return out


def recolectar_tipos(doc):
    out = []
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        tid = id_de(t)
        valido = False
        try:
            valido = bool(Conduit.IsValidConduitType(doc, ElementId(Int64(tid))))
        except Exception:
            valido = False
        out.append({
            "id": tid,
            "nombre": nombre_tipo(t),
            "valido": valido,
        })
    return out


def recolectar_conduits(doc):
    out = []
    for c in FilteredElementCollector(doc).OfClass(Conduit).ToElements():
        a = b = None
        try:
            loc = c.Location
            if isinstance(loc, LocationCurve):
                curva = loc.Curve
                a = curva.GetEndPoint(0)
                b = curva.GetEndPoint(1)
        except Exception:
            a = b = None
        comentarios = ""
        try:
            p = c.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                comentarios = p.AsString() or ""
        except Exception:
            comentarios = ""
        out.append({
            "id": id_de(c),
            "tipo_id": id_de(doc.GetElement(c.GetTypeId())) if c.GetTypeId() is not None else None,
            "comentarios": comentarios,
            "a_mm": ft_a_mm(a),
            "b_mm": ft_a_mm(b),
        })
    return out


def recolectar_dispositivos(doc):
    out = []
    categorias = (
        ("OST_ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
        ("OST_ElectricalEquipment", BuiltInCategory.OST_ElectricalEquipment),
        ("OST_LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    )
    for nombre_cat, cat in categorias:
        for inst in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
            try:
                sym = doc.GetElement(inst.GetTypeId())
            except Exception:
                sym = None
            nombre = nombre_tipo(sym) if sym is not None else ""
            try:
                familia = sym.Family.Name if sym is not None else ""
            except Exception:
                familia = ""
            punto, centro = punto_de(inst)
            xyz = punto if punto is not None else centro
            out.append({
                "id": id_de(inst),
                "categoria": nombre_cat,
                "familia": familia,
                "tipo": nombre,
                "x_mm": round(xyz.X * FT_A_MM, 3) if xyz is not None else None,
                "y_mm": round(xyz.Y * FT_A_MM, 3) if xyz is not None else None,
                "z_mm": round(xyz.Z * FT_A_MM, 3) if xyz is not None else None,
                "fuente_posicion": "LocationPoint" if punto is not None else ("BBox" if centro is not None else None),
            })
    return out


def main():
    log("=" * 60)
    log("RE7_PREFLIGHT_PYREVIT_{} - SOLO LECTURA (Etapa 0 F7)".format(VERSION))
    log("inicio_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    log("log_path={}".format(LOG_PATH))
    log("=" * 60)

    if IMPORT_ERROR:
        log("ERROR: fallo al importar la API de Revit:")
        log(IMPORT_ERROR)
        escribir_reporte_salida(_raiz(), {"error": IMPORT_ERROR, "version": VERSION})
        return
    log("imports RevitAPI OK")

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo de Revit.")
        log("     Ejecutar dentro de Revit 2026 con un modelo abierto.")
        escribir_reporte_salida(_raiz(), {"error": "sin documento activo", "version": VERSION})
        return

    log("documento={!r} modificado={} solo_lectura={}".format(
        doc.Title, bool(doc.IsModified), bool(doc.IsReadOnly)))

    raiz = _raiz()
    config_path = os.path.join(raiz, "config", "f7_ruteo_v01.json")
    config = {}
    if os.path.exists(config_path):
        try:
            f = open(config_path, "r")
            config = json.load(f)
            f.close()
            log("config cargada: {}".format(config_path))
        except Exception as e:
            log("AVISO: no se pudo leer la config ({}); se usan valores por defecto".format(e))
    else:
        log("AVISO: no existe {}; se usan valores por defecto".format(config_path))

    log("recolectando niveles / tipos conduit / conduits / dispositivos ...")
    niveles = recolectar_niveles(doc)
    tipos = recolectar_tipos(doc)
    conduits = recolectar_conduits(doc)
    dispositivos = recolectar_dispositivos(doc)

    nivel_cfg = config.get("nivel", {})
    elev_objetivo_mm = float(nivel_cfg.get("elevacion_m", 13.22)) * 1000.0
    tol_mm = float(nivel_cfg.get("tolerancia_mm", 1.0))
    nivel_p5 = {"encontrado": False}
    cercano = None
    cercano_delta = None
    for n in niveles:
        delta = abs(n["elevacion_mm"] - elev_objetivo_mm)
        if cercano_delta is None or delta < cercano_delta:
            cercano = n
            cercano_delta = delta
        if delta <= tol_mm:
            nivel_p5 = {
                "encontrado": True,
                "id": n["id"],
                "nombre": n["nombre"],
                "elevacion_mm": n["elevacion_mm"],
                "delta_mm": round(delta, 3),
            }
            break
    if not nivel_p5.get("encontrado") and cercano is not None:
        nivel_p5 = {
            "encontrado": False,
            "cercano": cercano["nombre"],
            "elevacion_mm": cercano["elevacion_mm"],
            "delta_mm": round(cercano_delta, 3),
        }

    reporte = {
        "version": VERSION,
        "script": "RE7_PREFLIGHT_PYREVIT_v03",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {
            "titulo": doc.Title,
            "ruta": doc.PathName,
            "modificado": bool(doc.IsModified),
            "solo_lectura": bool(doc.IsReadOnly),
        },
        "nivel_piso5": nivel_p5,
        "niveles": niveles,
        "tipos_conduit": tipos,
        "conduits": conduits,
        "dispositivos": dispositivos,
        "resumen": {
            "n_niveles": len(niveles),
            "n_tipos_conduit": len(tipos),
            "n_conduits": len(conduits),
            "n_dispositivos": len(dispositivos),
        },
    }

    escribir_reporte_salida(raiz, reporte)

    log("")
    log("RESUMEN: {} niveles | {} tipos conduit | {} conduits existentes | {} dispositivos".format(
        len(niveles), len(tipos), len(conduits), len(dispositivos)))
    if nivel_p5.get("encontrado"):
        log("Piso 5: ENCONTRADO id={} elevacion={} mm delta={} mm".format(
            nivel_p5.get("id"), nivel_p5["elevacion_mm"], nivel_p5["delta_mm"]))
    else:
        log("Piso 5: NO ENCONTRADO (cercano={} delta={} mm)".format(
            nivel_p5.get("cercano", "-"), nivel_p5.get("delta_mm", "-")))
    log("FIN")
    log("=" * 60)


try:
    main()
except Exception:
    log("EXCEPCION NO CONTROLADA:\n" + traceback.format_exc())
    try:
        escribir_reporte_salida(_raiz(), {
            "error": traceback.format_exc(),
            "version": VERSION,
        })
    except Exception:
        pass
