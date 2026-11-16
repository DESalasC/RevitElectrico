# -*- coding: utf-8 -*-
"""Resuelve el cielorraso de un aparato y su cota de montaje.

Motivo: el resolvedor anterior (`obtener_host_techo` en CREAR_DISPOSITIVOS_E06_FINAL_v20.py)
elegia el techo mas cercano **en XY** dentro de 10 m. En CENTRAL-V01 hay 523 techos, unos 25
por nivel, y **21 apilados sobre la misma vertical**: con esa regla un aparato de Piso 5 puede
colgar del techo de Piso 3.

Orden de seleccion que se aplica aqui, en este orden estricto:

1. Solo techos del **nivel del aparato** (si se conoce el nivel).
2. De esos, los que **contienen el punto en su bbox**.
3. Si ninguno contiene el punto, el **mas cercano** al centro del bbox, pero solo si esta dentro
   de un radio maximo. Si no hay nada, devuelve None: no inventa un techo.

La altura se deriva del techo, no del nivel:

* Aparato normal: cara **inferior** del techo menos un offset (0 = a ras).
* `ELEC-NET-PAU` (punto de consolidacion): **por encima del cielorraso**, cara superior mas un
  margen. Es una condicion del operador, no una preferencia.

Sin dependencias y sin sintaxis que IronPython 2.7 no entienda: se importa igual desde los
tests (Python 3) y desde Revit.
"""

from __future__ import division

# Radio maximo para aceptar un techo que no contiene el punto, en metros.
RADIO_MAXIMO_FALLBACK_M = 2.0

# Separacion por defecto entre la cara inferior del techo y el aparato (0 = a ras).
OFFSET_BAJO_TECHO_M = 0.0

# Margen del punto de consolidacion sobre la cara superior del cielorraso.
MARGEN_SOBRE_CIELORRASO_M = 0.08

# Codigos que deben quedar por encima del cielorraso, siempre.
SOBRE_CIELORRASO = ("ELEC-NET-PAU",)


def _contiene(bbox, x, y):
    """bbox = (xmin, ymin, xmax, ymax) en metros."""
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _distancia_al_centro(bbox, x, y):
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5


def elegir_techo(candidatos, x, y, nivel_id=None, radio_maximo_m=RADIO_MAXIMO_FALLBACK_M):
    """Devuelve el techo que corresponde al punto, o None.

    ``candidatos``: lista de diccionarios con las claves ``id``, ``nivel_id``,
    ``bbox`` (xmin, ymin, xmax, ymax en metros) y opcionalmente ``z_inferior_m`` y
    ``z_superior_m``.

    El resultado incluye ``motivo`` para que la decision sea auditable: no basta con acertar,
    hay que poder explicar por que se eligio ese techo.
    """
    if not candidatos:
        return None

    mismo_nivel = [c for c in candidatos if nivel_id is None or c.get("nivel_id") == nivel_id]

    contienen = [c for c in mismo_nivel if _contiene(c["bbox"], x, y)]
    if contienen:
        elegido = min(contienen, key=lambda c: _distancia_al_centro(c["bbox"], x, y))
        resultado = dict(elegido)
        resultado["motivo"] = "contiene_el_punto"
        resultado["candidatos_nivel"] = len(mismo_nivel)
        resultado["candidatos_que_contienen"] = len(contienen)
        return resultado

    con_distancia = [(_distancia_al_centro(c["bbox"], x, y), c) for c in mismo_nivel]
    con_distancia.sort(key=lambda par: par[0])
    for distancia, candidato in con_distancia:
        if distancia <= radio_maximo_m:
            resultado = dict(candidato)
            resultado["motivo"] = "mas_cercano_del_nivel"
            resultado["distancia_m"] = round(distancia, 4)
            resultado["candidatos_nivel"] = len(mismo_nivel)
            resultado["candidatos_que_contienen"] = 0
            return resultado

    return None


def altura_sobre_techo(techo, codigo=None, offset_m=OFFSET_BAJO_TECHO_M,
                       margen_sobre_cielorraso_m=MARGEN_SOBRE_CIELORRASO_M):
    """Cota absoluta (m) del aparato, referida al techo.

    Para ``ELEC-NET-PAU`` devuelve la cara superior mas el margen: el punto de consolidacion
    nunca queda por debajo del cielorraso. Para el resto, la cara inferior menos el offset.
    """
    if techo is None:
        return None

    superior = techo.get("z_superior_m")
    inferior = techo.get("z_inferior_m")

    if codigo in SOBRE_CIELORRASO:
        if superior is None:
            return None
        return round(superior + margen_sobre_cielorraso_m, 4)

    if inferior is None:
        return None
    return round(inferior - offset_m, 4)


def cumple_estar_sobre_cielorraso(techo, codigo, z_absoluta_m):
    """Verifica la condicion del operador para los codigos que van sobre el cielorraso."""
    if codigo not in SOBRE_CIELORRASO:
        return True
    if techo is None or z_absoluta_m is None or techo.get("z_superior_m") is None:
        return False
    return z_absoluta_m > techo["z_superior_m"]
