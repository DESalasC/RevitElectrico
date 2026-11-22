# -*- coding: utf-8 -*-
"""
RE7_ANALIZAR_UNIONES_v01.py
Analizador de topología de conduits para detectar puntos de unión/caja de empate.

Lee los conduits creados en Revit (f7_conduits_desde_revit_v01.json) e identifica
puntos donde los extremos de dos o más conduits están cercanos (clustering
espacial), clasificando el tipo de accesorio necesario:
  - 2 conduits en un punto      → Conduit Coupling (unión recta) / Conduit Elbow (codo)
  - 3 conduits en un punto      → Conduit Junction Box Tee (caja de empate T)
  - 4+ conduits en un punto     → Conduit Junction Box Cross (caja de empate +)

Enfoque: "primeros conduits creados" (IDs más bajos) como piloto.

Lee:
  - data/f7_conduits_desde_revit_v01.json  (exportación desde Revit)

Escribe:
  - data/f7_uniones_detectadas_v01.json    (reporte de puntos de unión)

Uso (Python 3.12 externo, no Revit):
    python RE7_ANALIZAR_UNIONES_v01.py [--primeros N] [--tolerancia-mm 100.0]
"""

import argparse
import datetime
import json
import math
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

FT_A_MM = 304.8


def raiz_proyecto() -> str:
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return r"D:\Work\PROJECTS\RevitElectrico"


def cargar_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(path: str, datos: Any) -> None:
    contenido = json.dumps(datos, ensure_ascii=True, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(contenido)


def distancia_puntos(p: Tuple[float, float, float],
                     q: Tuple[float, float, float]) -> float:
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def punto_medio(puntos: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    n = len(puntos)
    return (sum(p[0] for p in puntos) / n,
            sum(p[1] for p in puntos) / n,
            sum(p[2] for p in puntos) / n)


def _find(parent: List[int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: List[int], rank: List[int], a: int, b: int) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        parent[ra] = rb
    elif rank[ra] > rank[rb]:
        parent[rb] = ra
    else:
        parent[rb] = ra
        rank[ra] += 1


def clasificar_tipo_accesorio(num_conduits: int,
                              es_cambio_direccion: bool = False) -> str:
    """Devuelve el tipo de accesorio de conduit recomendado según la topología."""
    if num_conduits >= 4:
        return "Conduit Junction Box - Cross"
    if num_conduits == 3:
        return "Conduit Junction Box - Tee"
    if num_conduits == 2:
        return "Conduit Elbow" if es_cambio_direccion else "Conduit Coupling"
    return "Sin accesorio"


def analizar_uniones(conduits: List[Dict[str, Any]],
                     tolerancia_mm: float = 100.0,
                     primeros: int = 0,
                     celda_mm: float = 100.0) -> Dict[str, Any]:
    """Analiza los conduits y detecta puntos de unión/caja de empate.

    Usa clustering espacial basado en union-find sobre los extremos de conduits:
    dos extremos se agrupan si están dentro de tolerancia_mm. Cada cluster con
    >=2 conduits distintos es un candidato a accesorio.

    Args:
        conduits: lista de dicts con conduit_id, a_mm, b_mm, largo_mm
        tolerancia_mm: distancia máxima (mm) entre extremos para agrupar en un cluster
        primeros: si >0, solo analizar los primeros N conduits (por ID ascendente)
        celda_mm: tamaño de celda para indexación espacial (acelera búsqueda)
    """
    # Ordenar por ID y opcionalmente limitar a los primeros N
    conduits_ordenados = sorted(conduits, key=lambda c: c["conduit_id"])
    if primeros and primeros > 0:
        conduits_ordenados = conduits_ordenados[:primeros]

    # Construir lista de extremos con índice
    # Cada extremo: (conduit_id, extremo_tipo, punto_xyz, indice)
    extremos: List[Tuple[str, str, Tuple[float, float, float], int]] = []
    for c in conduits_ordenados:
        cid = c["conduit_id"]
        a = tuple(float(v) for v in c["a_mm"])
        b = tuple(float(v) for v in c["b_mm"])
        idx = len(extremos)
        extremos.append((cid, "A", a, idx))
        extremos.append((cid, "B", b, idx + 1))

    n = len(extremos)
    parent = list(range(n))
    rank = [0] * n

    # Indexación espacial por grid para evitar O(n^2)
    # Clave de celda: (cx, cy, cz) donde cada coordenada = round(coord / celda_mm)
    celdas: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for i, (cid, tipo, punto, _) in enumerate(extremos):
        clave_celda = (int(punto[0] // celda_mm),
                       int(punto[1] // celda_mm),
                       int(punto[2] // celda_mm))
        celdas[clave_celda].append(i)

    # Buscar extremos cercanos: solo comparar dentro de la misma celda y celdas vecinas
    offsets = [(dx, dy, dz) for dx in (-1, 0, 1)
               for dy in (-1, 0, 1) for dz in (-1, 0, 1)]

    for clave_celda, indices in celdas.items():
        # Recolectar todos los candidatos en esta celda y las 26 vecinas
        candidatos: Set[int] = set()
        for dx, dy, dz in offsets:
            vecina = (clave_celda[0] + dx, clave_celda[1] + dy, clave_celda[2] + dz)
            candidatos.update(celdas.get(vecina, []))

        # Comparar pares dentro del conjunto de candidatos
        lista_candidatos = sorted(candidatos)
        for ii in range(len(lista_candidatos)):
            i = lista_candidatos[ii]
            _, _, p_i, _ = extremos[i]
            for jj in range(ii + 1, len(lista_candidatos)):
                j = lista_candidatos[jj]
                _, _, p_j, _ = extremos[j]
                cid_i = extremos[i][0]
                cid_j = extremos[j][0]
                if cid_i == cid_j:
                    continue  # mismo conduit, ignorar
                if distancia_puntos(p_i, p_j) <= tolerancia_mm:
                    _union(parent, rank, i, j)

    # Agrupar por componente conectada
    componentes: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        raiz = _find(parent, i)
        componentes[raiz].append(i)

    # Filtrar componentes con >= 2 conduits distintos
    puntos_union: List[Dict[str, Any]] = []
    for miembros_idx in componentes.values():
        ids_conduits = sorted(set(extremos[i][0] for i in miembros_idx))
        if len(ids_conduits) < 2:
            continue

        # Punto central del cluster
        puntos_miembros = [extremos[i][2] for i in miembros_idx]
        pc = punto_medio(puntos_miembros)

        # Desviación máxima desde el centro
        max_desvio = max(distancia_puntos(p, pc) for p in puntos_miembros)

        # Determinar cambio de dirección para 2 conduits
        es_cambio_direccion = False
        if len(ids_conduits) == 2:
            vectores = []
            for i in miembros_idx:
                cid = extremos[i][0]
                tipo = extremos[i][1]
                punto = extremos[i][2]
                c = next((x for x in conduits_ordenados if x["conduit_id"] == cid), None)
                if c is None:
                    continue
                a = tuple(float(v) for v in c["a_mm"])
                b = tuple(float(v) for v in c["b_mm"])
                if tipo == "A":
                    # Punto de conexión en A, el otro extremo es B
                    v = (b[0] - punto[0], b[1] - punto[1], b[2] - punto[2])
                else:
                    # Punto de conexión en B, el otro extremo es A
                    v = (a[0] - punto[0], a[1] - punto[1], a[2] - punto[2])
                norm = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
                if norm > 0:
                    v = (v[0] / norm, v[1] / norm, v[2] / norm)
                vectores.append(v)

            if len(vectores) == 2:
                dp = (vectores[0][0] * vectores[1][0] +
                      vectores[0][1] * vectores[1][1] +
                      vectores[0][2] * vectores[1][2])
                # dp ~ -1: direcciones opuestas (recto → coupling)
                # dp ~ 0: perpendiculares (ángulo → codo)
                es_cambio_direccion = dp > -0.5

        tipo_accesorio = clasificar_tipo_accesorio(len(ids_conduits), es_cambio_direccion)

        puntos_union.append({
            "punto_mm": [round(pc[0], 2), round(pc[1], 2), round(pc[2], 2)],
            "conduit_ids": ids_conduits,
            "num_conduits": len(ids_conduits),
            "tipo_accesorio_recomendado": tipo_accesorio,
            "cambio_direccion": es_cambio_direccion,
            "max_desvío_mm": round(max_desvio, 2),
            "miembros": [
                {"conduit_id": extremos[i][0],
                 "extremo": extremos[i][1],
                 "punto_mm": [round(extremos[i][2][0], 2),
                              round(extremos[i][2][1], 2),
                              round(extremos[i][2][2], 2)]}
                for i in miembros_idx
            ],
        })

    # Ordenar por punto (X, Y, Z) para reporte estable
    puntos_union.sort(key=lambda u: (u["punto_mm"][0],
                                      u["punto_mm"][1],
                                      u["punto_mm"][2]))

    # Estadísticas
    por_tipo: Dict[str, int] = defaultdict(int)
    for p in puntos_union:
        por_tipo[p["tipo_accesorio_recomendado"]] += 1

    reporte = {
        "version": "v01",
        "script": "RE7_ANALIZAR_UNIONES_v01",
        "generado_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "parametros": {
            "tolerancia_mm": tolerancia_mm,
            "primeros_conduits": primeros if primeros else "todos",
            "total_conduits_analizados": len(conduits_ordenados),
            "celda_mm": celda_mm,
        },
        "resumen": {
            "puntos_union_detectados": len(puntos_union),
            "conduits_con_union": len(set(
                cid for p in puntos_union for cid in p["conduit_ids"]
            )),
            "por_tipo_accesorio": dict(sorted(por_tipo.items())),
        },
        "puntos_union": puntos_union,
    }
    return reporte


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detecta puntos de unión/caja de empate entre conduits creados."
    )
    parser.add_argument(
        "--input",
        default="data/f7_conduits_desde_revit_v01.json",
        help="JSON de conduits desde Revit (relativo al proyecto o absoluto)",
    )
    parser.add_argument(
        "--output",
        default="data/f7_uniones_detectadas_v01.json",
        help="JSON de reporte de uniones detectadas",
    )
    parser.add_argument(
        "--primeros",
        type=int,
        default=0,
        help="Si se especifica, solo analizar los primeros N conduits (por ID). "
             "Útil para piloto sobre los primeros creados.",
    )
    parser.add_argument(
        "--tolerancia-mm",
        type=float,
        default=100.0,
        help="Distancia máxima (mm) entre extremos para agrupar en un punto de unión.",
    )
    parser.add_argument(
        "--celda-mm",
        type=float,
        default=100.0,
        help="Tamaño de celda (mm) para indexación espacial.",
    )
    args = parser.parse_args(argv)

    raiz = raiz_proyecto()
    entrada = args.input if os.path.isabs(args.input) else os.path.join(raiz, args.input)
    salida = args.output if os.path.isabs(args.output) else os.path.join(raiz, args.output)

    if not os.path.exists(entrada):
        print("ERROR: no existe el archivo de entrada: {}".format(entrada))
        return 2

    datos = cargar_json(entrada)
    if datos is None:
        print("ERROR: no se pudo leer {}".format(entrada))
        return 2

    conduits = datos.get("conduits", [])
    if not conduits:
        print("ERROR: no hay conduits en el archivo de entrada.")
        return 2

    print("=" * 60)
    print("RE7_ANALIZAR_UNIONES_v01 - Detección de uniones/cajas de empate")
    print("ejecutado_utc={}".format(
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)
    print("Conduits cargados: {}".format(len(conduits)))
    print("Primeros N: {}".format(args.primeros if args.primeros else "todos"))
    print("Tolerancia: {} mm".format(args.tolerancia_mm))
    print("Celda espacial: {} mm".format(args.celda_mm))
    print("")

    reporte = analizar_uniones(
        conduits,
        tolerancia_mm=args.tolerancia_mm,
        primeros=args.primeros,
        celda_mm=args.celda_mm,
    )

    r = reporte["resumen"]
    print("Puntos de unión detectados: {}".format(r["puntos_union_detectados"]))
    print("Conduits con al menos una unión: {}".format(r["conduits_con_union"]))
    print("")
    print("Por tipo de accesorio:")
    for tipo, cnt in sorted(r["por_tipo_accesorio"].items()):
        print("  {:<40} {:>4}".format(tipo, cnt))
    print("")

    # Mostrar los primeros 25 puntos para revisión rápida
    print("Primeros 25 puntos de unión:")
    for p in reporte["puntos_union"][:25]:
        print("  ({:>9.1f}, {:>9.1f}, {:>8.1f})  conduits={:<2}  tipo={:<40}  ids={}".format(
            p["punto_mm"][0], p["punto_mm"][1], p["punto_mm"][2],
            p["num_conduits"],
            p["tipo_accesorio_recomendado"],
            ",".join(str(cid) for cid in p["conduit_ids"])))
    if len(reporte["puntos_union"]) > 25:
        print("  ... y {} más".format(len(reporte["puntos_union"]) - 25))

    guardar_json(salida, reporte)
    print("")
    print("Reporte guardado en: {}".format(salida))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
