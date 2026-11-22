# -*- coding: utf-8 -*-
"""
RE7_ANALIZAR_UNIONES_v02.py — Analizador de topología de conduits con ángulos y altura.

Mejoras vs v01:
  - Calcula ángulo entre conductos en cada punto de unión (para discriminar
    tipo de accesorio por disposición angular, no solo por conteo).
  - Usa altura real (Z) de los conductos en lugar de promedio simple.
  - Clasifica accesorios considerando ángulos:
      * 2 conduits rectos (ángulo ~180°)     → Conduit Coupling
      * 2 conduits en ángulo                  → Conduit Elbow
      * 3 conduits                            → Conduit Junction Box - Tee
      * 4 conduits en cruz (ángulos ~90°)     → Conduit Junction Box - Cross
      * 4 conduits en T asimétrica            → Conduit Junction Box - Tee (o hexagonal)
      * 4 conduits otros                      → M_Caja de conexiones hexagonal
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


def angulo_entre_vectores(v1: Tuple[float, float, float],
                          v2: Tuple[float, float, float]) -> float:
    """Devuelve el ángulo en grados entre dos vectores (0-180)."""
    dp = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
    n1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
    n2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cos = max(-1.0, min(1.0, dp / (n1 * n2)))
    return math.degrees(math.acos(cos))


def vector_desde_conducto_hacia_conexion(c: Dict[str, Any],
                                         tipo_extremo: str,
                                         punto_conexion: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Vector desde el punto de conexión hacia el otro extremo del conducto."""
    a = tuple(float(v) for v in c["a_mm"])
    b = tuple(float(v) for v in c["b_mm"])
    if tipo_extremo == "A":
        # Conexión en A, el otro extremo es B
        v = (b[0] - punto_conexion[0], b[1] - punto_conexion[1], b[2] - punto_conexion[2])
    else:
        # Conexión en B, el otro extremo es A
        v = (a[0] - punto_conexion[0], a[1] - punto_conexion[1], a[2] - punto_conexion[2])
    norm = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if norm > 0:
        v = (v[0]/norm, v[1]/norm, v[2]/norm)
    return v


def clasificar_tipo_accesorio(num_conduits: int,
                              es_cambio_direccion: bool = False,
                              angulos: List[float] = None) -> str:
    """Clasifica el tipo de accesorio considerando ángulos entre conduits."""
    angulos = angulos or []

    if num_conduits >= 4:
        # Si hay 4 conduits con ángulos ~90° entre pares opuestos → Cross
        # Si son 4 pero no forman cruz clara → hexagonal/caja genérica
        if len(angulos) >= 2:
            angulos_sorted = sorted(angulos)
            # En una cruz, hay 2 pares de ángulos opuestos (90° y 270°→90°)
            if (abs(angulos_sorted[0] - 90) < 20 and
                    abs(angulos_sorted[-1] - 90) < 20):
                return "Conduit Junction Box - Cross"
        return "M_Caja de conexiones hexagonal"

    if num_conduits == 3:
        return "Conduit Junction Box - Tee"

    if num_conduits == 2:
        if es_cambio_direccion:
            return "Conduit Elbow"
        return "Conduit Coupling"

    return "Sin accesorio"


def analizar_uniones(conduits: List[Dict[str, Any]],
                     tolerancia_mm: float = 100.0,
                     primeros: int = 0,
                     celda_mm: float = 100.0) -> Dict[str, Any]:
    conduits_ordenados = sorted(conduits, key=lambda c: c["conduit_id"])
    if primeros and primeros > 0:
        conduits_ordenados = conduits_ordenados[:primeros]

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

    celdas: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for i, (cid, tipo, punto, _) in enumerate(extremos):
        clave_celda = (int(punto[0] // celda_mm),
                       int(punto[1] // celda_mm),
                       int(punto[2] // celda_mm))
        celdas[clave_celda].append(i)

    offsets = [(dx, dy, dz) for dx in (-1, 0, 1)
               for dy in (-1, 0, 1) for dz in (-1, 0, 1)]

    for clave_celda, indices in celdas.items():
        candidatos: Set[int] = set()
        for dx, dy, dz in offsets:
            vecina = (clave_celda[0] + dx, clave_celda[1] + dy, clave_celda[2] + dz)
            candidatos.update(celdas.get(vecina, []))

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
                    continue
                if distancia_puntos(p_i, p_j) <= tolerancia_mm:
                    _union(parent, rank, i, j)

    componentes: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        raiz = _find(parent, i)
        componentes[raiz].append(i)

    puntos_union: List[Dict[str, Any]] = []
    for miembros_idx in componentes.values():
        ids_conduits = sorted(set(extremos[i][0] for i in miembros_idx))
        if len(ids_conduits) < 2:
            continue

        # Punto central: usa Z de los conductos (altura real), no promedio simple
        puntos_miembros = [extremos[i][2] for i in miembros_idx]
        pc = punto_medio(puntos_miembros)

        # Altura real: usar la Z mediana de los conductos involucrados
        z_real = sorted([p[2] for p in puntos_miembros])[len(puntos_miembros)//2]
        pc = (pc[0], pc[1], z_real)

        max_desvio = max(distancia_puntos(p, pc) for p in puntos_miembros)

        # Ángulos entre conductos (solo para 2 conduits)
        es_cambio_direccion = False
        angulos = []
        if len(ids_conduits) == 2:
            vectores = []
            for i in miembros_idx:
                cid = extremos[i][0]
                tipo = extremos[i][1]
                punto = extremos[i][2]
                c = next((x for x in conduits_ordenados if x["conduit_id"] == cid), None)
                if c is None:
                    continue
                v = vector_desde_conducto_hacia_conexion(c, tipo, punto)
                vectores.append(v)

            if len(vectores) == 2:
                dp = (vectores[0][0] * vectores[1][0] +
                      vectores[0][1] * vectores[1][1] +
                      vectores[0][2] * vectores[1][2])
                cos = max(-1.0, min(1.0, dp))
                angulo = math.degrees(math.acos(cos))
                angulos.append(angulo)
                # dp ~ -1 (ángulo ~180°): recto → coupling
                # dp ~ 0 (ángulo ~90°): codo
                es_cambio_direccion = angulo < 160.0

        # Para 3 o 4 conduits, calcular ángulos entre pares
        if len(ids_conduits) >= 3:
            vectores = []
            for i in miembros_idx:
                cid = extremos[i][0]
                tipo = extremos[i][1]
                punto = extremos[i][2]
                c = next((x for x in conduits_ordenados if x["conduit_id"] == cid), None)
                if c is None:
                    continue
                v = vector_desde_conducto_hacia_conexion(c, tipo, punto)
                vectores.append(v)

            for vi in range(len(vectores)):
                for vj in range(vi + 1, len(vectores)):
                    a = angulo_entre_vectores(vectores[vi], vectores[vj])
                    angulos.append(a)

        tipo_accesorio = clasificar_tipo_accesorio(
            len(ids_conduits), es_cambio_direccion, angulos)

        puntos_union.append({
            "punto_mm": [round(pc[0], 2), round(pc[1], 2), round(pc[2], 2)],
            "conduit_ids": ids_conduits,
            "num_conduits": len(ids_conduits),
            "tipo_accesorio_recomendado": tipo_accesorio,
            "cambio_direccion": es_cambio_direccion,
            "angulos_grados": [round(a, 1) for a in angulos],
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

    puntos_union.sort(key=lambda u: (u["punto_mm"][0],
                                      u["punto_mm"][1],
                                      u["punto_mm"][2]))

    por_tipo: Dict[str, int] = defaultdict(int)
    for p in puntos_union:
        por_tipo[p["tipo_accesorio_recomendado"]] += 1

    reporte = {
        "version": "v02",
        "script": "RE7_ANALIZAR_UNIONES_v02",
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
        description="Detecta puntos de unión/caja de empate entre conduits (con ángulos y altura real)."
    )
    parser.add_argument(
        "--input",
        default="data/f7_conduits_desde_revit_v01.json",
        help="JSON de conduits desde Revit",
    )
    parser.add_argument(
        "--output",
        default="data/f7_uniones_detectadas_v02.json",
        help="JSON de reporte de uniones detectadas",
    )
    parser.add_argument("--primeros", type=int, default=0,
                        help="Solo analizar los primeros N conduits (por ID).")
    parser.add_argument("--tolerancia-mm", type=float, default=100.0)
    parser.add_argument("--celda-mm", type=float, default=100.0)
    args = parser.parse_args(argv)

    raiz = raiz_proyecto()
    entrada = args.input if os.path.isabs(args.input) else os.path.join(raiz, args.input)
    salida = args.output if os.path.isabs(args.output) else os.path.join(raiz, args.output)

    if not os.path.exists(entrada):
        print("ERROR: no existe {}".format(entrada))
        return 2

    datos = cargar_json(entrada)
    conduits = datos.get("conduits", [])
    if not conduits:
        print("ERROR: no hay conduits.")
        return 2

    reporte = analizar_uniones(conduits,
                               tolerancia_mm=args.tolerancia_mm,
                               primeros=args.primeros,
                               celda_mm=args.celda_mm)

    r = reporte["resumen"]
    print("Puntos de unión: {}".format(r["puntos_union_detectados"]))
    print("Conduits con unión: {}".format(r["conduits_con_union"]))
    print("")
    print("Por tipo:")
    for tipo, cnt in sorted(r["por_tipo_accesorio"].items()):
        print("  {:<45} {:>4}".format(tipo, cnt))
    print("")
    print("Primeros 15 puntos:")
    for p in reporte["puntos_union"][:15]:
        print("  ({:>9.1f}, {:>9.1f}, {:>8.1f})  n={:<2}  tipo={:<45}  ids={}  ang={}".format(
            p["punto_mm"][0], p["punto_mm"][1], p["punto_mm"][2],
            p["num_conduits"],
            p["tipo_accesorio_recomendado"],
            ",".join(str(cid) for cid in p["conduit_ids"]),
            p.get("angulos_grados", [])))

    guardar_json(salida, reporte)
    print("\nGuardado en: {}".format(salida))
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
