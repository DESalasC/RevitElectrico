# -*- coding: utf-8 -*-
"""Dimensionamiento del conduit segun cantidad de cables, material y calibre."""
from __future__ import annotations

from dataclasses import dataclass

from config import ConfigRuteo


@dataclass(frozen=True)
class Dimension:
    cables: int
    material: str
    calibre: str
    pulgadas: str
    mm: float
    capacidad: int

    @property
    def holgura(self) -> int:
        return self.capacidad - self.cables


def dimensionar(cfg: ConfigRuteo, cables: int) -> Dimension:
    """Diametro minimo de conduit que aloja `cables` conductores del calibre de la zona."""
    if cables < 1:
        raise ValueError("La cantidad de cables debe ser >= 1 (recibido %r)" % cables)
    pulgadas, mm, capacidad = cfg.diametro_para(cables)
    return Dimension(
        cables=cables,
        material=cfg.material,
        calibre=cfg.calibre,
        pulgadas=pulgadas,
        mm=mm,
        capacidad=capacidad,
    )


def dimensionar_servicio(cfg: ConfigRuteo, servicio: str, cables: int) -> tuple[Dimension, str, str]:
    """Dimensiona aplicando la excepcion de diametro fijo por servicio.

    Devuelve (dimension, origen, motivo). origen es "fijo_servicio" o "cables".
    COMUNICACIONES se fija en 3/4" porque los cables de voz/datos no son 12 AWG
    y no vienen marcados en el DXF.
    """
    fijo = cfg.diametro_fijo(servicio)
    if fijo is not None:
        pulgadas, mm, motivo = fijo
        cap = cfg.capacidad(cfg.material, cfg.calibre)
        return (
            Dimension(cables=cables, material=cfg.material, calibre=cfg.calibre,
                      pulgadas=pulgadas, mm=mm, capacidad=cap.capacidades.get(pulgadas, 0)),
            "fijo_servicio",
            motivo,
        )
    return dimensionar(cfg, cables), "cables", ""
