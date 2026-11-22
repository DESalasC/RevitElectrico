"""
RE7_ANALIZAR_PREFLIGHT_v01.py
Etapa 0 del ruteo F7: analiza el reporte de preflight (solo lecturas de Revit)
y verifica que el modelo este listo para crear conduits.
Entorno: CPython 3.12 (sin Revit, sin clr).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, cast

RAIZ = Path(__file__).resolve().parents[2]


def resolver_ruta(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else RAIZ / p


def _cargar_json(path: Path) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    s = sorted(valores)
    k = max(1, min(len(s), math.ceil(p / 100.0 * len(s))))
    return s[k - 1]


def _mediana(valores: list[float]) -> float | None:
    if not valores:
        return None
    s = sorted(valores)
    n = len(s)
    mitad = n // 2
    return s[mitad] if n % 2 else (s[mitad - 1] + s[mitad]) / 2.0


def _round2(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


def _dist_xy(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist_3d(a: list[float], b: list[float]) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _endpoints_planificados(segmentos: dict[str, Any] | None) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    if not segmentos:
        return endpoints
    for s in segmentos.get("segmentos", []):
        for extremo in ("a_mm", "b_mm"):
            p = s.get(extremo)
            if p and len(p) == 3:
                endpoints.append({"id": s.get("id"), "extremo": extremo, "p": [float(v) for v in p]})
    return endpoints


def evaluar(
    config: dict[str, Any],
    preflight: dict[str, Any],
    segmentos: dict[str, Any] | None,
) -> dict[str, Any]:
    """Devuelve un reporte de checks con estado OK/FALLA/INSUFICIENTE/NO_APLICA."""
    tol = config.get("tolerancias", {})
    offset_mm = float(tol.get("offset_mm", 50.0))
    dispositivo_xy_mm = float(tol.get("dispositivo_xy_mm", 300.0))
    match_conduit_mm = float(tol.get("match_conduit_mm", 1000.0))
    nivel_cfg = config.get("nivel", {})
    elevacion_esperada_mm = float(nivel_cfg.get("elevacion_m", 13.22)) * 1000.0
    tolerancia_nivel_mm = float(nivel_cfg.get("tolerancia_mm", 1.0))
    tipos_cfg = config.get("tipos_conduit", {})

    checks: dict[str, dict[str, Any]] = {}

    # 1. Modelo guardado: informativo. La creacion no debe tocar un modelo sucio.
    doc = preflight.get("documento", {})
    modificado = bool(doc.get("modificado", True))
    checks["modelo_guardado"] = {
        "estado": "OK" if not modificado else "AVISO",
        "detalle": "Documento {} sin cambios sin guardar".format(
            doc.get("titulo", "desconocido")
        ),
    }

    # 2. Nivel Piso 5 (identidad por elevacion, tolerancia 1 mm)
    nivel_p5 = preflight.get("nivel_piso5") or {}
    encontrado = bool(nivel_p5.get("encontrado", False))
    delta_mm = nivel_p5.get("delta_mm")
    nivel_ok = encontrado and delta_mm is not None and abs(delta_mm) <= tolerancia_nivel_mm
    checks["nivel_piso5"] = {
        "estado": "OK" if nivel_ok else "FALLA",
        "encontrado": encontrado,
        "delta_mm": delta_mm,
        "detalle": "Piso 5 a {} mm (esperado {} +/- {} mm)".format(
            round(nivel_p5.get("elevacion_mm", 0.0), 2)
            if nivel_p5.get("elevacion_mm") is not None
            else "?",
            elevacion_esperada_mm,
            tolerancia_nivel_mm,
        ),
    }

    # 3. Tipos de conduit configurados: presentes y validos en el modelo.
    ids_config = list(tipos_cfg.values())
    presentes = preflight.get("tipos_conduit", [])
    validos = {t.get("id") for t in presentes if t.get("valido")}
    faltantes = [tid for tid in ids_config if tid not in validos]
    checks["tipos_conduit"] = {
        "estado": "OK" if not faltantes else "FALLA",
        "configurados": ids_config,
        "validos_en_modelo": sorted(validos),
        "faltantes": faltantes,
        "detalle": f"{len(ids_config) - len(faltantes)} de {len(ids_config)} tipos configurados estan presentes y validos",
    }

    # 4. Cobertura de dispositivos (XY): cada extremo de tramo cerca de un dispositivo.
    endpoints = _endpoints_planificados(segmentos)
    dispositivos = preflight.get("dispositivos", [])
    distancias_xy: list[float] = []
    cubiertos = 0
    if endpoints and dispositivos:
        for ep in endpoints:
            mejor = min(
                _dist_xy(ep["p"], [float(d.get("x_mm", 0.0)), float(d.get("y_mm", 0.0))])
                for d in dispositivos
            )
            distancias_xy.append(mejor)
            if mejor <= dispositivo_xy_mm:
                cubiertos += 1
        cobertura = cubiertos / len(endpoints)
        cov_ok = cobertura >= 0.9
    else:
        cobertura = None
        cov_ok = False
    checks["cobertura_dispositivos"] = {
        "estado": "OK"
        if cov_ok
        else ("NO_APLICA" if cobertura is None else "FALLA"),
        "endpoints": len(endpoints),
        "cubiertos": cubiertos,
        "cobertura": _round2(cobertura),
        "p50_mm": _round2(_percentil(distancias_xy, 50)) if distancias_xy else None,
        "p95_mm": _round2(_percentil(distancias_xy, 95)) if distancias_xy else None,
        "max_mm": _round2(max(distancias_xy)) if distancias_xy else None,
        "detalle": f"porcentaje de extremos de tramo a <= {dispositivo_xy_mm} mm XY de un dispositivo",
    }

    # 5. Offset estimado contra conduits existentes del modelo (distancia 3D).
    conduits = preflight.get("conduits", [])
    puntos_existentes: list[list[float]] = []
    for c in conduits:
        for extremo in ("a_mm", "b_mm"):
            p = c.get(extremo)
            if p and len(p) == 3:
                puntos_existentes.append([float(v) for v in p])
    deltas_x: list[float] = []
    deltas_y: list[float] = []
    deltas_z: list[float] = []
    n_match = 0
    if endpoints and puntos_existentes:
        for ep in endpoints:
            punto_mas_cerca: list[float] = min(puntos_existentes, key=lambda p: _dist_3d(cast(list[float], ep["p"]), p))
            if _dist_3d(cast(list[float], ep["p"]), punto_mas_cerca) <= match_conduit_mm:
                n_match += 1
                deltas_x.append(cast(list[float], ep["p"])[0] - punto_mas_cerca[0])
                deltas_y.append(cast(list[float], ep["p"])[1] - punto_mas_cerca[1])
                deltas_z.append(cast(list[float], ep["p"])[2] - punto_mas_cerca[2])
    if n_match >= 20:
        mx = _mediana(deltas_x)
        my = _mediana(deltas_y)
        mz = _mediana(deltas_z)
        mad_x = _mediana([abs(d - mx) for d in deltas_x]) if mx is not None else None
        offset_ok = (
            mx is not None
            and my is not None
            and abs(mx) <= offset_mm
            and abs(my) <= offset_mm
        )
        checks["offset_modelo"] = {
            "estado": "OK" if offset_ok else "FALLA",
            "n_match": n_match,
            "mediana_dx_mm": _round2(mx),
            "mediana_dy_mm": _round2(my),
            "mediana_dz_mm": _round2(mz),
            "mad_xy_mm": _round2(mad_x),
            "detalle": "offset estimado del modelo vs plan (mediana de coincidencias cercanas)",
        }
    else:
        checks["offset_modelo"] = {
            "estado": "INSUFICIENTE",
            "n_match": n_match,
            "detalle": "pocas coincidencias (< 20) para estimar offset; revisar manualmente",
        }

    # Veredictos
    criticos = ["nivel_piso5", "tipos_conduit", "offset_modelo", "cobertura_dispositivos"]
    fallas = [c for c in criticos if checks[c]["estado"] == "FALLA"]
    insuficientes = [c for c in criticos if checks[c]["estado"] == "INSUFICIENTE"]
    if fallas:
        veredicto = "NO_APTO"
    elif insuficientes:
        veredicto = "REVISAR"
    else:
        veredicto = "APTO"

    reporte = {
        "version": "v01",
        "script": "RE7_ANALIZAR_PREFLIGHT_v01",
        "veredicto": veredicto,
        "checks": checks,
        "resumen": {
            "modelo_modificado": modificado,
            "endpoints_planificados": len(endpoints),
            "dispositivos_en_modelo": len(dispositivos),
            "conduits_en_modelo": len(conduits),
        },
    }
    return reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analiza el preflight de ruteo F7 (solo lectura)."
    )
    parser.add_argument("--config", default="config/f7_ruteo_v01.json")
    parser.add_argument("--preflight", default="data/f7_preflight_v01.json")
    parser.add_argument("--segmentos", default="data/f7_segmentos_f01_f02_v01.json")
    parser.add_argument("--output", default="data/f7_preflight_analisis_v01.json")
    args = parser.parse_args(argv)

    config = _cargar_json(resolver_ruta(args.config))
    preflight = _cargar_json(resolver_ruta(args.preflight))
    segmentos = None
    seg_path = resolver_ruta(args.segmentos)
    if seg_path.exists():
        segmentos = _cargar_json(seg_path)

    reporte = evaluar(config, preflight, segmentos)
    salida = resolver_ruta(args.output)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w") as f:
        json.dump(reporte, f, ensure_ascii=True, indent=2)

    print("VEREDICTO: {}".format(reporte["veredicto"]))
    for nombre, check in reporte["checks"].items():
        print("  {}: {} | {}".format(nombre, check["estado"], check["detalle"]))
    print(f"Reporte: {salida}")
    return 0 if reporte["veredicto"] == "APTO" else 1


if __name__ == "__main__":
    sys.exit(main())
