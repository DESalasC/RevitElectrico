# -*- coding: utf-8 -*-
"""Carga y validacion de la configuracion de ruteo + tablas de capacidad CSV."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from typing import Any


class ConfigError(ValueError):
    """Error de configuracion con mensaje accionable para el operador."""


@dataclass
class Capacidad:
    """Fila de una tabla de capacidad: calibre -> {pulgadas: max cables}."""

    material: str
    calibre: str
    capacidades: dict[str, int]   # {"1/2\"": 11, "3/4\"": 19, ...}

    def diametro_para(self, cables: int) -> tuple[str, int] | None:
        """Devuelve (pulgadas, capacidad) del diametro mas pequeno que soporta `cables`."""
        candidatos = sorted(self.capacidades.items(), key=lambda kv: kv[1])
        for pulgadas, cap in candidatos:
            if cap >= cables:
                return pulgadas, cap
        return None


def _leer_csv_capacidad(ruta: str, material: str) -> dict[str, Capacidad]:
    if not os.path.exists(ruta):
        raise ConfigError("No existe la tabla de capacidad: %s" % ruta)

    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        # Los CSV tienen comillas dentro de los encabezados (1/2"", 3/4"")
        lector = csv.reader(f, quotechar='"', skipinitialspace=True)
        filas = [fila for fila in lector if any(c.strip() for c in fila)]

    if len(filas) < 2:
        raise ConfigError("Tabla de capacidad vacia o mal formada: %s" % ruta)

    # csv.reader ya resolvio las comillas dobles: '1/2""' -> '1/2"'.
    # No volver a quitar comillas aqui o se pierde la pulgada del diametro.
    encabezado = [c.strip() for c in filas[0]]
    if encabezado[0].lower() != "calibre":
        raise ConfigError("La primera columna debe ser 'Calibre' en %s (es '%s')" % (ruta, encabezado[0]))

    diametros = encabezado[1:]
    resultado: dict[str, Capacidad] = {}
    for fila in filas[1:]:
        celdas = [c.strip() for c in fila]
        if not celdas or not celdas[0]:
            continue
        calibre = celdas[0]
        caps: dict[str, int] = {}
        for i, pulgadas in enumerate(diametros):
            if i + 1 >= len(celdas):
                break
            valor = celdas[i + 1]
            if not valor:
                continue
            try:
                caps[pulgadas] = int(float(valor))
            except ValueError:
                raise ConfigError(
                    "Valor no numerico '%s' en %s (calibre %s, columna %s)"
                    % (valor, os.path.basename(ruta), calibre, pulgadas)
                )
        resultado[calibre] = Capacidad(material=material, calibre=calibre, capacidades=caps)
    return resultado


class ConfigRuteo:
    """Configuracion inmutable del pipeline para una corrida."""

    def __init__(self, datos: dict[str, Any], raiz_proyecto: str):
        self.datos = datos
        self.raiz = raiz_proyecto
        self.tablas: dict[str, dict[str, Capacidad]] = {}
        self._validar()
        self._cargar_tablas()

    # --- validacion -------------------------------------------------
    def _validar(self) -> None:
        requeridas = [
            "zona", "zonas_alternativas", "archivos_capacidad", "servicios_permitidos",
            "mapeo_capa_tuberia_a_servicio", "mapeo_capa_dispositivo_a_servicio",
            "altura_por_capa_dispositivo_m", "cota_banda_tuberia_m", "tolerancias",
            "reglas_cables", "reglas_geometria",
        ]
        faltantes = [k for k in requeridas if k not in self.datos]
        if faltantes:
            raise ConfigError("Faltan secciones en la configuracion: %s" % ", ".join(faltantes))

        permitidos = set(self.datos["servicios_permitidos"])
        for capa, servicio in self.datos["mapeo_capa_tuberia_a_servicio"].items():
            if servicio not in permitidos:
                raise ConfigError(
                    "Servicio '%s' de la capa '%s' no esta en servicios_permitidos %s"
                    % (servicio, capa, sorted(permitidos))
                )
        for capa, servicio in self.datos["mapeo_capa_dispositivo_a_servicio"].items():
            if servicio not in permitidos:
                raise ConfigError(
                    "Servicio '%s' de la capa de dispositivo '%s' no esta en servicios_permitidos"
                    % (servicio, capa)
                )

        zona = self.datos["zona"]
        if zona.get("material") not in self.datos["archivos_capacidad"]:
            raise ConfigError(
                "El material de la zona '%s' no tiene tabla de capacidad declarada"
                % zona.get("material")
            )

    def _cargar_tablas(self) -> None:
        for material, ruta_rel in self.datos["archivos_capacidad"].items():
            ruta = ruta_rel if os.path.isabs(ruta_rel) else os.path.join(self.raiz, ruta_rel)
            self.tablas[material] = _leer_csv_capacidad(ruta, material)

    # --- consultas --------------------------------------------------
    @property
    def zona(self) -> str:
        return self.datos["zona"]["nombre"]

    @property
    def material(self) -> str:
        return self.datos["zona"]["material"]

    @property
    def calibre(self) -> str:
        return self.datos["zona"]["calibre"]

    def tolerancia(self, clave: str) -> float:
        return float(self.datos["tolerancias"][clave])

    def servicio_de_capa_tuberia(self, capa: str) -> str | None:
        return self.datos["mapeo_capa_tuberia_a_servicio"].get(capa)

    def servicio_de_capa_dispositivo(self, capa: str) -> str | None:
        return self.datos["mapeo_capa_dispositivo_a_servicio"].get(capa)

    def altura_dispositivo(self, capa: str) -> float:
        altura = self.datos["altura_por_capa_dispositivo_m"].get(capa)
        if altura is None:
            return float(self.datos["altura_default_dispositivo_m"])
        return float(altura)

    def altura_aparato(self, nombre_bloque: str, capa: str) -> float:
        """Altura de montaje: primero por nombre de bloque, luego por capa."""
        por_bloque = self.datos.get("altura_por_bloque_m") or {}
        if nombre_bloque in por_bloque:
            return float(por_bloque[nombre_bloque])
        return self.altura_dispositivo(capa)

    def diametro_fijo(self, servicio: str) -> tuple[str, float, str] | None:
        """(pulgadas, mm, motivo) si el servicio tiene diametro fijado por norma."""
        fijos = self.datos.get("diametro_fijo_por_servicio") or {}
        dato = fijos.get(servicio)
        if not dato:
            return None
        return str(dato["pulgadas"]), float(dato["mm"]), str(dato.get("motivo", ""))

    def cota_banda(self, servicio: str) -> float:
        cota = self.datos["cota_banda_tuberia_m"].get(servicio)
        if cota is None:
            return float(self.datos["cota_banda_default_m"])
        return float(cota)

    def prioridad(self, servicio: str) -> int:
        orden = self.datos.get("prioridad_servicio", [])
        return orden.index(servicio) if servicio in orden else len(orden)

    def capacidad(self, material: str, calibre: str) -> Capacidad:
        tabla = self.tablas.get(material)
        if tabla is None:
            raise ConfigError("No hay tabla de capacidad cargada para el material '%s'" % material)
        cap = tabla.get(calibre)
        if cap is None:
            raise ConfigError(
                "El calibre '%s' no existe en la tabla de %s (disponibles: %s)"
                % (calibre, material, sorted(tabla))
            )
        return cap

    def diametro_para(self, cables: int) -> tuple[str, float, int]:
        """(pulgadas, mm, capacidad) del diametro minimo que soporta `cables`."""
        cap = self.capacidad(self.material, self.calibre)
        encontrado = cap.diametro_para(cables)
        if encontrado is None:
            raise ConfigError(
                "La tabla %s/%s no soporta %d cables (maximo %d en 2\")"
                % (self.material, self.calibre, cables,
                   max(cap.capacidades.values()) if cap.capacidades else 0)
            )
        pulgadas, capacidad = encontrado
        return pulgadas, PULGADAS_A_MM[pulgadas], capacidad


PULGADAS_A_MM: dict[str, float] = {
    '1/2"': 12.70,
    '3/4"': 19.05,
    '1"': 25.40,
    '1-1/4"': 31.75,
    '1-1/2"': 38.10,
    '2"': 50.80,
    '2-1/2"': 63.50,
    '3"': 76.20,
    '3-1/2"': 88.90,
    '4"': 101.60,
}


def cargar_config(ruta_json: str, raiz_proyecto: str | None = None) -> ConfigRuteo:
    if not os.path.exists(ruta_json):
        raise ConfigError("No existe la configuracion: %s" % ruta_json)
    with open(ruta_json, "r", encoding="utf-8-sig") as f:
        datos = json.load(f)
    if raiz_proyecto is None:
        raiz_proyecto = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(ruta_json)))))
    return ConfigRuteo(datos, raiz_proyecto)
