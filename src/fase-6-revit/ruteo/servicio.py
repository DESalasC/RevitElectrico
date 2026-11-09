# -*- coding: utf-8 -*-
"""Resolucion del servicio (Servicio_Conduit) de cada tramo."""
from __future__ import annotations

from config import ConfigRuteo
from modelos import ExtremoTramo


def resolver_servicio(
    cfg: ConfigRuteo,
    capa_tuberia: str,
    extremos: list[ExtremoTramo],
) -> tuple[str, list[str]]:
    """Determina el servicio de un tramo y devuelve (servicio, avisos).

    Prioridad de criterios:
      1. Servicio de los dispositivos conectados en los extremos (si coinciden).
      2. Servicio de la capa de la tuberia (base del plano).
      3. Si los extremos discrepan entre si, gana el de mayor prioridad
         (COMUNICACIONES > FUERZA > TOMAS > ILUMINACION) y se avisa.
    """
    avisos: list[str] = []
    servicio_capa = cfg.servicio_de_capa_tuberia(capa_tuberia)
    servicios_extremos = [e.servicio for e in extremos if e.tipo == "dispositivo" and e.servicio]

    # Algunas capas mandan sobre los extremos: las comunicaciones no llevan
    # marcador de cables y sus aparatos no siempre caen en el extremo dibujado.
    fijados = cfg.datos.get("servicios_fijados_por_capa") or {}
    if capa_tuberia in fijados:
        servicio_fijo = fijados[capa_tuberia]
        distintos = sorted(set(servicios_extremos) - {servicio_fijo})
        if distintos:
            avisos.append(
                "Servicio fijado por capa '%s' -> %s (extremos: %s)"
                % (capa_tuberia, servicio_fijo, distintos)
            )
        return servicio_fijo, avisos


    candidatos = sorted(set(servicios_extremos))
    if len(candidatos) == 1:
        servicio = candidatos[0]
        if servicio_capa and servicio != servicio_capa:
            avisos.append(
                "Servicio de extremos '%s' difiere de la capa '%s' (%s); se usa el de extremos"
                % (servicio, capa_tuberia, servicio_capa)
            )
        return servicio, avisos

    if len(candidatos) > 1:
        if cfg.datos["reglas_servicio"].get("si_extremos_difieren_gana_prioridad", True):
            servicio = sorted(candidatos, key=cfg.prioridad)[0]
            avisos.append(
                "Extremos con servicios distintos %s; se usa '%s' por prioridad"
                % (candidatos, servicio)
            )
            return servicio, avisos
        candidatos_str = "/".join(candidatos)
        avisos.append("Extremos con servicios distintos sin regla de desempate: %s" % candidatos_str)

    if servicio_capa:
        return servicio_capa, avisos

    avisos.append("Sin servicio resoluble (capa '%s' no mapeada); se asume FUERZA" % capa_tuberia)
    return "FUERZA", avisos
