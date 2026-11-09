# -*- coding: utf-8 -*-
"""Lectura del DXF electrico: dispositivos, marcadores de cables y polilineas de tuberia."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from modelos import Dispositivo, Marcador, Polilinea

_PATRON_CIRCUITO = re.compile(r'^[A-Z]{1,3}[- ]?\d{1,3}$')

# Nomenclatura de los simbolos de cableado: una letra por conductor, con un
# contador opcional delante. Si no hay contador, cuenta 1.
#   F = fase, N = neutro, T = tierra, R = retorno.
#   1FTN     -> 1F + T + N        = 3
#   1FTNR    -> 1F + T + N + R    = 4
#   2FT2N    -> 2F + T + 2N       = 5
#   2F2N1T1R -> 2F + 2N + 1T + 1R = 6
_LETRAS_CABLE = {"F", "N", "T", "R"}
_PATRON_MARCADOR = re.compile(r"^\d[0-9FNTR]*$")


def cables_desde_nombre(nombre: str) -> int | None:
    """Deriva la cantidad de cables del nombre del bloque de marcador.

    '1FTN'      -> 3   (1 fase + 1 tierra + 1 neutro)
    '1FTNR'     -> 4
    '2FT2N'     -> 5   (2 fases + 1 tierra + 2 neutros)
    '2F2N1T1R'  -> 6
    Devuelve None si el nombre no sigue la nomenclatura.
    """
    token = (nombre or "").strip().upper()
    if not token or not _PATRON_MARCADOR.match(token):
        return None
    if not any(c in _LETRAS_CABLE for c in token):
        return None
    total = 0
    i = 0
    while i < len(token):
        j = i
        while j < len(token) and token[j].isdigit():
            j += 1
        n = int(token[i:j]) if j > i else 1
        if j >= len(token) or token[j] not in _LETRAS_CABLE:
            return None
        total += n
        i = j + 1
    return total or None


@dataclass
class ContenidoDXF:
    """Todo lo que el ruteador necesita de un plano."""

    ruta: str
    dispositivos: list[Dispositivo] = field(default_factory=list)
    marcadores: list[Marcador] = field(default_factory=list)
    polilineas: list[Polilinea] = field(default_factory=list)
    textos_circuito: list[dict[str, Any]] = field(default_factory=list)
    capas: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def _capa_es_electrica(capa: str) -> bool:
    return capa.startswith(("ELEC-", "Elec-", "E-Lite", "E-Comm", "TDT"))


def leer_dxf(
    ruta: str,
    capas_tuberia: list[str],
    capas_dispositivo: list[str],
    leer_atributos: bool = True,
) -> ContenidoDXF:
    """Lee el DXF y separa dispositivos, marcadores y polilineas de tuberia."""
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Falta ezdxf. Instalar con: pip install ezdxf>=1.4"
        ) from exc

    if not os.path.exists(ruta):
        raise FileNotFoundError("No existe el DXF: %s" % ruta)

    doc = ezdxf.readfile(ruta)
    msp = doc.modelspace()
    contenido = ContenidoDXF(ruta=ruta)
    capas_tuberia_set = set(capas_tuberia)
    capas_dispositivo_set = set(capas_dispositivo)

    for entidad in msp:
        tipo = entidad.dxftype()
        capa = entidad.dxf.layer
        contenido.capas[capa] = contenido.capas.get(capa, 0) + 1

        if tipo == "LWPOLYLINE":
            if capa not in capas_tuberia_set:
                continue
            puntos = tuple((float(p[0]), float(p[1])) for p in entidad.get_points())
            if len(puntos) < 2:
                contenido.avisos.append(
                    "Polilinea %s en '%s' descartada: %d vertices"
                    % (entidad.dxf.handle, capa, len(puntos))
                )
                continue
            contenido.polilineas.append(
                Polilinea(handle=entidad.dxf.handle, capa=capa, puntos=puntos)
            )
            continue

        if tipo in ("ARC", "CIRCLE", "LINE", "POLYLINE") and capa in capas_tuberia_set:
            contenido.avisos.append(
                "Entidad %s %s en capa de tuberia '%s' no convertida a tramo "
                "(revisar si es un tramo curvo o un simbolo)"
                % (tipo, entidad.dxf.handle, capa)
            )
            continue

        if tipo == "TEXT" and capa.startswith(("ELEC-", "Elec-", "E-")) and "Iden" in capa:
            texto = (entidad.dxf.text or "").strip()
            # Solo textos que parezcan codigo de circuito (p.ej. TF-01, TF-03), no medidas ni 'VACIO'.
            if texto and _PATRON_CIRCUITO.match(texto.upper()):
                p = entidad.dxf.insert
                contenido.textos_circuito.append({
                    "texto": texto,
                    "x": float(p.x),
                    "y": float(p.y),
                    "handle": entidad.dxf.handle,
                })
            continue

        if tipo != "INSERT":
            continue

        nombre = entidad.dxf.name or ""
        x = float(entidad.dxf.insert.x)
        y = float(entidad.dxf.insert.y)

        cables = cables_desde_nombre(nombre)
        if cables is not None:
            contenido.marcadores.append(
                Marcador(handle=entidad.dxf.handle, nombre=nombre, capa=capa, x=x, y=y, cables=cables)
            )
            continue

        if capa not in capas_dispositivo_set and not _capa_es_electrica(capa):
            continue

        atributos: dict[str, str] = {}
        if leer_atributos:
            try:
                if getattr(entidad, "has_attrib", False):
                    for attrib in entidad.attribs:
                        atributos[attrib.dxf.tag] = (attrib.dxf.text or "").strip()
            except Exception:  # DXF mal formado no debe tumbar el pipeline
                contenido.avisos.append(
                    "Atributos ilegibles en INSERT %s (%s)" % (entidad.dxf.handle, nombre)
                )

        contenido.dispositivos.append(
            Dispositivo(handle=entidad.dxf.handle, nombre=nombre, capa=capa,
                        x=x, y=y, atributos=atributos)
        )

    return contenido


def resumen_contenido(contenido: ContenidoDXF) -> dict:
    por_capa_tuberia: dict[str, int] = {}
    largo_por_capa: dict[str, float] = {}
    for pl in contenido.polilineas:
        por_capa_tuberia[pl.capa] = por_capa_tuberia.get(pl.capa, 0) + 1
        largo_por_capa[pl.capa] = round(largo_por_capa.get(pl.capa, 0.0) + pl.largo(), 2)
    return {
        "polilineas": len(contenido.polilineas),
        "polilineas_por_capa": por_capa_tuberia,
        "largo_por_capa_m": largo_por_capa,
        "dispositivos": len(contenido.dispositivos),
        "marcadores": len(contenido.marcadores),
        "cables_distintos": sorted({m.cables for m in contenido.marcadores}),
        "avisos": len(contenido.avisos),
    }
