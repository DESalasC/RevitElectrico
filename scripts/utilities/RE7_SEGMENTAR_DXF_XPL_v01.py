# -*- coding: utf-8 -*-
"""
RE7_SEGMENTAR_DXF_XPL_v01.py
Lee el DXF de bloques electricos del piso 5 (misma escala/sistema que el modelo
Revit) y genera segmentos de conduit rectos listos para el preflight de F7.

Entidades usadas: LINE y LWPOLYLINE (polilineas rectas). Los ARC se ignoran
porque la regla del proyecto exige polilineas (LineSegments), NO curvas/NURBS.

Salida: data/f7_segmentos_xpl_v01.json  (formato compatible con RE7_ANALIZAR_PREFLIGHT_v01)

Entorno: CPython 3.12 (sin Revit, sin clr).
Requiere: $env:REVITELECTRICO_ROOT y ezdxf.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import ezdxf

FT_A_MM = 304.8  # pies -> mm (no se usa; el DXF ya esta en mm locales)

RAIZ = Path(__file__).resolve().parents[2]


def resolver_ruta(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else RAIZ / p


def cargar_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(path: Path, d: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=True, indent=2)


def dedup_punto(p: tuple[float, float], vistos: set[tuple[float, float]], umbral_mm: float = 1.0) -> bool:
    clave = (round(p[0] / umbral_mm), round(p[1] / umbral_mm))
    if clave in vistos:
        return True
    vistos.add(clave)
    return False


def segmento_valido(a: tuple[float, float], b: tuple[float, float], min_mm: float = 3.05) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) >= min_mm


def extraer_segmentos_doc(doc: ezdxf.document.Drawing) -> list[dict[str, Any]]:
    msp = doc.modelspace()
    segmentos: list[dict[str, Any]] = []
    visto_puntos: set[tuple[float, float]] = set()
    contador = 0

    def agregar(a: tuple[float, float], b: tuple[float, float], idx: int) -> None:
        nonlocal contador
        if not segmento_valido(a, b):
            return
        if dedup_punto(a, visto_puntos) and dedup_punto(b, visto_puntos):
            return
        contador += 1
        segmentos.append({
            "id": f"XPL-{idx:05d}",
            "apto": "Apartamento Tipo XPL",
            "servicio": "TOMAS",
            "tamano": "3/4",
            "diametro_mm": 21.03,
            "a_mm": [round(a[0], 3), round(a[1], 3), 15930.0],
            "b_mm": [round(b[0], 3), round(b[1], 3), 15930.0],
            "origen": "DXF_XPL",
            "z_absoluta_m": 15.93,
        })

    # LINE
    for e in msp.query("LINE"):
        s = e.dxf.start
        t = e.dxf.end
        agregar((s.x, s.y), (t.x, t.y), contador)

    # LWPOLYLINE -> segmentos rectos entre vertices consecutivos
    for e in msp.query("LWPOLYLINE"):
        vertices = [(float(v[0]), float(v[1])) for v in e.vertices()]
        for i in range(len(vertices) - 1):
            agregar(vertices[i], vertices[i + 1], contador)

    return segmentos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Segmenta polilineas rectas del DXF XPL del piso 5 (coordenadas locales)"
    )
    ap.add_argument("--dxf", default="ArchivosBase/STM-T5-P5_bloques_electricos-XPL.dxf")
    ap.add_argument("--out", default="data/f7_segmentos_xpl_v01.json")
    args = ap.parse_args(argv)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if not raiz:
        print("ERROR: falta REVITELECTRICO_ROOT", file=sys.stderr)
        return 2

    dxf_path = resolver_ruta(args.dxf)
    if not dxf_path.exists():
        print(f"ERROR: no existe el DXF: {dxf_path}", file=sys.stderr)
        return 2

    print(f"Leyendo DXF: {dxf_path}")
    doc = ezdxf.readfile(str(dxf_path))
    segmentos = extraer_segmentos_doc(doc)

    reporte = {
        "version": "v01",
        "script": "RE7_SEGMENTAR_DXF_XPL_v01",
        "fuente_dxf": str(dxf_path),
        "n_segmentos": len(segmentos),
        "segmentos": segmentos,
        "resumen": {
            "n_segmentos": len(segmentos),
        },
    }
    guardar_json(resolver_ruta(args.out), reporte)
    print(f"Segmentos generados: {len(segmentos)}")
    print(f"Salida: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
