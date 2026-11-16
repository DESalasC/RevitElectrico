# -*- coding: utf-8 -*-
"""Resuelve la altura local de montaje de cada dispositivo del inventario E06.

Orden de precedencia:

1. Excepcion por handle (config/alturas_tomas_v01.json).
2. Anotacion de altura del DXF, asignada por vecindad y consumida una sola vez.
3. Regla base por tipo de dispositivo.

Produce un inventario nuevo (v02) sin tocar el v01, con `altura_local_m`, `origen_altura`
y `z_absoluta_m`. Si una anotacion contradice una excepcion, gana la excepcion y el
conflicto se reporta.

Uso:
    .venv\\Scripts\\python.exe src\\fase-1-contexto\\RE_F1_RESOLVER_ALTURAS_v01.py ^
        --dxf "D:\\...\\Apartamento Tipo E 06.dxf" ^
        --inventario data\\inventario_dispositivos_E06_v01.json ^
        --config config\\alturas_tomas_v01.json ^
        --salida data\\inventario_dispositivos_E06_v02.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import ezdxf

NIVEL_PISO5_M = 13.22
PATRON_TOMA = re.compile(r"TOMA|GFCI|TEL|NET", re.IGNORECASE)


def _punto_texto(entidad: Any) -> tuple[float, float] | None:
    try:
        p = entidad.dxf.insert
        return (float(p[0]), float(p[1]))
    except Exception:
        return None


def _contenido(entidad: Any) -> str:
    try:
        if entidad.dxftype() == "MTEXT":
            return entidad.plain_text()
        return entidad.dxf.text
    except Exception:
        return ""


def extraer_anotaciones(ruta_dxf: Path, patrones: list[str]) -> list[dict[str, Any]]:
    """Devuelve las anotaciones de altura del DXF con su posicion y valor en metros."""
    compilados = [re.compile(p) for p in patrones]
    doc = ezdxf.readfile(str(ruta_dxf))
    anotaciones: list[dict[str, Any]] = []

    for entidad in doc.modelspace():
        if entidad.dxftype() not in ("TEXT", "MTEXT"):
            continue
        punto = _punto_texto(entidad)
        if punto is None:
            continue
        texto = _contenido(entidad).strip()
        if not texto:
            continue
        for patron in compilados:
            coincidencia = patron.search(texto)
            if not coincidencia:
                continue
            valor = 0.30 if "h-0.3" in texto.replace(",", ".").replace(" ", "").lower() else None
            if valor is None:
                try:
                    crudo = coincidencia.group("v").replace(",", ".")
                    valor = float(crudo)
                except Exception:
                    continue
            anotaciones.append(
                {
                    "texto": texto,
                    "x": punto[0],
                    "y": punto[1],
                    "altura_m": valor,
                    "capa": getattr(entidad.dxf, "layer", ""),
                }
            )
            break

    return anotaciones


def asignar_anotaciones(
    dispositivos: list[dict[str, Any]], anotaciones: list[dict[str, Any]], radio: float
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Asigna cada anotacion al dispositivo mas cercano dentro del radio, sin repetir."""
    usadas: set[int] = set()
    asignadas: dict[str, dict[str, Any]] = {}
    conflictos: list[dict[str, Any]] = []

    pares: list[tuple[float, int, str]] = []
    for indice, anotacion in enumerate(anotaciones):
        for dispositivo in dispositivos:
            distancia = math.hypot(anotacion["x"] - dispositivo["x"], anotacion["y"] - dispositivo["y"])
            if distancia <= radio:
                pares.append((distancia, indice, dispositivo["handle"]))
    pares.sort(key=lambda p: p[0])

    handles_ya_asignados: set[str] = set()
    for distancia, indice, handle in pares:
        if indice in usadas or handle in handles_ya_asignados:
            continue
        usadas.add(indice)
        handles_ya_asignados.add(handle)
        asignadas[handle] = {"altura_m": anotaciones[indice]["altura_m"], "dist_m": round(distancia, 3), "texto": anotaciones[indice]["texto"]}

    for handle, datos in asignadas.items():
        if datos["dist_m"] > 0.30:
            conflictos.append(
                {"handle": handle, "motivo": "anotacion lejana", "detalle": datos}
            )
    return asignadas, conflictos


def resolver(
    inventario: dict[str, Any],
    config: dict[str, Any],
    anotaciones: list[dict[str, Any]],
) -> dict[str, Any]:
    dispositivos = inventario["dispositivos"]
    radio = float(config["anotaciones_dxf"]["radio_asignacion_m"])
    asignadas, conflictos = asignar_anotaciones(dispositivos, anotaciones, radio)

    reglas = config["regla_base_altura_m"]
    excepciones = config["excepciones_por_handle"]

    resueltos: list[dict[str, Any]] = []
    for dispositivo in dispositivos:
        handle = dispositivo["handle"]
        nombre = dispositivo["nombre"]
        altura: float | None = None
        origen = ""

        if handle in excepciones:
            altura = float(excepciones[handle]["altura_m"])
            origen = "excepcion"
            anotacion = asignadas.get(handle)
            if anotacion and abs(anotacion["altura_m"] - altura) > 0.02:
                conflictos.append(
                    {
                        "handle": handle,
                        "motivo": "anotacion contradice excepcion",
                        "detalle": {"excepcion_m": altura, "anotacion_m": anotacion["altura_m"], "texto": anotacion["texto"]},
                    }
                )
        elif handle in asignadas:
            altura = float(asignadas[handle]["altura_m"])
            origen = "anotacion_dxf"
        elif nombre in reglas:
            altura = float(reglas[nombre])
            origen = "regla_base"
        else:
            origen = "sin_regla"

        resuelto = dict(dispositivo)
        resuelto["altura_local_m"] = round(altura, 4) if altura is not None else None
        resuelto["origen_altura"] = origen
        resuelto["z_absoluta_m"] = round(NIVEL_PISO5_M + altura, 4) if altura is not None else None
        resueltos.append(resuelto)

    por_origen: dict[str, int] = {}
    for fila in resueltos:
        por_origen[fila["origen_altura"]] = por_origen.get(fila["origen_altura"], 0) + 1

    return {
        "version": "2.0",
        "proyecto": "RE",
        "fase": "F1",
        "apartamento": "Apartamento Tipo E 06",
        "nivel_elevacion_m": NIVEL_PISO5_M,
        "fuente": "inventario v01 + anotaciones de altura del DXF + reglas de config/alturas_tomas_v01.json",
        "regla": "excepcion > anotacion DXF > regla base",
        "total": len(resueltos),
        "por_origen": por_origen,
        "anotaciones_dxf_detectadas": len(anotaciones),
        "conflictos": conflictos,
        "dispositivos": resueltos,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resuelve alturas de montaje del inventario E06.")
    parser.add_argument("--dxf", required=True)
    parser.add_argument("--inventario", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--salida", required=True)
    args = parser.parse_args(argv)

    ruta_dxf = Path(args.dxf)
    if not ruta_dxf.is_file():
        print("No existe el DXF: {r}".format(r=ruta_dxf))
        return 2

    with Path(args.inventario).open(encoding="utf-8") as fh:
        inventario = json.load(fh)
    with Path(args.config).open(encoding="utf-8") as fh:
        config = json.load(fh)

    anotaciones = extraer_anotaciones(ruta_dxf, config["anotaciones_dxf"]["patrones"])
    resultado = resolver(inventario, config, anotaciones)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print("Dispositivos: {n}".format(n=resultado["total"]))
    print("Anotaciones de altura en el DXF: {n}".format(n=resultado["anotaciones_dxf_detectadas"]))
    print("Por origen: {o}".format(o=resultado["por_origen"]))
    if resultado["conflictos"]:
        print("Conflictos: {n}".format(n=len(resultado["conflictos"])))
        for conflicto in resultado["conflictos"][:8]:
            print("   {h}: {m} -> {d}".format(h=conflicto["handle"], m=conflicto["motivo"], d=conflicto["detalle"]))
    print("JSON: {s}".format(s=salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
