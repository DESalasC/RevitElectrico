# -*- coding: utf-8 -*-
"""
RE7_ALIGN_COORDS_v01.py
Alinea coordenadas de segmentos DXF (globales) a coordenadas del modelo Revit
(locales) aplicando el desfase virtual por apartamento.

Lee los segmentos generados por RE7_SEGMENTAR_CONDUITS_v01 y los dispositivos
colectados por RE7_PREFLIGHT_PYREVIT_v03, agrupa dispositivos en clusters
espaciales (uno por apartamento), y para cada apartamento de segmentos busca
el cluster de dispositivos que mejor coincide (por patron de extremos) para
calcular el offset (dx, dy) que lleva los segmentos al sistema local del modelo.

Escribe: data/f7_segmentos_f01_f02_v02_aligned.json  (segmentos con offset aplicado)
Escribe: data/f7_align_offsets_v01.json              (offsets calculados por apto)

Entorno: CPython 3.12 (sin Revit, sin clr).
Requiere: $env:REVITELECTRICO_ROOT
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FT_A_MM = 304.8

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


def dist_xy(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def agrupar_dispositivos_por_cluster(
    dispositivos: list[dict[str, Any]], tam_celda_mm: float = 3000.0
) -> dict[str, list[dict[str, Any]]]:
    """Agrupa dispositivos en cajas espaciales (una caja ~= un apartamento)."""
    grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for d in dispositivos:
        x = d.get("x_mm")
        y = d.get("y_mm")
        if x is None or y is None:
            continue
        gx = int(x // tam_celda_mm)
        gy = int(y // tam_celda_mm)
        grid[(gx, gy)].append(d)
    return {f"{gx},{gy}": ds for (gx, gy), ds in grid.items() if ds}


def centroide(puntos: list[list[float]]) -> tuple[float, float]:
    n = len(puntos)
    if n == 0:
        return (0.0, 0.0)
    sx = sum(p[0] for p in puntos)
    sy = sum(p[1] for p in puntos)
    return (sx / n, sy / n)


def extremos_de_apartamento(
    segmentos: list[dict[str, Any]], apto: str
) -> list[list[float]]:
    extremos: list[list[float]] = []
    for s in segmentos:
        if s.get("apto") != apto:
            continue
        extremos.append(s["a_mm"])
        extremos.append(s["b_mm"])
    return extremos


def contar_coincidencias(
    extremos: list[list[float]],
    dispositivos: list[dict[str, Any]],
    dx: float,
    dy: float,
    tolerancia_mm: float,
) -> int:
    """Cuenta cuántos extremos (desplazados dx,dy) quedan <= tolerancia de un dispositivo."""
    pts_dis = [
        (d["x_mm"], d["y_mm"])
        for d in dispositivos
        if d.get("x_mm") is not None and d.get("y_mm") is not None
    ]
    if not pts_dis or not extremos:
        return 0
    n_match = 0
    for e in extremos:
        ex = e[0] + dx
        ey = e[1] + dy
        mejor = min(dist_xy([ex, ey], p) for p in pts_dis)
        if mejor <= tolerancia_mm:
            n_match += 1
    return n_match


def buscar_offset_por_apartamento(
    segmentos: list[dict[str, Any]],
    dispositivos: list[dict[str, Any]],
    apto: str,
    clusters: dict[str, list[dict[str, Any]]],
    tolerancia_mm: float = 300.0,
) -> dict[str, Any] | None:
    """Para un apartamento, busca el cluster de dispositivos que mejor coincide
    y devuelve el offset (dx,dy) que alinea los extremos de segmento con ese cluster."""
    extremos = extremos_de_apartamento(segmentos, apto)
    if not extremos:
        return None
    cen_ext = centroide(extremos)

    mejor_cluster: str | None = None
    mejor_offset: tuple[float, float] | None = None
    mejor_n_match = -1
    mejor_detalle: str = ""

    for clave, disps in clusters.items():
        if not disps:
            continue
        pts = [(d["x_mm"], d["y_mm"]) for d in disps if d.get("x_mm") is not None and d.get("y_mm") is not None]
        if not pts:
            continue
        cen_dis = centroide(pts)
        dx = cen_dis[0] - cen_ext[0]
        dy = cen_dis[1] - cen_ext[1]
        n_match = contar_coincidencias(extremos, disps, dx, dy, tolerancia_mm)
        if n_match > mejor_n_match:
            mejor_n_match = n_match
            mejor_cluster = clave
            mejor_offset = (dx, dy)
            mejor_detalle = f"cluster={clave} n_disps={len(disps)} n_match={n_match}/{len(extremos)}"

    if mejor_offset is None:
        return None

    dx, dy = mejor_offset
    return {
        "apto": apto,
        "cluster": mejor_cluster,
        "dx_mm": round(dx, 3),
        "dy_mm": round(dy, 3),
        "n_extremos": len(extremos),
        "n_match": mejor_n_match,
        "detalle": mejor_detalle,
    }


def aplicar_offset(
    segmentos: list[dict[str, Any]],
    offsets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in segmentos:
        apto = s.get("apto", "")
        off = offsets.get(apto)
        dx = off["dx_mm"] if off else 0.0
        dy = off["dy_mm"] if off else 0.0
        ns = dict(s)
        ns["a_mm"] = [round(s["a_mm"][0] + dx, 3), round(s["a_mm"][1] + dy, 3), s["a_mm"][2]]
        ns["b_mm"] = [round(s["b_mm"][0] + dx, 3), round(s["b_mm"][1] + dy, 3), s["b_mm"][2]]
        ns["offset_aplicado"] = {"dx_mm": dx, "dy_mm": dy}
        out.append(ns)
    return out


def evaluar_cobertura(
    segmentos_alineados: list[dict[str, Any]],
    dispositivos: list[dict[str, Any]],
    tolerancia_mm: float = 300.0,
) -> dict[str, Any]:
    extremos: list[list[float]] = []
    for s in segmentos_alineados:
        extremos.append(s["a_mm"])
        extremos.append(s["b_mm"])
    pts_dis = [
        (d["x_mm"], d["y_mm"])
        for d in dispositivos
        if d.get("x_mm") is not None and d.get("y_mm") is not None
    ]
    cubiertos = 0
    distancias: list[float] = []
    for e in extremos:
        mejor = min(dist_xy(e, p) for p in pts_dis) if pts_dis else float("inf")
        distancias.append(mejor)
        if mejor <= tolerancia_mm:
            cubiertos += 1
    distancias.sort()
    n = len(distancias)
    return {
        "endpoints": n,
        "cubiertos": cubiertos,
        "cobertura": round(cubiertos / n, 4) if n else 0.0,
        "p50_mm": round(distancias[n // 2], 2) if n else None,
        "p95_mm": round(distancias[int(n * 0.95)], 2) if n else None,
        "max_mm": round(distancias[-1], 2) if n else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Alinea coordenadas de segmentos DXF al modelo Revit (desfase virtual por apto)"
    )
    ap.add_argument("--segmentos", default="data/f7_segmentos_f01_f02_v01.json")
    ap.add_argument("--preflight", default="data/f7_preflight_v03.json")
    ap.add_argument("--out-segmentos", default="data/f7_segmentos_f01_f02_v02_aligned.json")
    ap.add_argument("--out-offsets", default="data/f7_align_offsets_v01.json")
    ap.add_argument("--tolerancia-mm", type=float, default=300.0)
    ap.add_argument("--tam-celda-mm", type=float, default=3000.0)
    args = ap.parse_args(argv)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if not raiz:
        print("ERROR: falta REVITELECTRICO_ROOT", file=sys.stderr)
        return 2

    seg_path = resolver_ruta(args.segmentos)
    pre_path = resolver_ruta(args.preflight)
    if not seg_path.exists():
        print(f"ERROR: no existe {seg_path}", file=sys.stderr)
        return 2
    if not pre_path.exists():
        print(f"ERROR: no existe {pre_path}", file=sys.stderr)
        return 2

    seg_data = cargar_json(seg_path)
    pre_data = cargar_json(pre_path)

    segmentos = seg_data.get("segmentos", [])
    dispositivos = pre_data.get("dispositivos", [])
    dispositivos_validos = [
        d for d in dispositivos if d.get("x_mm") is not None and d.get("y_mm") is not None
    ]

    aptos = sorted({s.get("apto") for s in segmentos if s.get("apto")})
    print(f"Apartamentos en segmentos: {aptos}")
    print(f"Dispositivos en modelo: {len(dispositivos_validos)}")

    clusters = agrupar_dispositivos_por_cluster(dispositivos_validos, args.tam_celda_mm)
    print(f"Clusters espaciales detectados: {len(clusters)}")

    offsets: dict[str, dict[str, Any]] = {}
    for apto in aptos:
        res = buscar_offset_por_apartamento(
            segmentos, dispositivos_validos, apto, clusters, args.tolerancia_mm
        )
        if res:
            offsets[apto] = res
            print(f"  {apto}: dx={res['dx_mm']} dy={res['dy_mm']} | {res['detalle']}")
        else:
            print(f"  {apto}: NO SE ENCONTRO OFFSET")

    segmentos_alineados = aplicar_offset(segmentos, offsets)

    cobertura = evaluar_cobertura(segmentos_alineados, dispositivos_validos, args.tolerancia_mm)
    print()
    print("COBERTURA DESPUES DE ALINEAR:")
    print(json.dumps(cobertura, ensure_ascii=True, indent=2))

    guardar_json(resolver_ruta(args.out_segmentos), {
        "version": "v02_aligned",
        "script": "RE7_ALIGN_COORDS_v01",
        "segmentos": segmentos_alineados,
        "resumen": {
            "n_segmentos": len(segmentos_alineados),
            "n_apartamentos": len(aptos),
            "offsets": {k: {"dx_mm": v["dx_mm"], "dy_mm": v["dy_mm"]} for k, v in offsets.items()},
        },
    })
    guardar_json(resolver_ruta(args.out_offsets), {
        "version": "v01",
        "script": "RE7_ALIGN_COORDS_v01",
        "offsets": offsets,
    })
    print(f"\nSegmentos alineados: {args.out_segmentos}")
    print(f"Offsets: {args.out_offsets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
