# -*- coding: utf-8 -*-
"""Comprobacion del lado de un aparato respecto a su muro anfitrion (RE-P-060).

ALCANCE REAL (corregido 2026-11-17): este modulo mide si la normal del muro
anfitrion apunta hacia el muro o hacia el cuarto. **No determina el frente del
simbolo.** Para las 10 tomas de datos de E 06, ``FacingOrientation`` y
``rotationDeg`` valen 120/240 grados mientras el eje real del simbolo es 90/270
(el que trae el DXF). Verificar orientacion con estos atributos da falsos
positivos; la verificacion correcta es el **eje del bounding box** contra la
rotacion del bloque DXF, con tolerancia de ~5 grados.

Regla derivada de E 06 (sigue siendo valida como comprobacion de lado):

* En E 06 **todos** los aparatos face-based tienen la normal del muro apuntando
  hacia adentro del muro: ``dot(FacingOrientation, punto - punto_muro) < 0``.
* Los interruptores NO son face-based: su ``dot`` es 0 porque su eje no es
  perpendicular al muro. Se clasifican aparte y no se corrigen con esta regla.

La correccion de un aparato volteado es cambiar de cara del muro (o voltear la
instancia), NO sumar grados a la rotacion.

Uso desde el colocador:

    from RE_ORACULO_ORIENTACION_v01 import clasificar, resumir
    estado = clasificar(dot)
    if estado == "VOLTEADO": ...
"""

from __future__ import annotations

from typing import Any, Iterable

UMBRAL_PARALELO = 0.30
UMBRAL_VOLTEO = 0.30


def clasificar(dot: float, umbral_paralelo: float = UMBRAL_PARALELO) -> str:
    """Clasifica un aparato segun ``dot(FacingOrientation, punto - punto_muro)``.

    Devuelve ``"PARALELO"`` si el eje no es perpendicular al muro (no face-based),
    ``"OK"`` si la normal apunta hacia el muro (convencion de E 06) y
    ``"VOLTEADO"`` si apunta hacia el cuarto.
    """
    if abs(dot) < umbral_paralelo:
        return "PARALELO"
    return "OK" if dot < 0 else "VOLTEADO"


def resumir(registros: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Resume una lista de registros con clave ``dot``.

    Cada registro debe traer al menos ``element_id``, ``familia``, ``tipo`` y ``dot``.
    Devuelve conteos por estado y la lista de volteados con su identificacion.
    """
    conteo = {"OK": 0, "VOLTEADO": 0, "PARALELO": 0}
    volteados: list[dict[str, Any]] = []
    detalle: list[dict[str, Any]] = []
    for registro in registros:
        estado = clasificar(float(registro["dot"]))
        conteo[estado] += 1
        fila = {
            "element_id": registro.get("element_id"),
            "familia": registro.get("familia"),
            "tipo": registro.get("tipo"),
            "dot": round(float(registro["dot"]), 4),
            "estado": estado,
        }
        detalle.append(fila)
        if estado == "VOLTEADO":
            volteados.append(fila)
    return {
        "total": sum(conteo.values()),
        "conteo": conteo,
        "volteados": volteados,
        "detalle": detalle,
    }
