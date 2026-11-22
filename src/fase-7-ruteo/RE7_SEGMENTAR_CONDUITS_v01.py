"""
RE7_SEGMENTAR_CONDUITS_v01.py
Etapa 0 del ruteo F7: descompone cada polilinea de conduits en segmentos rectos.

Entrada: JSON de conduits extraido del DXF (data/conduits_dxf_v01.json,
         conduits_dxf_v01_E06.json, ...)
Salida:  JSON de segmentos listo para el preflight y el analizador.
Entorno: CPython 3.12 (sin Revit, sin clr, sin requests).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FT_A_MM = 304.8
MIN_SEGMENTO_MM_DEFAULT = 3.05
DEDUP_PUNTOS_MM_DEFAULT = 1.0
Z_DIFERENCIA_UMBRAL_MM = 5.0
LARGO_RELATIVO_DIFERENCIA = 0.02

RAIZ = Path(__file__).resolve().parents[2]


def resolver_ruta(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else RAIZ / p


@dataclass(frozen=True)
class Punto:
    x: float
    y: float
    z: float

    def distancia(self, otro: Punto) -> float:
        return math.sqrt(
            (self.x - otro.x) ** 2 + (self.y - otro.y) ** 2 + (self.z - otro.z) ** 2
        )

    def como_lista(self) -> list[float]:
        return [self.x, self.y, self.z]


def _numero(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _punto_mm(tripleta: Any) -> Punto | None:
    """Convierte una tripleta del JSON a Punto en milímetros.

    Los JSON de conduits (extraccion DXF) traen x,y en metros y z en
    milímetros (coherente con z_absoluta_m). Se normaliza todo a mm para
    que distancias, diametro_mm y el reporte final queden en la misma
    unidad que el resto del pipeline de Revit (pies * 304.8).
    """
    if not isinstance(tripleta, (list, tuple)) or len(tripleta) < 3:
        return None
    x = _numero(tripleta[0])
    y = _numero(tripleta[1])
    z = _numero(tripleta[2])
    if x is None or y is None or z is None:
        return None
    return Punto(round(float(x) * 1000.0, 4), round(float(y) * 1000.0, 4), round(float(z), 4))


def normalizar_polilinea(
    conduit: dict[str, Any], dedup_mm: float
) -> tuple[list[Punto], list[dict[str, Any]], str]:
    """Devuelve (puntos, avisos, origen).

    Origen es "puntos_2d" cuando la polilinea existe, "a_b" si hay que
    reconstruirla solo con los extremos.
    """
    avisos: list[dict[str, Any]] = []
    pid = str(conduit.get("id", "?"))
    pts2d = conduit.get("puntos_2d") or []
    puntos: list[Punto] = []
    origen = "a_b"

    if isinstance(pts2d, list) and len(pts2d) >= 2:
        pa = _punto_mm(conduit.get("a"))
        pb = _punto_mm(conduit.get("b"))
        za = pa.z if pa else 0.0
        zb = pb.z if pb else 0.0
        z_constante = abs(za - zb) < Z_DIFERENCIA_UMBRAL_MM
        acumulado = 0.0
        prev_xy: tuple[float, float] | None = None
        for par in pts2d:
            if not isinstance(par, (list, tuple)) or len(par) < 2:
                continue
            x = _numero(par[0])
            y = _numero(par[1])
            if x is None or y is None:
                continue
            if prev_xy is not None:
                acumulado += math.hypot(x - prev_xy[0], y - prev_xy[1])
            prev_xy = (float(x), float(y))
            if z_constante:
                z = za
            else:
                total = math.hypot(
                    float(pts2d[-1][0]) - float(pts2d[0][0]),
                    float(pts2d[-1][1]) - float(pts2d[0][1]),
                )
                z = za + (acumulado / total * (zb - za)) if total > 0 else za
            puntos.append(Punto(round(float(x) * 1000.0, 4), round(float(y) * 1000.0, 4), round(z, 4)))
        origen = "puntos_2d"
    else:
        pa = _punto_mm(conduit.get("a"))
        pb = _punto_mm(conduit.get("b"))
        if pa is None or pb is None:
            return (
                [],
                [
                    {
                        "polilinea_id": pid,
                        "tipo": "dato_invalido",
                        "detalle": "a/b faltantes o no numericos",
                    }
                ],
                origen,
            )
        puntos = [pa, pb]

    if len(puntos) < 2:
        return (
            [],
            [
                {
                    "polilinea_id": pid,
                    "tipo": "polilinea_sin_longitud",
                    "detalle": "menos de 2 puntos validos",
                }
            ],
            origen,
        )

    # Deduplicar puntos consecutivos muy cercanos
    depurada: list[Punto] = [puntos[0]]
    duplicados = 0
    for pt in puntos[1:]:
        if depurada[-1].distancia(pt) < dedup_mm:
            duplicados += 1
            continue
        depurada.append(pt)
    if duplicados:
        avisos.append(
            {
                "polilinea_id": pid,
                "tipo": "puntos_duplicados",
                "detalle": f"{duplicados} punto(s) eliminados por proximidad (< {dedup_mm} mm)",
            }
        )
    puntos = depurada

    if len(puntos) < 2:
        return (
            [],
            [
                {
                    "polilinea_id": pid,
                    "tipo": "polilinea_sin_longitud",
                    "detalle": "despues del dedup queda menos de 2 puntos",
                }
            ],
            origen,
        )

    return puntos, avisos, origen


def segmentar_conduit(
    conduit: dict[str, Any], dedup_mm: float, min_segmento_mm: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Devuelve (segmentos, descartados, avisos)."""
    pid = str(conduit.get("id", "?"))
    apto = str(conduit.get("apartamento", "?"))
    servicio = str(conduit.get("servicio", "?"))
    diametro_mm = _numero(conduit.get("diametro_mm")) or 0.0
    tamano = str(conduit.get("diametro_pulgadas", "")).replace('"', "").strip()
    handle = str(conduit.get("handle_dxf", ""))
    cota_m = _numero(conduit.get("cota_m"))
    z_absoluta_m = _numero(conduit.get("z_absoluta_m"))
    largo_declarado = _numero(conduit.get("largo_mm"))

    puntos, avisos_pol, origen = normalizar_polilinea(conduit, dedup_mm)

    if len(puntos) >= 2 and abs(puntos[0].z - puntos[-1].z) >= Z_DIFERENCIA_UMBRAL_MM:
        avisos_pol.append(
            {
                "polilinea_id": pid,
                "tipo": "z_variable",
                "detalle": f"z inicial {round(puntos[0].z, 2)}mm != z final {round(puntos[-1].z, 2)}mm",
            }
        )
        pa = _punto_mm(conduit.get("a"))
        pb = _punto_mm(conduit.get("b"))
        if (
            pa is not None
            and pb is not None
            and z_absoluta_m is not None
            and abs(pa.z - pb.z) >= Z_DIFERENCIA_UMBRAL_MM
        ):
            avisos_pol.append(
                {
                    "polilinea_id": pid,
                    "tipo": "z_inconsistente",
                    "detalle": f"z_absoluta_m {z_absoluta_m} != a[2]/1000 {pa.z / 1000.0}",
                }
            )

    # Alerta de unidad en largo_mm: los datos traen el campo en metros, no en mm.
    largo_polilinea_mm = 0.0
    for i in range(len(puntos) - 1):
        largo_polilinea_mm += puntos[i].distancia(puntos[i + 1])
    if (
        largo_declarado is not None
        and largo_polilinea_mm > 0
        and abs(largo_declarado - largo_polilinea_mm / 1000.0)
        < max(0.01, largo_polilinea_mm / 1000.0 * LARGO_RELATIVO_DIFERENCIA)
    ):
            avisos_pol.append(
                {
                    "polilinea_id": pid,
                    "tipo": "largo_mm_en_metros",
                    "detalle": f"declarado={largo_declarado} vs computed={round(largo_polilinea_mm / 1000.0, 3)}m",
                }
            )

    segmentos: list[dict[str, Any]] = []
    descartados: list[dict[str, Any]] = []
    for i in range(len(puntos) - 1):
        a = puntos[i]
        b = puntos[i + 1]
        largo = a.distancia(b)
        if largo < min_segmento_mm:
            descartados.append(
                {
                    "polilinea_id": pid,
                    "segmento": f"S{i + 1:02d}",
                    "motivo": "segmento_corto",
                    "detalle": f"largo {round(largo, 2)} mm < minimo {min_segmento_mm} mm",
                }
            )
            continue
        segmentos.append(
            {
                "id": f"{pid}-S{i + 1:02d}",
                "polilinea_id": pid,
                "apto": apto,
                "servicio": servicio,
                "tamano": tamano,
                "diametro_mm": round(diametro_mm, 4),
                "handle_dxf": handle,
                "a_mm": a.como_lista(),
                "b_mm": b.como_lista(),
                "largo_mm": round(largo, 3),
                "origen": origen,
                "cota_m": cota_m,
                "z_absoluta_m": z_absoluta_m,
            }
        )
    return segmentos, descartados, avisos_pol


def segmentar_documento(
    data: dict[str, Any], dedup_mm: float, min_segmento_mm: float
) -> dict[str, Any]:
    conduits = data.get("conduits") or []
    todos_segmentos: list[dict[str, Any]] = []
    todos_descartados: list[dict[str, Any]] = []
    todos_avisos: list[dict[str, Any]] = []
    largo_total_mm = 0.0
    por_servicio: dict[str, int] = {}
    por_apto: dict[str, int] = {}
    por_tamano: dict[str, int] = {}
    polilineas_con_quiebre = 0

    for conduit in conduits:
        pts2d = conduit.get("puntos_2d") or []
        if isinstance(pts2d, list) and len(pts2d) > 2:
            polilineas_con_quiebre += 1
        segmentos, descartados, avisos = segmentar_conduit(
            conduit, dedup_mm, min_segmento_mm
        )
        todos_segmentos.extend(segmentos)
        todos_descartados.extend(descartados)
        todos_avisos.extend(avisos)
        for s in segmentos:
            largo_total_mm += s["largo_mm"]
            por_servicio[s["servicio"]] = por_servicio.get(s["servicio"], 0) + 1
            por_apto[s["apto"]] = por_apto.get(s["apto"], 0) + 1
            por_tamano[s["tamano"]] = por_tamano.get(s["tamano"], 0) + 1

    ids = [s["id"] for s in todos_segmentos]
    ids_polilineas = {s["polilinea_id"] for s in todos_segmentos}
    reporte = {
        "version": "v01",
        "script": "RE7_SEGMENTAR_CONDUITS_v01",
        "resumen": {
            "polilineas_entrada": len(conduits),
            "segmentos": len(todos_segmentos),
            "descartados": len(todos_descartados),
            "avisos": len(todos_avisos),
            "longitud_total_m": round(largo_total_mm / 1000.0, 3),
            "largo_min_mm": round(
                min((s["largo_mm"] for s in todos_segmentos), default=0.0), 3
            ),
            "largo_max_mm": round(
                max((s["largo_mm"] for s in todos_segmentos), default=0.0), 3
            ),
            "largo_medio_mm": (
                round(largo_total_mm / len(todos_segmentos), 3)
                if todos_segmentos
                else 0.0
            ),
            "polilineas_con_quiebre": polilineas_con_quiebre,
            "segmentos_por_polilinea_max": max(
                (
                    sum(1 for s in todos_segmentos if s["polilinea_id"] == pid)
                    for pid in ids_polilineas
                ),
                default=0,
            ),
            "por_servicio": dict(sorted(por_servicio.items())),
            "por_apto": dict(sorted(por_apto.items())),
            "por_tamano": dict(sorted(por_tamano.items())),
        },
        "segmentos": todos_segmentos,
        "descartados": todos_descartados,
        "avisos": todos_avisos,
        "ids_unicos": len(ids) == len(set(ids)),
    }
    return reporte


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Segmenta polilineas de conduits en tramos rectos (Etapa 0 F7)."
    )
    parser.add_argument(
        "--input",
        default="data/conduits_dxf_v01.json",
        help="JSON de conduits de entrada (relativo al proyecto o absoluto)",
    )
    parser.add_argument(
        "--output",
        default="data/f7_segmentos_v01.json",
        help="JSON de segmentos de salida",
    )
    parser.add_argument(
        "--dedup-mm", type=float, default=DEDUP_PUNTOS_MM_DEFAULT
    )
    parser.add_argument(
        "--min-mm", type=float, default=MIN_SEGMENTO_MM_DEFAULT
    )
    args = parser.parse_args(argv)

    entrada = resolver_ruta(args.input)
    salida = resolver_ruta(args.output)
    if not entrada.exists():
        print(f"ERROR: no existe el archivo de entrada: {entrada}")
        return 2

    with open(entrada, "r") as f:
        data = json.load(f)

    reporte = segmentar_documento(data, args.dedup_mm, args.min_mm)
    reporte["generado_utc"] = datetime.datetime.now(datetime.UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    reporte["fuente"] = {
        "archivo": str(entrada),
        "sha256": _sha256(entrada),
        "bytes": entrada.stat().st_size,
    }
    reporte["parametros"] = {
        "dedup_mm": args.dedup_mm,
        "min_segmento_mm": args.min_mm,
    }

    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w") as f:
        json.dump(reporte, f, ensure_ascii=True, indent=2)

    r = reporte["resumen"]
    print(
        "SEGMENTACION TERMINADA: {} segmentos de {} polilineas | longitud total {} m | descartados {} | avisos {}".format(
            r["segmentos"], r["polilineas_entrada"], r["longitud_total_m"], r["descartados"], r["avisos"]
        )
    )
    print(f"Salida: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
