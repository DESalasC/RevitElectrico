# -*- coding: utf-8 -*-
"""
RE7_EMPAREJA_TODAS_CATEGORIAS_v01.py
Empareja dispositivos REVIT (f7_todas_categorias_v01.json) con aparatos DXF
(f7_topologia_dxf_f17_f18_v01.json) por proximidad + tipo.
Genera listado de ElementIds por categoria:
  A) EMPAREJADOS (DXF -> Revit): pueden rutearse automaticamente
  B) REVIT SIN DXF: dispositivos en modelo no en diagrama
  C) DXF SIN REVIT: en diagrama pero no colocados en modelo
Salida: consola + data/f7_empareja_todas_categorias_v01.txt (+JSON)
"""
import json
import math
from collections import defaultdict

REVIT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_todas_categorias_v01.json"
DXF_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_topologia_dxf_f17_f18_v01.json"
OUT_TXT = r"D:\Work\PROJECTS\RevitElectrico\data\f7_empareja_todas_categorias_v01.txt"
OUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_empareja_todas_categorias_v01.json"

RADIO_MM = 400.0  # radio de busqueda para emparejar

# Mapeo bloque DXF -> (familia Revit, tipo Revit) aceptados
MAPEO = {
    "Bala Stil Led 10W":  [("M_Iluminacion", "SONO FLEX 10 trim")],
    "Bala Stil Led 13W":  [("M_Iluminacion", "SONO FLEX 13 trim")],
    "Bala Stil Led 22W":  [("M_Iluminacion", "SONO FLEX 22 trim")],
    "ELEC-CAMPANA":       [("M_Timbre", "Campana")],
    "ELEC-EXT":           [("M_Toma doble", None)],
    "ELEC-F-CONTROL":     [("M_Climatizacion", "Interruptor Ventilador")],
    "ELEC-F-VENT":        [("M_ClimatizacionV", "Ventilador")],
    "ELEC-I-S-1-5A":      [("M_Interruptores", "Simple")],
    "ELEC-I-S-2-5A":      [("M_Interruptores", "Doble")],
    "ELEC-NET-PAU":       [("Consolidation_Point", "CPB12BL")],
    "ELEC-T-D-t-15A":     [("M_Toma doble", "Normal")],
    "ELEC-T-GFCI-t-15A":  [("M_Toma doble", "GFCI")],
    "ELEC-TEL":           [("M_Comunicaciones", "Datos")],
    "ELEC-TIMBRE":        [("M_Pulsador - Interruptor", "Timbre")],
    "S3":                 [("M_Interruptores", "Simple")],
    "S3C":                [("M_Interruptores", "Doble")],
}


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cargar():
    with open(REVIT_JSON) as f:
        revit_dump = json.load(f)
    with open(DXF_JSON) as f:
        dxf = json.load(f)
    return revit_dump, dxf


def tipo_ok(dev, validos):
    fam = dev.get("familia")
    tip = dev.get("tipo")
    for vfam, vtip in validos:
        if fam == vfam and (vtip is None or tip == vtip):
            return True
    return False


def main():
    revit_dump, dxf = cargar()
    # todos los dispositivos revit en lista plana con categoria
    revit_devs = []
    for cat_nombre, devs in revit_dump["categorias"].items():
        for d in devs:
            d["categoria"] = cat_nombre
            revit_devs.append(d)

    aparatos = dxf["aparatos"]
    dxf_por_apto = defaultdict(list)
    for a in aparatos:
        dxf_por_apto[a["apto"]].append(a)

    revit_por_apto = defaultdict(list)
    for d in revit_devs:
        revit_por_apto[d["apto"]].append(d)

    lineas = []
    resumen = {
        "emparejados": [],
        "revit_sin_dxf": [],
        "dxf_sin_revit": [],
        "por_categoria": defaultdict(lambda: {"emp": 0, "revit_sin": 0, "dxf_sin": 0}),
    }

    for apto in ["F17", "F18"]:
        lineas.append("=" * 90)
        lineas.append("APARTAMENTO %s" % apto)
        lineas.append("=" * 90)

        d_ap = dxf_por_apto.get(apto, [])
        r_ap = revit_por_apto.get(apto, [])

        lineas.append("")
        lineas.append("APARATOS DXF (%d):" % len(d_ap))
        for a in sorted(d_ap, key=lambda x: x["bloque"]):
            lineas.append("  %-30s (%-8.1f, %-8.1f)" % (a["bloque"], a["x"], a["y"]))

        lineas.append("")
        lineas.append("DISPOSITIVOS REVIT (%d):" % len(r_ap))
        for d in sorted(r_ap, key=lambda x: (d.get("categoria",""), d.get("familia",""), d.get("tipo",""), d["x_mm"], d["y_mm"])):
            lineas.append("  id=%-9s | %-24s | %-22s | %-20s | (%-8.1f, %-8.1f) Z=%-7.1f" % (
                d["id"], d.get("categoria","?"), d.get("familia","?"),
                d.get("tipo","?"), d["x_mm"], d["y_mm"], d["z_mm"]))

        # Emparejamiento greedy por proximidad
        lineas.append("")
        lineas.append("-" * 90)
        lineas.append("EMPAREJAMIENTO DXF -> REVIT (radio %.0f mm):" % RADIO_MM)
        lineas.append("-" * 90)

        usado_revit = set()
        emp_apto = []

        for a in sorted(d_ap, key=lambda x: x["bloque"]):
            validos = MAPEO.get(a["bloque"], [])
            mejor = None
            mejor_dist = None
            for d in r_ap:
                if d["id"] in usado_revit:
                    continue
                if not tipo_ok(d, validos):
                    continue
                dd = dist2d((a["x"], a["y"]), (d["x_mm"], d["y_mm"]))
                if mejor_dist is None or dd < mejor_dist:
                    mejor_dist = dd
                    mejor = d
            if mejor is not None and mejor_dist <= RADIO_MM:
                usado_revit.add(mejor["id"])
                emp_apto.append({
                    "apto": apto, "dxf_bloque": a["bloque"],
                    "dxf_x": a["x"], "dxf_y": a["y"],
                    "revit_id": mejor["id"], "revit_categoria": mejor.get("categoria"),
                    "revit_familia": mejor.get("familia"),
                    "revit_tipo": mejor.get("tipo"),
                    "revit_x": mejor["x_mm"], "revit_y": mejor["y_mm"],
                    "dist_mm": round(mejor_dist, 1),
                })
                resumen["por_categoria"][mejor.get("categoria")]["emp"] += 1
                lineas.append("  OK   %-30s DXF(%.0f,%.0f) -> id=%-9s %-24s %-22s %-20s dist=%.0fmm" % (
                    a["bloque"], a["x"], a["y"], mejor["id"],
                    mejor.get("categoria","?"), mejor.get("familia","?"),
                    mejor.get("tipo","?"), mejor_dist))
            else:
                resumen["por_categoria"]["(sin categoria DXF)"]["dxf_sin"] += 1
                lineas.append("  FALTA %-30s DXF(%.0f,%.0f) -> SIN contraparte en REVIT" % (
                    a["bloque"], a["x"], a["y"]))
                resumen["dxf_sin_revit"].append({
                    "apto": apto, "bloque": a["bloque"], "x": a["x"], "y": a["y"]})

        # Revit sin emparejar
        sin_emp = [d for d in r_ap if d["id"] not in usado_revit]
        lineas.append("")
        lineas.append("DISPOSITIVOS REVIT SIN DIAGRAMA DXF (%d):" % len(sin_emp))
        for d in sorted(sin_emp, key=lambda x: (x.get("categoria",""), x.get("familia",""), x.get("tipo",""), d["x_mm"], d["y_mm"])):
            lineas.append("  id=%-9s | %-24s | %-22s | %-20s | (%-8.1f, %-8.1f) Z=%-7.1f" % (
                d["id"], d.get("categoria","?"), d.get("familia","?"),
                d.get("tipo","?"), d["x_mm"], d["y_mm"], d["z_mm"]))
            resumen["por_categoria"][d.get("categoria")]["revit_sin"] += 1
            resumen["revit_sin_dxf"].append({
                "apto": apto, "id": d["id"], "categoria": d.get("categoria"),
                "familia": d.get("familia"), "tipo": d.get("tipo"),
                "x": d["x_mm"], "y": d["y_mm"], "z": d["z_mm"]})

        resumen["emparejados"].extend(emp_apto)

    txt = "\n".join(lineas)
    with open(OUT_TXT, "w") as f:
        f.write(txt)
    # JSON serializable
    resumen_json = {
        "emparejados": resumen["emparejados"],
        "revit_sin_dxf": resumen["revit_sin_dxf"],
        "dxf_sin_revit": resumen["dxf_sin_revit"],
        "por_categoria": {k: dict(v) for k, v in resumen["por_categoria"].items()},
    }
    with open(OUT_JSON, "w") as f:
        json.dump(resumen_json, f, ensure_ascii=True, indent=2)

    print(txt)
    print("\n" + "=" * 90)
    print("RESUMEN GLOBAL")
    print("=" * 90)
    print("Emparejados: %d" % len(resumen["emparejados"]))
    print("REVIT sin DXF: %d" % len(resumen["revit_sin_dxf"]))
    print("DXF sin REVIT: %d" % len(resumen["dxf_sin_revit"]))
    print("")
    print("POR CATEGORIA REVIT (emp / revit_sin_dxf / dxf_sin):")
    for cat in sorted(resumen["por_categoria"]):
        c = resumen["por_categoria"][cat]
        print("  %-28s emp=%3d  revit_sin=%3d  dxf_sin=%3d" % (
            cat, c["emp"], c["revit_sin"], c["dxf_sin"]))
    print("TXT: %s" % OUT_TXT)
    print("JSON: %s" % OUT_JSON)


if __name__ == "__main__":
    main()
