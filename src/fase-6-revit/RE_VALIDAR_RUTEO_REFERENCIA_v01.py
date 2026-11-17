# -*- coding: utf-8 -*-
"""Valida el ruteo de referencia exportado de V02-f (F 01 / F 02).

Entrada: los dos JSON que exporta el canal MCP desde Revit
(``data/v02f/dispositivos_v01.json`` y ``data/v02f/conduits_v01.json``).

No modifica el modelo. Comprueba:

1. Cuantos tramos hay y cuanta longitud suman.
2. Cuantos quedan fuera de rango (restos de prueba a cientos de metros).
3. Que servicio y diametro estan puestos, y cuales faltan.
4. Cuantos aparatos tienen un extremo de conduit cerca (tolerancia 500 mm).

Salida: ``data/v02f/validacion_ruteo_v01.json``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

# Un conduit o aparato a mas de 20 m de altura, o a mas de 50 m del origen en
# planta, no pertenece a un apartamento: es un resto de prueba.
Z_MAX_MM = 20000.0
XY_MAX_MM = 50000.0
TOLERANCIA_CONEXION_MM = 500.0


def esta_fuera_de_rango(punto: Iterable[float]) -> bool:
    """True si el punto (x, y, z en mm) cae fuera del volumen del edificio."""
    x, y, z = list(punto)[:3]
    return abs(z) > Z_MAX_MM or abs(x) > XY_MAX_MM or abs(y) > XY_MAX_MM


def extremos(conduits: list[dict[str, Any]]) -> list[list[float]]:
    """Devuelve todos los extremos de los tramos."""
    puntos: list[list[float]] = []
    for c in conduits:
        puntos.append(c["a"])
        puntos.append(c["b"])
    return puntos


def distancia_minima(punto: Iterable[float], candidatos: list[list[float]]) -> float:
    """Distancia euclidiana en mm al candidato mas cercano."""
    x, y, z = list(punto)[:3]
    return min(math.dist((x, y, z), c) for c in candidatos)


def validar(dispositivos: list[dict[str, Any]],
            conduits: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula el informe de validacion del ruteo de referencia."""
    fuera = [c for c in conduits if esta_fuera_de_rango(c["a"]) or esta_fuera_de_rango(c["b"])]
    validos = [c for c in conduits if c not in fuera]

    por_servicio = Counter((c.get("servicio") or "(vacio)") for c in validos)
    por_diametro = Counter(round(float(c.get("diam_mm", 0.0))) for c in validos)
    sin_servicio = [c["id"] for c in validos if not c.get("servicio")]

    puntos = extremos(validos)
    conexion: dict[int, float] = {}
    for d in dispositivos:
        if esta_fuera_de_rango([d["x"], d["y"], d["z"]]):
            continue
        conexion[int(d["id"])] = round(distancia_minima((d["x"], d["y"], d["z"]), puntos), 1)

    conectados = [i for i, dist in conexion.items() if dist <= TOLERANCIA_CONEXION_MM]
    return {
        "tramos_total": len(conduits),
        "tramos_validos": len(validos),
        "tramos_fuera_de_rango": [c["id"] for c in fuera],
        "longitud_valida_m": round(sum(float(c["long_mm"]) for c in validos) / 1000.0, 3),
        "longitud_total_m": round(sum(float(c["long_mm"]) for c in conduits) / 1000.0, 3),
        "por_servicio": dict(sorted(por_servicio.items())),
        "por_diametro_mm": dict(sorted(por_diametro.items())),
        "tramos_sin_servicio": sin_servicio,
        "tramos_sin_servicio_n": len(sin_servicio),
        "dispositivos_total": len(dispositivos),
        "dispositivos_con_conexion": len(conectados),
        "dispositivos_sin_conexion": sorted(
            i for i in conexion if i not in set(conectados)),
        "tolerancia_conexion_mm": TOLERANCIA_CONEXION_MM,
    }


def main() -> int:
    raiz = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(raiz / "data" / "v02f"))
    args = parser.parse_args()

    base = Path(args.dir)
    dispositivos = json.loads((base / "dispositivos_v01.json").read_text(encoding="utf-8"))
    conduits = json.loads((base / "conduits_v01.json").read_text(encoding="utf-8"))

    informe = validar(dispositivos, conduits)
    destino = base / "validacion_ruteo_v01.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

    print("tramos: {} (validos {}, fuera de rango {})".format(
        informe["tramos_total"], informe["tramos_validos"],
        len(informe["tramos_fuera_de_rango"])))
    print("longitud valida: {} m de {} m".format(
        informe["longitud_valida_m"], informe["longitud_total_m"]))
    print("por servicio:", informe["por_servicio"])
    print("por diametro (mm):", informe["por_diametro_mm"])
    print("tramos sin servicio:", informe["tramos_sin_servicio_n"])
    print("aparatos con conexion: {} de {}".format(
        informe["dispositivos_con_conexion"], informe["dispositivos_total"]))
    print("informe:", destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
