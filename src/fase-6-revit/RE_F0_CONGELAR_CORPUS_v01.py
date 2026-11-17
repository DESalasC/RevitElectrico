# -*- coding: utf-8 -*-
"""F0 — Congela el corpus de ruteo de referencia (V02-f, F 01 / F 02).

Lee el export crudo del canal MCP (``data/v02f/``), aplica las exclusiones
aprobadas por el operador y escribe el corpus inmutable en
``data/referencia/ruteo_F01_F02_v01/``:

  dispositivos.json   aparatos y cajas de F 01 / F 02
  conduits.json       tramos validos con servicio
  metricas.json       magnitudes de calibracion del motor de ruteo
  MANIFEST.json       hash SHA-256 de cada archivo y reglas aplicadas

Exclusiones (decision 2026-11-17):

* Tramos fuera de rango: |z| > 20 m o |x|,|y| > 50 m. Son restos de prueba.
* Tramos sin ``Servicio_Conduit``: los cinco, aunque cuatro tenian lectura
  probable. El operador prefirio no inferir servicio en el benchmark.
* Aparatos fuera de rango.

El corpus no se edita a mano: si cambia una regla, se vuelve a minar.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

Z_MAX_MM = 20000.0
XY_MAX_MM = 50000.0
# F 01 y F 02 ocupan la franja este del piso: todos sus aparatos tienen x > 10 m.
# La region se define por caja, no por radio al tablero: un radio de 6 m cortaba
# aparatos legitimos del fondo del apartamento.
REGION = {"x_min": 9000.0, "x_max": 16000.0, "y_min": -2000.0, "y_max": 18000.0}
PANELES = {"F 01": (11611.0, 7534.0), "F 02": (11611.0, 10151.0)}


def fuera_de_rango(punto: list[float]) -> bool:
    x, y, z = punto[:3]
    return abs(z) > Z_MAX_MM or abs(x) > XY_MAX_MM or abs(y) > XY_MAX_MM


def unidad_mas_cercana(x: float, y: float) -> tuple[str | None, float]:
    """Unidad a la que pertenece el punto, y distancia a su tablero en mm.

    Devuelve ``None`` si el punto cae fuera de la region de F 01 / F 02.
    """
    if not (REGION["x_min"] <= x <= REGION["x_max"]
            and REGION["y_min"] <= y <= REGION["y_max"]):
        return None, float("inf")
    nombre, (px, py) = min(PANELES.items(), key=lambda p: math.hypot(p[1][0] - x, p[1][1] - y))
    return nombre, math.hypot(px - x, py - y)


def congelar(dispositivos: list[dict[str, Any]],
             conduits: list[dict[str, Any]]) -> dict[str, Any]:
    """Aplica las exclusiones y calcula el corpus y sus metricas."""
    disp = []
    descartes_disp = []
    for d in dispositivos:
        if fuera_de_rango([d["x"], d["y"], d["z"]]):
            descartes_disp.append({"id": d["id"], "motivo": "fuera_de_rango",
                                   "punto": [d["x"], d["y"], d["z"]]})
            continue
        unidad, distancia = unidad_mas_cercana(d["x"], d["y"])
        if unidad is None:
            descartes_disp.append({"id": d["id"], "motivo": "fuera_de_unidad",
                                   "distancia_mm": round(distancia, 1)})
            continue
        fila = dict(d)
        fila["unidad"] = unidad
        fila["dist_tablero_mm"] = round(distancia, 1)
        disp.append(fila)

    tramos = []
    descartes_con = []
    for c in conduits:
        if fuera_de_rango(c["a"]) or fuera_de_rango(c["b"]):
            descartes_con.append({"id": c["id"], "motivo": "fuera_de_rango"})
            continue
        if not c.get("servicio"):
            descartes_con.append({"id": c["id"], "motivo": "sin_servicio"})
            continue
        tramos.append(dict(c))

    es_caja = lambda d: "Caja" in d.get("fam", "")
    aparatos = [d for d in disp if not es_caja(d)]
    cajas = [d for d in disp if es_caja(d)]
    longitud = sum(float(c["long_mm"]) for c in tramos) / 1000.0

    metricas = {
        "unidades": sorted(PANELES),
        "tramos": len(tramos),
        "longitud_m": round(longitud, 3),
        "dispositivos": len(disp),
        "aparatos": len(aparatos),
        "cajas": len(cajas),
        "m_por_aparato": round(longitud / len(aparatos), 3) if aparatos else None,
        "tramos_por_aparato": round(len(tramos) / len(aparatos), 3) if aparatos else None,
        "por_servicio": dict(sorted(Counter(c["servicio"] for c in tramos).items())),
        "por_diametro_mm": dict(sorted(Counter(round(float(c["diam_mm"])) for c in tramos).items())),
        "por_unidad": dict(sorted(Counter(d["unidad"] for d in disp).items())),
        "descartes_dispositivos": descartes_disp,
        "descartes_conduits": descartes_con,
    }
    return {"dispositivos": disp, "conduits": tramos, "metricas": metricas}


def escribir_corpus(corpus: dict[str, Any], destino: Path) -> dict[str, str]:
    """Escribe el corpus y devuelve el hash SHA-256 de cada archivo."""
    destino.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for nombre, clave in (("dispositivos.json", "dispositivos"),
                          ("conduits.json", "conduits"),
                          ("metricas.json", "metricas")):
        texto = json.dumps(corpus[clave], ensure_ascii=False, indent=1)
        ruta = destino / nombre
        ruta.write_text(texto, encoding="utf-8")
        hashes[nombre] = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    return hashes


def main() -> int:
    raiz = Path(__file__).resolve().parents[2]
    origen = raiz / "data" / "v02f"
    dispositivos = json.loads((origen / "dispositivos_v01.json").read_text(encoding="utf-8"))
    conduits = json.loads((origen / "conduits_v01.json").read_text(encoding="utf-8"))

    corpus = congelar(dispositivos, conduits)
    destino = raiz / "data" / "referencia" / "ruteo_F01_F02_v01"
    hashes = escribir_corpus(corpus, destino)

    manifiesto = {
        "version": "v01",
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "origen": "data/v02f (export MCP de E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt)",
        "reglas": {
            "fuera_de_rango": "|z| > 20000 mm o |x|,|y| > 50000 mm",
            "sin_servicio": "excluidos por decision del operador 2026-11-17",
            "unidad": "region x 9000-16000, y -2000-18000; tablero mas cercano (F 01 / F 02)",
        },
        "hashes": hashes,
    }
    (destino / "MANIFEST.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")

    m = corpus["metricas"]
    print("tramos:", m["tramos"], "longitud:", m["longitud_m"], "m")
    print("dispositivos:", m["dispositivos"], "aparatos:", m["aparatos"], "cajas:", m["cajas"])
    print("m/aparato:", m["m_por_aparato"], "tramos/aparato:", m["tramos_por_aparato"])
    print("por servicio:", m["por_servicio"])
    print("descartes:", len(m["descartes_conduits"]), "tramos,",
          len(m["descartes_dispositivos"]), "dispositivos")
    print("corpus:", destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
