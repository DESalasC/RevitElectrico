# -*- coding: utf-8 -*-
"""Inventario de dispositivos por unidad a partir de los DXF de ArchivosBase.

Solo lectura: no toca el modelo de Revit. Cuenta INSERT de aparatos electricos
por archivo, los agrupa por unidad y deja dos salidas:

  data/inventario_unidades_v01.json      (legible por el colocador y por tests)
  entregables/_inventario_unidades_v01.csv  (revision del operador)

Un bloque se considera aparato si empieza por ELEC- (salvo ELEC-POWER-PANEL),
por 'Bala Stil Led' o por 'S3'. Los marcadores de tuberia y el tablero no cuentan
como aparato.

Uso:
    .venv\\Scripts\\python.exe src\\fase-1-contexto\\RE_F1_INVENTARIO_UNIDADES_v01.py
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import ezdxf

PREFIJOS_APARATO = ("ELEC-", "Bala Stil Led", "S3")
# Bloques que empiezan por ELEC- pero no son aparatos: tuberia, tablero, cableado.
PATRONES_NO_APARATO = ("PIPE", "PANEL", "SERVICE", "WIRE", "IDEN")
EXCLUIDOS = {"ELEC-POWER-PANEL"}


def es_aparato(nombre_bloque: str) -> bool:
    """True si el bloque representa un aparato electrico colocable."""
    if nombre_bloque in EXCLUIDOS:
        return False
    if any(patron in nombre_bloque.upper() for patron in PATRONES_NO_APARATO):
        return False
    return nombre_bloque.startswith(PREFIJOS_APARATO)


def contar_aparatos(ruta_dxf: str | os.PathLike[str]) -> dict[str, int]:
    """Cuenta INSERT de aparatos en el espacio modelo de un DXF."""
    doc = ezdxf.readfile(str(ruta_dxf))
    conteo: dict[str, int] = {}
    for entidad in doc.modelspace().query("INSERT"):
        nombre = entidad.dxf.name
        if es_aparato(nombre):
            conteo[nombre] = conteo.get(nombre, 0) + 1
    return dict(sorted(conteo.items()))


def unidad_desde_nombre(nombre_archivo: str) -> str:
    """Extrae el nombre de la unidad quitando el prefijo y la extension."""
    base = Path(nombre_archivo).stem
    for prefijo in ("ELEC-Apartamento Tipo ", "ELEC-Apartamentos Tipo ",
                    "Apartamento Tipo ", "Apartamentos Tipo "):
        if base.startswith(prefijo):
            return base[len(prefijo):].strip()
    return base


def inventariar(rutas: Iterable[str | os.PathLike[str]]) -> dict[str, Any]:
    """Construye el inventario de un conjunto de DXF."""
    unidades: dict[str, Any] = {}
    total_bloques: dict[str, int] = {}
    total_aparatos = 0
    for ruta in sorted(rutas, key=lambda p: Path(p).name):
        conteo = contar_aparatos(ruta)
        nombre = Path(ruta).name
        unidades[nombre] = {
            "unidad": unidad_desde_nombre(nombre),
            "total": sum(conteo.values()),
            "por_bloque": conteo,
        }
        total_aparatos += sum(conteo.values())
        for bloque, n in conteo.items():
            total_bloques[bloque] = total_bloques.get(bloque, 0) + n
    return {
        "version": "v01",
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "fuente": "ArchivosBase/*.dxf",
        "criterio": "INSERT cuyo nombre empieza por ELEC-, 'Bala Stil Led' o 'S3', salvo ELEC-POWER-PANEL",
        "total_unidades": len(unidades),
        "total_aparatos": total_aparatos,
        "total_por_bloque": dict(sorted(total_bloques.items())),
        "unidades": unidades,
    }


def buscar_dxfs(base: Path) -> list[Path]:
    """Devuelve los DXF de apartamento de una carpeta."""
    patrones = ("Apartamento Tipo *.dxf", "Apartamentos Tipo *.dxf",
                "ELEC-Apartamento Tipo *.dxf")
    rutas: set[Path] = set()
    for patron in patrones:
        rutas.update(base.glob(patron))
    return sorted(rutas)


def escribir_csv(inventario: dict[str, Any], destino: Path) -> None:
    """Escribe el inventario en CSV con ; y BOM para Excel."""
    bloques = sorted(inventario["total_por_bloque"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(["archivo", "unidad", "total"] + bloques)
        for archivo, datos in inventario["unidades"].items():
            fila = [archivo, datos["unidad"], datos["total"]]
            fila += [datos["por_bloque"].get(b, 0) for b in bloques]
            escritor.writerow(fila)
        totales = [inventario["total_por_bloque"].get(b, 0) for b in bloques]
        escritor.writerow(["TOTAL", "", inventario["total_aparatos"]] + totales)


def main() -> int:
    raiz = Path(os.environ.get("REVITELECTRICO_ROOT", Path(__file__).resolve().parents[2]))
    base = raiz / "ArchivosBase"
    rutas = buscar_dxfs(base)
    if not rutas:
        print("No se encontraron DXF de apartamento en", base)
        return 1

    inventario = inventariar(rutas)
    salida_json = raiz / "data" / "inventario_unidades_v01.json"
    salida_json.write_text(json.dumps(inventario, ensure_ascii=False, indent=1), encoding="utf-8")

    salida_csv = raiz / "entregables" / "_inventario_unidades_v01.csv"
    escribir_csv(inventario, salida_csv)

    print("DXF leidos:", inventario["total_unidades"])
    print("Aparatos:", inventario["total_aparatos"])
    for archivo, datos in inventario["unidades"].items():
        print("  {:45s} {:3d}".format(archivo, datos["total"]))
    print("JSON:", salida_json)
    print("CSV :", salida_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
