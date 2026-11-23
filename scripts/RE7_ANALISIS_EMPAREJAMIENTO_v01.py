# -*- coding: utf-8 -*-
"""
RE7_ANALISIS_EMPAREJAMIENTO_v01.py
Compara dispositivos Revit (f7_revit_dispositivos_v02.json) vs aparatos DXF
(f7_topologia_dxf_f17_f18_v01.json) y genera listado de ElementIds por categoria:
  A) REVIT con diagrama DXF (emparejados) - pueden rutearse automaticamente
  B) REVIT sin diagrama DXF (sin emparejar) - necesitan revision/manual
  C) DXF sin contraparte en REVIT - aparecen en plano pero no en modelo
Salida: data/f7_emparejamiento_revit_dxf_v01.txt (+ JSON)
"""
import json
import math
from collections import defaultdict

REVIT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_revit_dispositivos_v02.json"
DXF_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_topologia_dxf_f17_f18_v01.json"
OUT_TXT = r"D:\Work\PROJECTS\RevitElectrico\data\f7_emparejamiento_revit_dxf_v01.txt"
OUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_emparejamiento_revit_dxf_v01.json"

# Mapeo bloque DXF -> familias/tipos Revit validos (amplio, segun usuario)
MAPEO = {
    "Bala Stil Led 10W":  [("M_Iluminacion", "SONO FLEX 10 trim")],
    "Bala Stil Led 13W":  [("M_Iluminacion", "SONO FLEX 13 trim")],
    "Bala Stil Led 22W":  [("M_Iluminacion", "SONO FLEX 22 trim")],
    "ELEC-T-D-t-15A":     [("M_Toma doble", "Normal"), ("M_Toma doble", "GFCI")],
    "ELEC-T-GFCI-t-15A":  [("M_Toma doble", "GFCI"), ("M_Toma doble", "Normal")],
    "ELEC-I-S-1-5A":      [("M_Interruptores", "Simple")],
    "ELEC-I-S-2-5A":      [("M_Interruptores", "Doble")],
    "ELEC-F-CONTROL":     [("M_Climatizacion", "Interruptor Ventilador")],
    "ELEC-F-VENT":        [("M_ClimatizacionV", "Ventilador")],
    "ELEC-NET-PAU":       [("Consolidation_Point", "CPB12BL")],
    "ELEC-TEL":           [("M_Comunicaciones", None)],  # Datos, segun usuario
    "ELEC-TIMBRE":        [("M_Timbre", None)],
    "ELEC-CAMPANA":       [("M_Campana", None), ("M_Timbre", None)],
    "ELEC-EXT":           [("M_Toma doble", None)],
    "S3":                 [("M_Interruptores", "Simple")],
    "S3C":                [("M_Interruptores", "Doble")],
}


def dist2d(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def cargar():
    with open(REVIT_JSON) as f:
        revit = json.load(f)["dispositivos"]
    with open(DXF_JSON) as f:
        dxf = json.load(f)
    return revit, dxf


def analizar():
    revit, dxf = cargar()
    aparatos = dxf["aparatos"]
    aristas = dxf["aristas"]

    # Indexar aparatos DXF por apto
    dxf_por_apto = defaultdict(list)
    for a in aparatos:
        dxf_por_apto[a["apto"]].append(a)

    # Indexar Revit por apto
    revit_por_apto = defaultdict(list)
    for d in revit:
        revit_por_apto[d["apto"]].append(d)

    lineas = []
    resumen = {"emparejados": [], "revit_sin_dxf": [], "dxf_sin_revit": []}

    for apto in ["F17", "F18"]:
        lineas.append("=" * 80)
        lineas.append("APARTAMENTO %s" % apto)
        lineas.append("=" * 80)

        d_ap = dxf_por_apto.get(apto, [])
        r_ap = revit_por_apto.get(apto, [])

        lineas.append("")
        lineas.append("APARATOS DXF (%d):" % len(d_ap))
        for a in sorted(d_ap, key=lambda x: (x["bloque"], x["x"], x["y"])):
            lineas.append("  %-30s (%-8.1f, %-8.1f)" % (a["bloque"], a["x"], a["y"]))

        lineas.append("")
        lineas.append("DISPOSITIVOS REVIT (%d):" % len(r_ap))
        for d in sorted(r_ap, key=lambda x: (x.get("familia",""), x.get("tipo",""), x["x_mm"], x["y_mm"])):
            lineas.append("  id=%-9s %-30s %-26s (%-8.1f, %-8.1f) Z=%-7.1f" % (
                d["id"], d.get("familia","?"), d.get("tipo","?"),
                d["x_mm"], d["y_mm"], d["z_mm"]))

        # Emparejamiento
        lineas.append("")
        lineas.append("-" * 80)
        lineas.append("EMPAREJAMIENTO (proximidad + tipo):")
        lineas.append("-" * 80)

        usado_revit = set()
        emparejados = []

        for a in sorted(d_ap, key=lambda x: x["bloque"]):
            validos = MAPEO.get(a["bloque"], [])
            mejor = None
            mejor_dist = None
            for d in r_ap:
                if d["id"] in usado_revit:
                    continue
                # verificar tipo
                tipo_ok = False
                for fam, tip in validos:
                    if d.get("familia") == fam and (tip is None or d.get("tipo") == tip):
                        tipo_ok = True
                        break
                if not tipo_ok:
                    continue
                dd = dist2d((a["x"], a["y"]), (d["x_mm"], d["y_mm"]))
                if mejor_dist is None or dd < mejor_dist:
                    mejor_dist = dd
                    mejor = d
            if mejor is not None:
                usado_revit.add(mejor["id"])
                emparejados.append({
                    "apto": apto, "dxf_bloque": a["bloque"],
                    "dxf_x": a["x"], "dxf_y": a["y"],
                    "revit_id": mejor["id"], "revit_familia": mejor.get("familia"),
                    "revit_tipo": mejor.get("tipo"),
                    "revit_x": mejor["x_mm"], "revit_y": mejor["y_mm"],
                    "dist_mm": round(mejor_dist, 1),
                })
                lineas.append("  OK  %-30s DXF(%.0f,%.0f) -> REVIT id=%-9s %-30s %-20s dist=%.0fmm" % (
                    a["bloque"], a["x"], a["y"], mejor["id"],
                    mejor.get("familia","?"), mejor.get("tipo","?"), mejor_dist))
            else:
                lineas.append("  FALTA %-30s DXF(%.0f,%.0f) -> SIN contraparte en REVIT" % (
                    a["bloque"], a["x"], a["y"]))
                resumen["dxf_sin_revit"].append({
                    "apto": apto, "bloque": a["bloque"], "x": a["x"], "y": a["y"]})

        # Revit sin emparejar
        sin_emparejar = [d for d in r_ap if d["id"] not in usado_revit]
        lineas.append("")
        lineas.append("DISPOSITIVOS REVIT SIN DIAGRAMA DXF (%d):" % len(sin_emparejar))
        for d in sorted(sin_emparejar, key=lambda x: (x.get("familia",""), x.get("tipo",""), x["x_mm"], x["y_mm"])):
            lineas.append("  id=%-9s %-30s %-26s (%-8.1f, %-8.1f) Z=%-7.1f" % (
                d["id"], d.get("familia","?"), d.get("tipo","?"),
                d["x_mm"], d["y_mm"], d["z_mm"]))
            resumen["revit_sin_dxf"].append({
                "apto": apto, "id": d["id"], "familia": d.get("familia"),
                "tipo": d.get("tipo"), "x": d["x_mm"], "y": d["y_mm"], "z": d["z_mm"]})

        resumen["emparejados"].extend(emparejados)

    # Escritura
    txt = "\n".join(lineas)
    with open(OUT_TXT, "w") as f:
        f.write(txt)
    with open(OUT_JSON, "w") as f:
        json.dump(resumen, f, ensure_ascii=True, indent=2)

    print(txt)
    print("\n" + "=" * 80)
    print("RESUMEN GLOBAL")
    print("=" * 80)
    print("Emparejados: %d" % len(resumen["emparejados"]))
    print("REVIT sin DXF: %d" % len(resumen["revit_sin_dxf"]))
    print("DXF sin REVIT: %d" % len(resumen["dxf_sin_revit"]))
    print("TXT: %s" % OUT_TXT)
    print("JSON: %s" % OUT_JSON)


if __name__ == "__main__":
    analizar()
