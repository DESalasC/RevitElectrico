# -*- coding: utf-8 -*-
"""RE_VALIDAR_TRANSFERENCIA_v01.py - Valida la transferencia DXF -> RVT por panel-ancla.

Que resuelve
------------
Antes de mover o crear componentes en Revit, comprueba que:
  1. El apartamento existe en el DXF consolidado y tiene un TB-Panel en su definicion.
  2. La posicion mundial del panel en el DXF coincide con el panel real del RVT.
  3. Cada dispositivo del JSON de transferencia coincide con la posicion calculada
     desde el DXF mas el ajuste fino del ancla.

Entradas (CLI)
--------------
--dxf          DXF consolidado (por defecto ArchivosBase/STM-T4-P4_bloques_electricos.dxf)
--apto         Nombre del apartamento, ej. "Apartamento Tipo E 05"
--estado       JSON de estado del modelo (paneles reales del RVT)
--transfer     JSON de transferencia a validar (opcional)
--json-out     Reporte de validacion (opcional)
--tolerancia   Tolerancia XY en metros (por defecto 0.20)

Salida: codigo 0 si PASA, 1 si FALLA.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

FT_A_M = 0.3048


def _normalizar(texto):
    t = (texto or "").upper().replace("APATAMENTO", "APARTAMENTO").replace("APATAMENTOS", "APARTAMENTOS")
    return re.sub(r"\s+", " ", t).strip()


def _patron_apto(nombre):
    m = re.search(r"TIPO\s+([A-Z]+)\s*0*(\d+)", _normalizar(nombre))
    if not m:
        raise SystemExit("No pude interpretar el apartamento: {!r}".format(nombre))
    tipo, nro = m.group(1), m.group(2)
    return re.compile(r"TIPO\s+{}\s*0*{}\b".format(re.escape(tipo), re.escape(nro)))


def _buscar_apto(msp, doc, patron):
    for e in msp.query("INSERT"):
        if "APART" in _normalizar(e.dxf.name) and patron.search(_normalizar(e.dxf.name)):
            return e
    return None


def _buscar_panel(doc, insert_apto):
    blk = doc.blocks.get(insert_apto.dxf.name)
    for h in blk:
        if h.dxftype() == "INSERT" and re.search(r"TB-PANEL|TB-PARCIAL|PANEL", h.dxf.name, re.I):
            return h
    return None


def _paneles_rvt(estado):
    salida = []
    for i in estado.get("instancias_electricas") or []:
        if i.get("familia") == "E_Distribution Panel" and i.get("punto"):
            salida.append({
                "id": i.get("id"),
                "x_m": i["punto"][0] * FT_A_M,
                "y_m": i["punto"][1] * FT_A_M,
                "z_rel_m": (i.get("z_relativo_nivel") or 0.0) * FT_A_M,
            })
    return salida


def validar(dxf, apto, estado, transfer=None, tolerancia=0.20):
    import ezdxf

    doc = ezdxf.readfile(dxf)
    msp = doc.modelspace()
    patron = _patron_apto(apto)
    e_apto = _buscar_apto(msp, doc, patron)
    if e_apto is None:
        return {"aprobado": False, "errores": ["No se encontro el apartamento en el DXF."]}

    h_panel = _buscar_panel(doc, e_apto)
    if h_panel is None:
        return {"aprobado": False, "errores": ["El apartamento no tiene TB-Panel en su definicion."]}

    rot = math.radians(getattr(e_apto.dxf, "rotation", 0.0) or 0.0)
    lx, ly = h_panel.dxf.insert.x, h_panel.dxf.insert.y
    wx = e_apto.dxf.insert.x + lx * math.cos(rot) - ly * math.sin(rot)
    wy = e_apto.dxf.insert.y + lx * math.sin(rot) + ly * math.cos(rot)

    paneles = _paneles_rvt(estado)
    mejor = None
    for p in paneles:
        d = math.hypot(wx - p["x_m"], wy - p["y_m"])
        if mejor is None or d < mejor[0]:
            mejor = (d, p)

    errores = []
    advertencias = []
    if mejor is None:
        errores.append("El estado del modelo no contiene paneles E_Distribution Panel.")
        delta_xy = None
    else:
        delta_xy = mejor[0]
        if delta_xy > tolerancia:
            errores.append("Panel DXF vs RVT fuera de tolerancia: {:.3f} m > {:.2f} m.".format(delta_xy, tolerancia))

    ajuste = None
    if mejor is not None:
        ajuste = {"x": mejor[1]["x_m"] - wx, "y": mejor[1]["y_m"] - wy}

    comprobados = 0
    max_desv = 0.0
    if transfer and ajuste is not None:
        for d in transfer.get("dispositivos") or []:
            base_x = d.get("x_dxf_world", d.get("x_dxf"))
            base_y = d.get("y_dxf_world", d.get("y_dxf"))
            if base_x is None or base_y is None:
                continue
            esperado_x = base_x + ajuste["x"]
            esperado_y = base_y + ajuste["y"]
            desv = math.hypot(d.get("x_revit_esperado", 0) - esperado_x,
                              d.get("y_revit_esperado", 0) - esperado_y)
            max_desv = max(max_desv, desv)
            comprobados += 1
        if max_desv > tolerancia:
            errores.append("Dispositivos del JSON desviados hasta {:.3f} m (>{:.2f} m).".format(max_desv, tolerancia))

    return {
        "aprobado": not errores,
        "apartamento": apto,
        "dxf": str(dxf),
        "panel_dxf_m": {"x": round(wx, 4), "y": round(wy, 4)},
        "panel_rvt_m": None if mejor is None else {"id": mejor[1]["id"], "x": round(mejor[1]["x_m"], 4),
                                                   "y": round(mejor[1]["y_m"], 4),
                                                   "z_rel_m": round(mejor[1]["z_rel_m"], 4)},
        "delta_panel_xy_m": None if delta_xy is None else round(delta_xy, 4),
        "ajuste_ancla": None if ajuste is None else {"x": round(ajuste["x"], 4), "y": round(ajuste["y"], 4)},
        "tolerancia_xy_m": tolerancia,
        "dispositivos_comprobados": comprobados,
        "max_desviacion_dispositivos_m": round(max_desv, 4),
        "errores": errores,
        "advertencias": advertencias,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Valida transferencia DXF -> RVT por panel-ancla.")
    parser.add_argument("--dxf", default=r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T4-P4_bloques_electricos.dxf")
    parser.add_argument("--apto", required=True)
    parser.add_argument("--estado", default=r"D:\Work\PROJECTS\RevitElectrico\data\estado_modelo_v01.json")
    parser.add_argument("--transfer", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--tolerancia", type=float, default=0.20)
    args = parser.parse_args(argv)

    transfer = None
    if args.transfer:
        transfer = json.loads(Path(args.transfer).read_text(encoding="utf-8"))
    estado = json.loads(Path(args.estado).read_text(encoding="utf-8"))

    r = validar(args.dxf, args.apto, estado, transfer, args.tolerancia)
    print(json.dumps(r, indent=2, ensure_ascii=True))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(r, indent=2, ensure_ascii=True), encoding="utf-8")
    print("\nVALIDACION: {}".format("APROBADA" if r["aprobado"] else "FALLIDA"))
    return 0 if r["aprobado"] else 1


if __name__ == "__main__":
    sys.exit(main())
