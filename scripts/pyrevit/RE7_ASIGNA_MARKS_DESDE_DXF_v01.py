# -*- coding: utf-8 -*-
"""
RE7_ASIGNA_MARKS_DESDE_DXF_v01.py
Lee el DXF XPL, extrae bloques electricos de F17/F18 con sus circuitos cercanos,
empareja con dispositivos de Revit por proximidad y asigna Mark y Comments.

Mark: apartamento|tablero|circuito  (ej: F17|TF|TF-03)
Comment: "Cocina" si el dispositivo esta marcado como cocina en Revit

Entrada:
  D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf

Entorno: pyRevit IronPython 2.7 (dentro de Revit)
"""
import ezdxf
import json
import math
import re
import os
import sys
import datetime
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationPoint,
    Transaction,
)
from System import Int64

VERSION = "v01_desde_dxf"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
OUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_desde_dxf_v01.json"

# Zonas para identificar apartamento por coordenadas del DXF
ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

# Bloques electricos a considerar
BLOQUES_ELEC = [
    "ELEC-T-D-t-15A", "ELEC-T-GFCI-t-15A", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
    "ELEC-I-S-C1-5A", "ELEC-TEL", "ELEC-NET-PAU", "ELEC-CAMPANA", "ELEC-TIMBRE",
    "ELEC-F-CONTROL", "ELEC-F-VENT", "S3", "S3C", "ELEC-EXT",
    "Bala Stil Led 10W", "Bala Stil Led 13W", "Bala Stil Led 22W",
]

# Categorias de Revit que consideramos dispositivos
CATEGORIAS_REVIT = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

RADIO_EMPAREJAMIENTO_MM = 400.0  # radio para emparejar DXF con Revit
RADIO_TEXTO_MM = 1000.0          # radio para buscar textos cercanos al bloque DXF

PATRON_CIRCUITO = re.compile(r"\b([A-Z]{2}-\d{2})\b")  # TF-01, TE-03, etc.


def _raiz():
    r = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if r and os.path.exists(r):
        return r
    return DEFAULT_ROOT


def log(msg):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def obtener_doc():
    try:
        app = __revit__
        if app is not None and hasattr(app, "ActiveUIDocument"):
            return app.ActiveUIDocument.Document
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if getattr(_revit, "doc", None) is not None:
            return _revit.doc
    except Exception:
        pass
    return None


def id_de(el):
    v = el.Id
    if hasattr(v, "IntegerValue"):
        return int(v.IntegerValue)
    return int(v.Value)


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def obtener_mark(el):
    param = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if param is None:
        param = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)
    if param is not None and not param.IsReadOnly:
        try:
            return param.AsString()
        except Exception:
            return None
    return None


def obtener_comment(el):
    param = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_COMMENTS)
    if param is None:
        param = el.get_Parameter(BuiltInParameter.ALL_MODEL_COMMENTS)
    if param is not None and not param.IsReadOnly:
        try:
            return param.AsString()
        except Exception:
            return None
    return None


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * 304.8, p.Y * 304.8, p.Z * 304.8]
    return None


def leer_dxf_bloques_y_textos(dxf_path):
    """Lee el DXF y devuelve bloques electricos F17/F18 con textos cercanos."""
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    bloques = []
    textos = []

    # Extraer INSERTs (bloques)
    for e in msp.query("INSERT"):
        name = e.dxf.name or ""
        if name not in BLOQUES_ELEC:
            continue
        p = e.dxf.insert
        apto = apto_de(p.x, p.y)
        if not apto:
            continue
        bloques.append({
            "nombre": name,
            "x": p.x,
            "y": p.y,
            "apto": apto,
            "handle": str(e.dxf.handle),
        })

    # Extraer TEXT y MTEXT
    for e in msp.query("TEXT"):
        p = e.dxf.insert
        textos.append({"x": p.x, "y": p.y, "text": e.dxf.text})
    for e in msp.query("MTEXT"):
        p = e.dxf.insert
        textos.append({"x": p.x, "y": p.y, "text": e.text})

    log("DXF leído: %d bloques electricos F17/F18, %d textos" % (len(bloques), len(textos)))

    # Para cada bloque, buscar circuito mas cercano
    for b in bloques:
        mejor_dist = None
        mejor_circuito = None
        mejor_texto = None
        for t in textos:
            d = math.sqrt((t["x"] - b["x"]) ** 2 + (t["y"] - b["y"]) ** 2)
            if d > RADIO_TEXTO_MM:
                continue
            m = PATRON_CIRCUITO.search(t["text"])
            if m:
                circuito = m.group(1)
                if mejor_dist is None or d < mejor_dist:
                    mejor_dist = d
                    mejor_circuito = circuito
                    mejor_texto = t["text"]
        b["circuito"] = mejor_circuito
        b["circuito_dist"] = mejor_dist
        b["circuito_texto"] = mejor_texto

    return bloques, textos


def obtener_dispositivos_revit(doc):
    """Obtiene dispositivos de Revit en F17/F18 con su marca actual."""
    dispositivos = []
    for cat in CATEGORIAS_REVIT:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            apto = apto_de(pt[0], pt[1])
            if not apto:
                continue
            mark = obtener_mark(el)
            comment = obtener_comment(el)
            dispositivos.append({
                "id": id_de(el),
                "x": pt[0],
                "y": pt[1],
                "z": pt[2],
                "apto": apto,
                "categoria": el.Category.Name,
                "mark_actual": mark,
                "comment_actual": comment,
                "elemento": el,
            })
    log("Revit: %d dispositivos en F17/F18" % len(dispositivos))
    return dispositivos


def emparejar_y_asignar(dispositivos, bloques_dxf):
    """Empareja cada dispositivo de Revit con el bloque DXF mas cercano
    y genera el mark y comment."""
    resultados = []
    no_emparejados = []

    for disp in dispositivos:
        apto = disp["apto"]
        # Filtrar bloques del mismo apartamento
        bloques_apto = [b for b in bloques_dxf if b["apto"] == apto]
        if not bloques_apto:
            no_emparejados.append(disp)
            continue

        # Encontrar el bloque DXF mas cercano
        mejor = None
        mejor_dist = None
        for b in bloques_apto:
            d = dist2d([disp["x"], disp["y"]], [b["x"], b["y"]])
            if mejor_dist is None or d < mejor_dist:
                mejor = b
                mejor_dist = d

        if mejor is None or mejor_dist > RADIO_EMPAREJAMIENTO_MM:
            no_emparejados.append(disp)
            continue

        circuito = mejor["circuito"] or "SIN CIRCUITO"
        # Tablero: usar el prefijo del circuito (ej: TF-01 -> TF) o apto
        if circuito != "SIN CIRCUITO" and "-" in circuito:
            tablero = circuito.split("-")[0]  # TF, TE, etc.
        else:
            tablero = apto

        mark = "%s|%s|%s" % (apto, tablero, circuito)
        comment = "Cocina" if (disp["comment_actual"] and "cocina" in disp["comment_actual"].lower()) else None

        resultados.append({
            "id": disp["id"],
            "mark": mark,
            "comment": comment,
            "apto": apto,
            "circuito_dxf": circuito,
            "dist_dxf_mm": round(mejor_dist, 1),
            "bloque_dxf": mejor["nombre"],
            "mark_anterior": disp["mark_actual"],
        })

    log("Emparejados: %d, No emparejados: %d" % (len(resultados), len(no_emparejados)))
    for d in no_emparejados:
        log("  NO EMPAREJADO: id=%s apto=%s (%.1f,%.1f)" % (d["id"], d["apto"], d["x"], d["y"]))

    return resultados, no_emparejados


def asignar_en_revit(doc, resultados):
    """Asigna Mark y Comments a los elementos de Revit."""
    ok = 0
    fail = 0

    t = Transaction(doc, "RE7 Asignar Marks desde DXF")
    t.Start()
    try:
        for r in resultados:
            el = doc.GetElement(ElementId(Int64(r["id"])))
            if el is None:
                fail += 1
                log("  FAIL id=%s: elemento no encontrado" % r["id"])
                continue

            # Asignar Mark
            p_mark = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark is None:
                p_mark = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)
            if p_mark is None or p_mark.IsReadOnly:
                fail += 1
                log("  FAIL id=%s: sin parameter Mark" % r["id"])
                continue
            p_mark.Set(r["mark"])

            # Asignar Comment
            if r["comment"] is not None:
                p_com = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_COMMENTS)
                if p_com is None:
                    p_com = el.get_Parameter(BuiltInParameter.ALL_MODEL_COMMENTS)
                if p_com is not None and not p_com.IsReadOnly:
                    p_com.Set(r["comment"])

            ok += 1
            log("  OK id=%s -> Mark=%r Comment=%r" % (r["id"], r["mark"], r["comment"]))
        t.Commit()
    except Exception:
        t.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 0, 0

    return ok, fail


def main():
    log("=" * 70)
    log("RE7_ASIGNA_MARKS_DESDE_DXF_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    # 1. Leer DXF
    bloques_dxf, textos = leer_dxf_bloques_y_textos(DXF_PATH)

    # 2. Obtener dispositivos de Revit
    dispositivos = obtener_dispositivos_revit(doc)

    # 3. Emparejar y generar marks
    resultados, no_emparejados = emparejar_y_asignar(dispositivos, bloques_dxf)

    # 4. Guardar JSON de reporte
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "dxf": DXF_PATH,
        "documento": doc.Title,
        "resumen": {
            "total_revit": len(dispositivos),
            "emparejados": len(resultados),
            "no_emparejados": len(no_emparejados),
        },
        "resultados": resultados,
        "no_emparejados": [
            {"id": d["id"], "apto": d["apto"], "x": d["x"], "y": d["y"],
             "mark_actual": d["mark_actual"], "comment_actual": d["comment_actual"]}
            for d in no_emparejados
        ],
    }

    raiz = _raiz()
    out_path = os.path.join(raiz, "data", "f7_marks_desde_dxf_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    # 5. Asignar en Revit
    ok, fail = asignar_en_revit(doc, resultados)

    log("")
    log("=" * 70)
    log("RESULTADO: %d asignados OK, %d fallos, %d no emparejados" % (ok, fail, len(no_emparejados)))
    log("=" * 70)
    return 0 if fail == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
