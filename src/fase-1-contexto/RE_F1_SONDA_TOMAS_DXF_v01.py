# -*- coding: utf-8 -*-
"""Sonda de tomas en el DXF de un apartamento (F1).

Objetivo: averiguar de donde puede salir la altura de cada toma sin adivinar por
coordenadas. Se revisan tres fuentes, en orden de fiabilidad:

1. Atributos del INSERT (si el bloque los trae: circuito, altura, tipo).
2. La capa del INSERT (si el dibujo separa variantes por capa).
3. El texto mas cercano (TEXT/MTEXT), que en los planos electricos suele llevar el
   codigo de circuito o la anotacion de altura.

No decide alturas: emite la evidencia para que el operador marque las excepciones.

Uso:
    .venv\\Scripts\\python.exe src\\fase-1-contexto\\RE_F1_SONDA_TOMAS_DXF_v01.py ^
        --dxf "D:\\...\\Apartamento Tipo E 06.dxf" --salida data\\sondeo_tomas_E06_v01.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf

PATRON_TOMA = re.compile(r"TOMA|GFCI|TEL|NET|COMUNIC", re.IGNORECASE)
PATRON_MOBILIARIO = re.compile(
    r"ESTUFA|NEVERA|REFRIG|LAVAPLATOS|FREGADERO|MESON|MESADA|GABINETE|ALACENA|EXTRACTOR|CAMPANA",
    re.IGNORECASE,
)
RADIO_TEXTO_M = 2.5


def _punto(entidad: Any) -> tuple[float, float] | None:
    try:
        if entidad.dxftype() == "INSERT":
            p = entidad.dxf.insert
        elif entidad.dxftype() in ("TEXT",):
            p = entidad.dxf.insert
        else:
            p = entidad.dxf.insert
        return (float(p[0]), float(p[1]))
    except Exception:
        return None


def _texto(entidad: Any) -> str:
    tipo = entidad.dxftype()
    try:
        if tipo == "MTEXT":
            return entidad.plain_text()
        if tipo == "TEXT":
            return entidad.dxf.text
    except Exception:
        pass
    return ""


def _atributos(entidad: Any) -> dict[str, str]:
    atributos: dict[str, str] = {}
    try:
        for atributo in entidad.attribs:
            tag = getattr(atributo.dxf, "tag", "") or ""
            valor = getattr(atributo.dxf, "text", "") or ""
            if tag or valor:
                atributos[tag] = valor
    except Exception:
        pass
    return atributos


def _capa(entidad: Any) -> str:
    try:
        return entidad.dxf.layer
    except Exception:
        return ""


def _bloque(entidad: Any) -> str:
    try:
        return entidad.dxf.name
    except Exception:
        return ""


def sondear(ruta_dxf: Path, radio: float = RADIO_TEXTO_M) -> dict[str, Any]:
    doc = ezdxf.readfile(str(ruta_dxf))
    msp = doc.modelspace()

    textos: list[tuple[float, float, str, str]] = []
    mobiliario: list[tuple[float, float, str, str]] = []
    tomas: list[Any] = []
    capas: Counter[str] = Counter()

    for entidad in msp:
        try:
            tipo = entidad.dxftype()
            capa = _capa(entidad)
            if tipo in ("TEXT", "MTEXT"):
                punto = _punto(entidad)
                contenido = _texto(entidad).strip()
                if punto and contenido:
                    textos.append((punto[0], punto[1], contenido, capa))
                continue
            if tipo != "INSERT":
                continue
            nombre = _bloque(entidad)
            if PATRON_TOMA.search(nombre) or PATRON_TOMA.search(capa):
                tomas.append(entidad)
                capas[capa] += 1
            elif PATRON_MOBILIARIO.search(nombre) or PATRON_MOBILIARIO.search(capa):
                punto = _punto(entidad)
                if punto:
                    mobiliario.append((punto[0], punto[1], nombre or capa, capa))
        except Exception:
            continue

    filas: list[dict[str, Any]] = []
    for entidad in tomas:
        punto = _punto(entidad)
        if punto is None:
            continue
        x, y = punto
        cercanos = []
        for tx, ty, contenido, capa_texto in textos:
            distancia = math.hypot(tx - x, ty - y)
            if distancia <= radio:
                cercanos.append(
                    {"texto": contenido, "capa": capa_texto, "dist_m": round(distancia, 3)}
                )
        cercanos.sort(key=lambda t: t["dist_m"])

        muebles = []
        for mx, my, nombre_bloque, capa_mueble in mobiliario:
            distancia = math.hypot(mx - x, my - y)
            if distancia <= radio:
                muebles.append(
                    {"bloque": nombre_bloque, "capa": capa_mueble, "dist_m": round(distancia, 3)}
                )
        muebles.sort(key=lambda m: m["dist_m"])

        filas.append(
            {
                "handle": entidad.dxf.handle,
                "bloque": _bloque(entidad),
                "capa": _capa(entidad),
                "x": round(x, 4),
                "y": round(y, 4),
                "rotacion": round(float(getattr(entidad.dxf, "rotation", 0.0)), 3),
                "atributos": _atributos(entidad),
                "textos_cercanos": cercanos[:4],
                "mobiliario_cercano": muebles[:3],
            }
        )

    filas.sort(key=lambda f: (f["capa"], f["handle"]))

    return {
        "version": "1.0",
        "proyecto": "RE",
        "fase": "F1",
        "dxf": str(ruta_dxf),
        "radio_texto_m": radio,
        "resumen": {
            "tomas": len(filas),
            "capas_de_toma": dict(capas),
            "bloques_de_toma": dict(Counter(f["bloque"] for f in filas)),
            "con_atributos": sum(1 for f in filas if f["atributos"]),
            "con_texto_cercano": sum(1 for f in filas if f["textos_cercanos"]),
            "con_mobiliario_cercano": sum(1 for f in filas if f["mobiliario_cercano"]),
        },
        "tomas": filas,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sonda de tomas en DXF de apartamento.")
    parser.add_argument("--dxf", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--radio", type=float, default=RADIO_TEXTO_M)
    args = parser.parse_args(argv)

    ruta_dxf = Path(args.dxf)
    if not ruta_dxf.is_file():
        print("No existe el DXF: {r}".format(r=ruta_dxf))
        return 2

    datos = sondear(ruta_dxf, args.radio)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    resumen = datos["resumen"]
    print("Tomas encontradas: {n}".format(n=resumen["tomas"]))
    print("Capas: {c}".format(c=resumen["capas_de_toma"]))
    print("Bloques: {b}".format(b=resumen["bloques_de_toma"]))
    print("Con atributos: {n}".format(n=resumen["con_atributos"]))
    print("Con texto cercano: {n}".format(n=resumen["con_texto_cercano"]))
    print("Con mobiliario cercano: {n}".format(n=resumen["con_mobiliario_cercano"]))
    print("JSON: {s}".format(s=salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
