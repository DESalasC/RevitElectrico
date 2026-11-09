# -*- coding: utf-8 -*-
"""RE_GENERAR_TRANSFERENCIA_v02.py - Genera el JSON de transferencia DXF -> RVT.

Cambios frente a v01:
  * Coordenadas X,Y,Z explicitas en metros y en pies (sin ambiguedad).
  * Equivalencias DXF -> familia Revit desde config/equivalencias_dxf_revit_v02.json
    (ya no usa M_Interruptor bipolar ni M_Toma simple).
  * Panel-ancla tomado del DXF consolidado y contrastado con el panel real del RVT.

Salida: data/E05_transferencia_panel_ancla_v03.json

Ultimos tres cambios
--------------------
1. 2026-11-08 v02: unidades explicitas m/ft y equivalencias vigentes.
2. 2026-11-08: corrige el error metros/pies de la primera aplicacion.
3. 2026-11-08 v01: version inicial con coordenadas en metros sin convertir.
"""
import json
import math
import re
from pathlib import Path

import ezdxf

ROOT = Path(r"D:\Work\PROJECTS\RevitElectrico")
FT = 3.280839895
DXF = ROOT / "ArchivosBase" / "STM-T4-P4_bloques_electricos.dxf"
INV = ROOT / "data" / "inventario_apartamentos_v01.json"
ESTADO = ROOT / "data" / "estado_modelo_v01.json"
EQUIV = ROOT / "config" / "equivalencias_dxf_revit_v02.json"
APTO = "Apartamento Tipo E 05"
NIVEL = "Piso 5"
ELEV_M = 43.3727


def main():
    doc = ezdxf.readfile(str(DXF))
    msp = doc.modelspace()

    apt = None
    for e in msp.query("INSERT"):
        n = e.dxf.name.upper().replace("APATAMENTO", "APARTAMENTO")
        if re.search(r"E\s*0?5\b", n) and "APART" in n:
            apt = e
            break
    if apt is None:
        raise SystemExit("No se encontro el apartamento E 05 en el DXF.")

    blk = doc.blocks.get(apt.dxf.name)
    panel = None
    for h in blk:
        if h.dxftype() == "INSERT" and re.search(r"TB-Panel|TB-Parcial", h.dxf.name, re.I):
            panel = h
            break
    if panel is None:
        raise SystemExit("El apartamento E 05 no tiene TB-Panel.")

    rot = math.radians(apt.dxf.rotation or 0.0)

    def world(lx, ly):
        return (apt.dxf.insert.x + lx * math.cos(rot) - ly * math.sin(rot),
                apt.dxf.insert.y + lx * math.sin(rot) + ly * math.cos(rot))

    px, py = world(panel.dxf.insert.x, panel.dxf.insert.y)

    estado = json.loads(ESTADO.read_text(encoding="utf-8"))
    paneles = []
    for i in estado["instancias_electricas"]:
        if i.get("familia") == "E_Distribution Panel" and i.get("punto"):
            paneles.append({"id": i["id"], "x_m": i["punto"][0] * 0.3048,
                            "y_m": i["punto"][1] * 0.3048,
                            "z_m": (i.get("z_relativo_nivel") or 0) * 0.3048})
    best = min(paneles, key=lambda p: math.hypot(p["x_m"] - px, p["y_m"] - py))
    adj = {"x": best["x_m"] - px, "y": best["y_m"] - py}

    equiv = json.loads(EQUIV.read_text(encoding="utf-8"))
    inv = json.loads(INV.read_text(encoding="utf-8"))
    a = next(x for x in inv["apartamentos"] if x["nombre_normalizado"] == APTO)

    dispositivos = []
    for d in a["dispositivos_hijos"]:
        wx, wy = world(d["x_dxf"], d["y_dxf"])
        rx, ry = wx + adj["x"], wy + adj["y"]
        fam = equiv["por_bloque"].get(d["nombre_bloque_hijo"])
        if not fam:
            fam = equiv["por_capa"].get(d["capa"], d.get("familia_revit"))
        dispositivos.append({
            "nombre_bloque_hijo": d["nombre_bloque_hijo"],
            "capa": d["capa"],
            "familia_revit": fam,
            "simbolo": equiv.get("simbolo_por_bloque", {}).get(d["nombre_bloque_hijo"], d.get("simbolo")),
            "anfitrion": d.get("anfitrion"),
            "rotacion": d.get("rotacion"),
            "x_dxf_local_m": d["x_dxf"],
            "y_dxf_local_m": d["y_dxf"],
            "x_dxf_world_m": round(wx, 4),
            "y_dxf_world_m": round(wy, 4),
            "x_revit_m": round(rx, 4),
            "y_revit_m": round(ry, 4),
            "x_revit_ft": round(rx * FT, 4),
            "y_revit_ft": round(ry * FT, 4),
            "z_local_m": d["z_local_m"],
            "z_abs_m": round(ELEV_M + d["z_local_m"], 4),
            "z_abs_ft": round((ELEV_M + d["z_local_m"]) * FT, 4),
        })

    out = {
        "version": "v03",
        "fecha": "2026-11-08",
        "apartamento": APTO,
        "nivel": NIVEL,
        "elevacion_nivel_m": ELEV_M,
        "dxf_referencia": str(DXF),
        "unidades": {"dxf": "metros", "json_revit_m": "metros", "json_revit_ft": "pies (API Revit)"},
        "insert_apartamento_dxf": {"x": round(apt.dxf.insert.x, 4), "y": round(apt.dxf.insert.y, 4),
                                   "rotacion": apt.dxf.rotation},
        "panel_ancla": {
            "nombre_bloque": panel.dxf.name,
            "x_dxf_world_m": round(px, 4), "y_dxf_world_m": round(py, 4),
            "panel_rvt_id": best["id"],
            "x_rvt_m": round(best["x_m"], 4), "y_rvt_m": round(best["y_m"], 4),
            "z_rvt_m": round(best["z_m"], 4),
            "ajuste_ancla_m": {"x": round(adj["x"], 4), "y": round(adj["y"], 4)},
            "delta_xy_m": round(math.hypot(best["x_m"] - px, best["y_m"] - py), 4),
        },
        "tolerancias": {"xy_m": 0.20, "z_m": "0.3/1.1/1.2/2.6 +-0.06"},
        "dispositivos": dispositivos,
        "marcadores_conductor": [{"nombre_bloque_hijo": m["nombre_bloque_hijo"], "modelar": False}
                                  for m in a["marcadores_conductor"]],
        "resumen": {"total_dispositivos": len(dispositivos),
                    "total_marcadores": len(a["marcadores_conductor"]),
                    "excluidos": "F 01 y F 02 (referencia intocable)",
                    "familias_excluidas": equiv["excluidos"]},
    }
    dest = ROOT / "data" / "E05_transferencia_panel_ancla_v03.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=True), encoding="utf-8")
    print("OK", dest)
    print("panel DXF", round(px, 4), round(py, 4), "| RVT", best["id"],
          round(best["x_m"], 4), round(best["y_m"], 4), "| delta", out["panel_ancla"]["delta_xy_m"])
    print("dispositivos", len(dispositivos))


if __name__ == "__main__":
    main()
