# -*- coding: utf-8 -*-
"""Modelos de datos del pipeline de ruteo de conduit.

Unidades: metros para longitud/coordenadas, milimetros para diametros nominales,
pulgadas para la designacion comercial del conduit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Punto2D = tuple[float, float]
Punto3D = tuple[float, float, float]


@dataclass(frozen=True)
class Dispositivo:
    """Aparato electrico insertado en el DXF (INSERT con o sin atributos)."""

    handle: str
    nombre: str
    capa: str
    x: float
    y: float
    atributos: dict[str, str] = field(default_factory=dict)

    @property
    def punto(self) -> Punto2D:
        return (self.x, self.y)


@dataclass(frozen=True)
class Marcador:
    """Simbolo de cableado que indica cuantos conductores lleva la tuberia."""

    handle: str
    nombre: str
    capa: str
    x: float
    y: float
    cables: int
    fuente_cables: str = "nombre_bloque"

    @property
    def punto(self) -> Punto2D:
        return (self.x, self.y)


@dataclass(frozen=True)
class Polilinea:
    """Tramo de tuberia dibujado en 2D."""

    handle: str
    capa: str
    puntos: tuple[Punto2D, ...]

    @property
    def inicio(self) -> Punto2D:
        return self.puntos[0]

    @property
    def fin(self) -> Punto2D:
        return self.puntos[-1]

    def largo(self) -> float:
        total = 0.0
        for i in range(len(self.puntos) - 1):
            ax, ay = self.puntos[i]
            bx, by = self.puntos[i + 1]
            total += ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        return total


@dataclass
class ExtremoTramo:
    """A que se conecta un extremo del tramo."""

    tipo: str                       # "dispositivo" | "libre" | "empalme"
    x: float
    y: float
    distancia_m: float
    handle: str = ""
    nombre: str = ""
    capa: str = ""
    servicio: str | None = None
    altura_m: float | None = None


@dataclass
class Tramo:
    """Un conduit a crear en Revit."""

    id: str
    handle_dxf: str
    capa: str
    servicio: str
    cables: int
    cables_origen: str               # "marcador" | "heredado" | "default"
    material: str
    calibre: str
    diametro_pulgadas: str
    diametro_mm: float
    largo_m: float
    cota_m: float
    diametro_origen: str = "cables"   # "cables" | "fijo_servicio"
    puntos_2d: list[Punto2D] = field(default_factory=list)
    puntos_3d: list[Punto3D] = field(default_factory=list)
    extremos: list[ExtremoTramo] = field(default_factory=list)
    marcadores: list[str] = field(default_factory=list)
    red: str | None = None        # circuito/red a la que pertenece el tramo
    avisos: list[str] = field(default_factory=list)

    def a_dict(self, elevacion_nivel_m: float = 0.0) -> dict[str, Any]:
        return {
            "id": self.id,
            "handle_dxf": self.handle_dxf,
            "capa": self.capa,
            "servicio": self.servicio,
            "cables": self.cables,
            "cables_origen": self.cables_origen,
            "material": self.material,
            "calibre": self.calibre,
            "diametro_pulgadas": self.diametro_pulgadas,
            "diametro_mm": self.diametro_mm,
            "diametro_origen": self.diametro_origen,
            "largo_m": round(self.largo_m, 3),
            "cota_m": round(self.cota_m, 3),
            "z_absoluta_m": round(elevacion_nivel_m + self.cota_m, 4),
            "puntos_3d": [[round(v, 4) for v in p] for p in self.puntos_3d],
            "extremos": [
                {
                    "tipo": e.tipo,
                    "handle": e.handle,
                    "nombre": e.nombre,
                    "capa": e.capa,
                    "servicio": e.servicio,
                    "altura_m": e.altura_m,
                    "distancia_m": round(e.distancia_m, 3),
                    "x": round(e.x, 3),
                    "y": round(e.y, 3),
                }
                for e in self.extremos
            ],
            "marcadores": self.marcadores,
            "red": self.red,
            "avisos": self.avisos,
        }


@dataclass
class Caja:
    """Caja de conexion (octogonal/hexagonal) previa al aparato.

    En el plano, el tramo de tuberia termina en la caja y desde ahi baja una
    conexion corta al aparato (luminaria, ventilador).
    """

    id: str
    tramo_id: str
    x: float
    y: float
    cota_m: float
    servicio: str
    aparato_handle: str = ""
    aparato_nombre: str = ""
    aparato_capa: str = ""
    distancia_m: float = 0.0
    altura_aparato_m: float = 0.0

    def a_dict(self, elevacion_nivel_m: float = 0.0) -> dict[str, Any]:
        return {
            "id": self.id,
            "tramo_id": self.tramo_id,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z_absoluta_m": round(elevacion_nivel_m + self.cota_m, 4),
            "cota_m": round(self.cota_m, 3),
            "servicio": self.servicio,
            "aparato_handle": self.aparato_handle,
            "aparato_nombre": self.aparato_nombre,
            "aparato_capa": self.aparato_capa,
            "altura_aparato_m": round(self.altura_aparato_m, 3),
            "distancia_m": round(self.distancia_m, 3),
        }


@dataclass
class Cruce:
    """Cruce en planta entre tramos de distinto servicio."""

    tramo_a: str
    tramo_b: str
    servicio_a: str
    servicio_b: str
    x: float
    y: float
    cota_a: float
    cota_b: float

    @property
    def separacion_m(self) -> float:
        return abs(self.cota_a - self.cota_b)

    def a_dict(self) -> dict[str, Any]:
        return {
            "tramo_a": self.tramo_a,
            "tramo_b": self.tramo_b,
            "servicio_a": self.servicio_a,
            "servicio_b": self.servicio_b,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "cota_a": round(self.cota_a, 3),
            "cota_b": round(self.cota_b, 3),
            "separacion_m": round(self.separacion_m, 3),
        }


@dataclass
class ResultadoRuteo:
    """Salida completa del pipeline para un DXF y una zona."""

    dxf: str
    zona: str
    material: str
    calibre: str
    nivel: str
    elevacion_nivel_m: float
    tramos: list[Tramo] = field(default_factory=list)
    cajas: list[Caja] = field(default_factory=list)
    cruces: list[Cruce] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    estadisticas: dict[str, Any] = field(default_factory=dict)
    ancla: dict[str, Any] = field(default_factory=dict)

    def resumen(self) -> dict[str, Any]:
        por_servicio: dict[str, int] = {}
        por_diametro: dict[str, int] = {}
        largo_por_servicio: dict[str, float] = {}
        sin_marcador = 0
        avisos_totales = 0
        for t in self.tramos:
            por_servicio[t.servicio] = por_servicio.get(t.servicio, 0) + 1
            por_diametro[t.diametro_pulgadas] = por_diametro.get(t.diametro_pulgadas, 0) + 1
            largo_por_servicio[t.servicio] = largo_por_servicio.get(t.servicio, 0.0) + t.largo_m
            if t.cables_origen != "marcador":
                sin_marcador += 1
            avisos_totales += len(t.avisos)
        return {
            "tramos": len(self.tramos),
            "tramos_con_marcador": len(self.tramos) - sin_marcador,
            "tramos_sin_marcador": sin_marcador,
            "tramos_en_revision": len(self.tramos_en_revision()),
            "cajas_conexion": len(self.cajas),
            "cruces_planta": len(self.cruces),
            "cruces_a_la_misma_cota": len([c for c in self.cruces if c.separacion_m < 0.02]),
            "longitud_total_m": round(sum(t.largo_m for t in self.tramos), 2),
            "por_servicio": por_servicio,
            "largo_por_servicio_m": {k: round(v, 2) for k, v in largo_por_servicio.items()},
            "por_diametro": por_diametro,
            "avisos": avisos_totales,
        }

    def tramos_en_revision(self) -> list[Tramo]:
        """Tramos con al menos un extremo sin dispositivo ni caja."""
        return [t for t in self.tramos if any(e.tipo == "libre" for e in t.extremos)]

    def a_dict(self) -> dict[str, Any]:
        revision = self.tramos_en_revision()
        return {
            "version": "v01",
            "dxf": self.dxf,
            "zona": self.zona,
            "material": self.material,
            "calibre": self.calibre,
            "nivel": self.nivel,
            "elevacion_nivel_m": self.elevacion_nivel_m,
            "resumen": self.resumen(),
            "avisos_globales": self.avisos,
            "estadisticas_extraccion": self.estadisticas,
            "ancla": self.ancla,
            "revision": {
                "total": len(revision),
                "tramos": [
                    {
                        "id": t.id,
                        "handle_dxf": t.handle_dxf,
                        "capa": t.capa,
                        "servicio": t.servicio,
                        "diametro_pulgadas": t.diametro_pulgadas,
                        "largo_m": round(t.largo_m, 3),
                        "puntos_2d": [[round(x, 3), round(y, 3)] for x, y in t.puntos_2d],
                        "extremos_libres": [
                            {"x": round(e.x, 3), "y": round(e.y, 3),
                             "distancia_m": round(e.distancia_m, 3)}
                            for e in t.extremos if e.tipo == "libre"
                        ],
                    }
                    for t in revision
                ],
            },
            "cajas": [c.a_dict(self.elevacion_nivel_m) for c in self.cajas],
            "cruces": [c.a_dict() for c in self.cruces],
            "tramos": [t.a_dict(self.elevacion_nivel_m) for t in self.tramos],
        }
