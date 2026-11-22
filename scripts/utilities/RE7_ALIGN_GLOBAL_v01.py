"""
RE7_ALIGN_GLOBAL_v01.py
Encuentra el desfase virtual (offset global) que alinea los extremos de los
segmentos DXF con los dispositivos del modelo Revit, usando votacion por pares
(extremo, dispositivo). Es el enfoque correcto cuando el modelo BIM local tiene
un origen (0,0,0) que corresponde a una coordenada global unica.

Lee:  data/f7_segmentos_f01_f02_v01.json  (segmentos)
Lee:  data/f7_preflight_v03.json          (dispositivos del modelo)
Escribe: data/f7_segmentos_f01_f02_v03_aligned_global.json
Escribe: data/f7_align_global_offset_v01.json

Entorno: CPython 3.12 (sin Revit, sin clr).
Requiere: $env:REVITELECTRICO_ROOT
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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


def dist_xy(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def construir_grid(
    dispositivos: list[dict[str, Any]], tam_celda_mm: float
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for d in dispositivos:
        x = d.get("x_mm")
        y = d.get("y_mm")
        if x is None or y is None:
            continue
        gx = int(x // tam_celda_mm)
        gy = int(y // tam_celda_mm)
        grid[(gx, gy)].append((x, y))
    return grid


def dispositivo_mas_cercano(
    ex: float, ey: float, grid: dict[tuple[int, int], list[tuple[float, float]]],
    tam_celda_mm: float, radio_mm: float
) -> float:
    """Devuelve la distancia al dispositivo mas cercano dentro del radio, o inf."""
    mejor = float("inf")
    gx0 = int(ex // tam_celda_mm)
    gy0 = int(ey // tam_celda_mm)
    celdas = math.ceil(radio_mm / tam_celda_mm) + 1
    for dx in range(-celdas, celdas + 1):
        for dy in range(-celdas, celdas + 1):
            celda = (gx0 + dx, gy0 + dy)
            for (px, py) in grid.get(celda, []):
                dist = dist_xy((ex, ey), (px, py))
                mejor = min(mejor, dist)
    return mejor


def contar_coincidencias(
    extremos: list[tuple[float, float]],
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    tam_celda_mm: float,
    tolerancia_mm: float,
    dx: float,
    dy: float,
) -> int:
    n = 0
    for (ex, ey) in extremos:
        if dispositivo_mas_cercano(ex + dx, ey + dy, grid, tam_celda_mm, tolerancia_mm) <= tolerancia_mm:
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Desfase virtual global por votacion pares extremo-dispositivo"
    )
    ap.add_argument("--segmentos", default="data/f7_segmentos_f01_f02_v01.json")
    ap.add_argument("--preflight", default="data/f7_preflight_v03.json")
    ap.add_argument("--out-segmentos", default="data/f7_segmentos_f01_f02_v03_aligned_global.json")
    ap.add_argument("--out-offset", default="data/f7_align_global_offset_v01.json")
    ap.add_argument("--tolerancia-mm", type=float, default=300.0)
    ap.add_argument("--tam-celda-mm", type=float, default=300.0)
    ap.add_argument("--top-offsets", type=int, default=20)
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
    dispositivos = [
        d for d in pre_data.get("dispositivos", [])
        if d.get("x_mm") is not None and d.get("y_mm") is not None
    ]

    extremos: list[tuple[float, float]] = []
    for s in segmentos:
        extremos.append((s["a_mm"][0], s["a_mm"][1]))
        extremos.append((s["b_mm"][0], s["b_mm"][1]))

    print(f"Extremos de segmento: {len(extremos)}")
    print(f"Dispositivos en modelo: {len(dispositivos)}")

    if not extremos or not dispositivos:
        print("ERROR: no hay extremos o dispositivos.")
        return 2

    # 1. Voting: para cada par (extremo, dispositivo), el offset candidato
    #    es dispositivo - extremo. Redondeamos a multiplos de 50 mm para agrupar.
    votos: Counter[tuple[float, float]] = Counter()
    redondeo = 50.0
    for (ex, ey) in extremos:
        for d in dispositivos:
            dx = d["x_mm"] - ex
            dy = d["y_mm"] - ey
            dx_r = round(dx / redondeo) * redondeo
            dy_r = round(dy / redondeo) * redondeo
            votos[(dx_r, dy_r)] += 1

    total_pares = len(extremos) * len(dispositivos)
    print(f"Pares (extremo, dispositivo) evaluados: {total_pares}")
    print(f"Offsets candidatos unicos: {len(votos)}")

    # 2. Tomar los top offsets por votos y verificar exactamente con grid.
    grid = construir_grid(dispositivos, args.tam_celda_mm)
    top = votos.most_common(args.top_offsets)

    print("\nTop offsets por votos (verificacion exacta):")
    resultados: list[dict[str, Any]] = []
    for (dx, dy), votos_n in top:
        n_match = contar_coincidencias(extremos, grid, args.tam_celda_mm, args.tolerancia_mm, dx, dy)
        cobertura = n_match / len(extremos)
        resultados.append({
            "dx_mm": round(dx, 3),
            "dy_mm": round(dy, 3),
            "votos": votos_n,
            "n_match": n_match,
            "cobertura": round(cobertura, 4),
        })
        print(f"  dx={dx:>14.1f} dy={dy:>14.1f} votos={votos_n:>5} match={n_match:>3}/{len(extremos)} ({cobertura*100:.1f}%)")

    # 3. Elegir el mejor offset por n_match (desempate por votos).
    resultados.sort(key=lambda r: (r["n_match"], r["votos"]), reverse=True)
    mejor = resultados[0]
    print(f"\nMEJOR OFFSET: dx={mejor['dx_mm']} dy={mejor['dy_mm']} match={mejor['n_match']}/{len(extremos)}")

    # 4. Aplicar offset a todos los segmentos y guardar.
    segmentos_alineados = []
    for s in segmentos:
        ns = dict(s)
        ns["a_mm"] = [round(s["a_mm"][0] + mejor["dx_mm"], 3),
                      round(s["a_mm"][1] + mejor["dy_mm"], 3), s["a_mm"][2]]
        ns["b_mm"] = [round(s["b_mm"][0] + mejor["dx_mm"], 3),
                      round(s["b_mm"][1] + mejor["dy_mm"], 3), s["b_mm"][2]]
        ns["offset_global"] = {"dx_mm": mejor["dx_mm"], "dy_mm": mejor["dy_mm"]}
        segmentos_alineados.append(ns)

    # 5. Cobertura final por apartamento y global.
    pts_dis = [(d["x_mm"], d["y_mm"]) for d in dispositivos]
    cobertura_por_apto: dict[str, dict[str, Any]] = {}
    aptos = sorted({s.get("apto") for s in segmentos if s.get("apto")})
    for apto in aptos:
        ext_apto: list[tuple[float, float]] = []
        for s in segmentos_alineados:
            if s.get("apto") == apto:
                ext_apto.append((s["a_mm"][0], s["a_mm"][1]))
                ext_apto.append((s["b_mm"][0], s["b_mm"][1]))
        cub = 0
        dists: list[float] = []
        for e in ext_apto:
            mejor_dist = min(dist_xy(e, p) for p in pts_dis) if pts_dis else float("inf")
            dists.append(mejor_dist)
            if mejor_dist <= args.tolerancia_mm:
                cub += 1
        dists.sort()
        n = len(dists)
        cobertura_por_apto[apto] = {
            "endpoints": n,
            "cubiertos": cub,
            "cobertura": round(cub / n, 4) if n else 0.0,
            "p50_mm": round(dists[n // 2], 2) if n else None,
            "p95_mm": round(dists[int(n * 0.95)], 2) if n else None,
            "max_mm": round(dists[-1], 2) if n else None,
        }

    todos_extremos: list[tuple[float, float]] = []
    for s in segmentos_alineados:
        todos_extremos.append((s["a_mm"][0], s["a_mm"][1]))
        todos_extremos.append((s["b_mm"][0], s["b_mm"][1]))
    cub_tot = 0
    dist_tot: list[float] = []
    for e in todos_extremos:
        md = min(dist_xy(e, p) for p in pts_dis) if pts_dis else float("inf")
        dist_tot.append(md)
        if md <= args.tolerancia_mm:
            cub_tot += 1
    dist_tot.sort()
    nt = len(dist_tot)

    reporte_alineado = {
        "version": "v03_aligned_global",
        "script": "RE7_ALIGN_GLOBAL_v01",
        "offset_global": {"dx_mm": mejor["dx_mm"], "dy_mm": mejor["dy_mm"]},
        "parametros": {
            "tolerancia_mm": args.tolerancia_mm,
            "tam_celda_mm": args.tam_celda_mm,
            "top_offsets": args.top_offsets,
        },
        "verificacion_global": {
            "endpoints": nt,
            "cubiertos": cub_tot,
            "cobertura": round(cub_tot / nt, 4) if nt else 0.0,
            "p50_mm": round(dist_tot[nt // 2], 2) if nt else None,
            "p95_mm": round(dist_tot[int(nt * 0.95)], 2) if nt else None,
            "max_mm": round(dist_tot[-1], 2) if nt else None,
        },
        "cobertura_por_apartamento": cobertura_por_apto,
        "top_offsets": resultados[: args.top_offsets],
        "segmentos": segmentos_alineados,
    }
    guardar_json(resolver_ruta(args.out_segmentos), reporte_alineado)

    guardar_json(resolver_ruta(args.out_offset), {
        "version": "v01",
        "script": "RE7_ALIGN_GLOBAL_v01",
        "offset_global": {"dx_mm": mejor["dx_mm"], "dy_mm": mejor["dy_mm"]},
        "verificacion_global": reporte_alineado["verificacion_global"],
        "cobertura_por_apartamento": cobertura_por_apto,
    })

    print(f"\nSegmentos alineados: {args.out_segmentos}")
    print(f"Offset guardado: {args.out_offset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
