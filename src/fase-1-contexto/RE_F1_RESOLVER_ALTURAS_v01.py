# -*- coding: utf-8 -*-
"""Resuelve la altura local de montaje de cada dispositivo del inventario E06.

Orden de precedencia:

1. Excepcion por handle (config/alturas_tomas_v01.json).
2. Anotacion de altura del DXF, asignada por vecindad y consumida una sola vez,
   salvo para los codigos listados en `anotaciones_ignoradas_por_codigo`.
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


def anclar_excepciones_por_posicion(
    dispositivos: list[dict[str, Any]],
    entradas: list[dict[str, Any]],
    tolerancia_m: float = 0.02,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Ancla cada excepcion a un aparato por codigo + coordenada DXF.

    Los handles se regeneran cuando alguien reexporta el DXF, pero las coordenadas no cambian:
    por eso el anclaje estable es (codigo, x, y), no el handle. Devuelve ``{handle: regla}`` y
    la lista de excepciones que no encontraron aparato (para no fallar en silencio).
    """
    ancladas: dict[str, dict[str, Any]] = {}
    sin_anclar: list[dict[str, Any]] = []

    for entrada in entradas:
        codigo = entrada.get("codigo")
        candidatos = [d for d in dispositivos if d.get("nombre") == codigo]
        mejor: dict[str, Any] | None = None
        mejor_d: float | None = None
        for dispositivo in candidatos:
            distancia = (
                (dispositivo["x"] - float(entrada["x"])) ** 2
                + (dispositivo["y"] - float(entrada["y"])) ** 2
            ) ** 0.5
            if mejor_d is None or distancia < mejor_d:
                mejor, mejor_d = dispositivo, distancia

        if mejor is None or mejor_d is None or mejor_d > tolerancia_m:
            sin_anclar.append(
                {
                    "codigo": codigo,
                    "altura_m": entrada.get("altura_m"),
                    "dist_m": round(mejor_d, 4) if mejor_d is not None else None,
                    "motivo": "sin aparato a menos de {t} m".format(t=tolerancia_m),
                }
            )
            continue

        ancladas[mejor["handle"]] = {
            "altura_m": entrada["altura_m"],
            "nota": entrada.get("nota", ""),
            "element_id_revit": entrada.get("element_id_revit"),
            "origen": "posicion",
            "dist_m": round(mejor_d, 6),
        }

    return ancladas, sin_anclar


def resolver(
    inventario: dict[str, Any],
    config: dict[str, Any],
    anotaciones: list[dict[str, Any]],
    apartamento: str | None = None,
) -> dict[str, Any]:
    dispositivos = inventario["dispositivos"]
    radio = float(config["anotaciones_dxf"]["radio_asignacion_m"])
    asignadas, conflictos = asignar_anotaciones(dispositivos, anotaciones, radio)

    reglas = config["regla_base_altura_m"]
    excepciones = dict(config["excepciones_por_handle"])
    ignoradas = config.get("anotaciones_ignoradas_por_codigo", {})
    anotaciones_ignoradas: list[dict[str, Any]] = []

    ancladas: dict[str, dict[str, Any]] = {}
    sin_anclar: list[dict[str, Any]] = []
    if apartamento:
        entradas = config.get("excepciones_por_apartamento", {}).get(apartamento, [])
        if entradas:
            ancladas, sin_anclar = anclar_excepciones_por_posicion(dispositivos, entradas)
            # La posicion gana sobre el handle: es la unica que sobrevive a una reexportacion.
            excepciones.update(ancladas)

    resueltos: list[dict[str, Any]] = []
    for dispositivo in dispositivos:
        handle = dispositivo["handle"]
        nombre = dispositivo["nombre"]
        altura: float | None = None
        origen = ""

        if handle in excepciones:
            altura = float(excepciones[handle]["altura_m"])
            origen = "excepcion_posicion" if handle in ancladas else "excepcion"
            anotacion = asignadas.get(handle)
            if anotacion and abs(anotacion["altura_m"] - altura) > 0.02:
                conflictos.append(
                    {
                        "handle": handle,
                        "motivo": "anotacion contradice excepcion",
                        "detalle": {"excepcion_m": altura, "anotacion_m": anotacion["altura_m"], "texto": anotacion["texto"]},
                    }
                )
        elif nombre in ignoradas:
            # Estandarizacion explicita: el codigo manda sobre lo que anote el plano.
            altura = float(reglas[nombre]) if nombre in reglas else None
            origen = "regla_base_estandarizada"
            if handle in asignadas:
                anotaciones_ignoradas.append(
                    {
                        "handle": handle,
                        "codigo": nombre,
                        "anotacion_m": asignadas[handle]["altura_m"],
                        "texto": asignadas[handle]["texto"],
                        "motivo": "codigo estandarizado a {v} m".format(v=altura),
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

    # Un aviso de "anotacion lejana" deja de ser conflicto si la anotacion coincide con la
    # excepcion confirmada: la distancia era el unico motivo de duda y el valor la despeja.
    conflictos = [
        conflicto
        for conflicto in conflictos
        if not (
            conflicto["motivo"] == "anotacion lejana"
            and conflicto["handle"] in excepciones
            and abs(
                float(conflicto["detalle"]["altura_m"])
                - float(excepciones[conflicto["handle"]]["altura_m"])
            )
            <= 0.02
        )
    ]

    return {
        "version": "2.0",
        "proyecto": "RE",
        "fase": "F1",
        "apartamento": "Apartamento Tipo E 06",
        "nivel_elevacion_m": NIVEL_PISO5_M,
        "fuente": "inventario v01 + anotaciones de altura del DXF + reglas de config/alturas_tomas_v01.json",
        "regla": "excepcion > anotacion DXF > regla base (los codigos de anotaciones_ignoradas_por_codigo saltan la anotacion)",
        "total": len(resueltos),
        "por_origen": por_origen,
        "anotaciones_dxf_detectadas": len(anotaciones),
        "anotaciones_ignoradas": anotaciones_ignoradas,
        "excepciones_ancladas": {
            "apartamento": apartamento,
            "aplicadas_por_handle": por_origen.get("excepcion", 0),
            "aplicadas_por_posicion": por_origen.get("excepcion_posicion", 0),
            "sin_anclar": sin_anclar,
        },
        "conflictos": conflictos,
        "dispositivos": resueltos,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resuelve alturas de montaje del inventario E06.")
    parser.add_argument("--dxf", required=True)
    parser.add_argument("--inventario", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--apartamento", default=None, help="Clave de apartamento para anclar excepciones por posicion (p.ej. 'E 06')")
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
    resultado = resolver(inventario, config, anotaciones, apartamento=args.apartamento)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print("Dispositivos: {n}".format(n=resultado["total"]))
    print("Anotaciones de altura en el DXF: {n}".format(n=resultado["anotaciones_dxf_detectadas"]))
    print("Por origen: {o}".format(o=resultado["por_origen"]))
    anclaje = resultado.get("excepciones_ancladas") or {}
    if anclaje.get("apartamento"):
        print("Excepciones ancladas en {a}: por posicion {p}, por handle {h}".format(
            a=anclaje["apartamento"], p=anclaje["aplicadas_por_posicion"], h=anclaje["aplicadas_por_handle"]))
        for pendiente in anclaje.get("sin_anclar", []):
            print("   SIN ANCLAR: {c} (altura {h}, dist {d})".format(
                c=pendiente.get("codigo"), h=pendiente.get("altura_m"), d=pendiente.get("dist_m")))
    if resultado["conflictos"]:
        print("Conflictos: {n}".format(n=len(resultado["conflictos"])))
        for conflicto in resultado["conflictos"][:8]:
            print("   {h}: {m} -> {d}".format(h=conflicto["handle"], m=conflicto["motivo"], d=conflicto["detalle"]))
    print("JSON: {s}".format(s=salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
