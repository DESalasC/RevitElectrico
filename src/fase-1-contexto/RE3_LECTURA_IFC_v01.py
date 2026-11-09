"""
================================================================================
RE3_LECTURA_IFC_v01.py — Lectura de modelos IFC con ifcopenshell
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)
================================================================================

OBJETIVO:
  Leer un archivo IFC exportado desde Revit 2026 (o cualquier herramienta BIM)
  y extraer, en forma de JSON intermedio:
    - Elementos por tipo Ifc (IfcWall, IfcFloor, IfcSpace, IfcBuildingElementProxy, etc.)
    - Cantidades de cada elemento (GrossArea, NetVolume, GrossVolume, Length)
    - Qto sets (conjuntos de cantidades) de cada elemento
    - Tipos de elemento (IfcWallType, IfcFloorType, etc.) y sus nombres
    - Resumen de conteos por tipo

  Solo lectura. No modifica el IFC. Requiere ifcopenshell.

ENTRADAS (CLI):
  --ifc       : ruta al archivo IFC fuente
  --json-out  : ruta del JSON de salida (default: data/<chip>_ifc.json)
  --chip      : identificador del predio/lote (default: SANTAMARTA_T5)

SALIDA:
  JSON con:
    - metadatos (chip, origen ifc, schema, total elementos)
    - resumen (conteos por tipo Ifc)
    - elementos: lista de {guid, tipo, nombre, cantidad_nombre, cantidad_valor, unidad}
    - qto_sets: lista de {guid, tipo, nombre_qto, nombre_cantidad, valor, unidad}
    - tipos_elemento: lista de {tipo_ifc, nombre_tipo, conteo}

HISTORIAL:
  v01.0 (2026-10-21) — versión inicial. Lectura IFC para RevitElectrico.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CHIP = "SANTAMARTA_T5"

# Cantidades que intentamos extraer de cada elemento (por nombre de Qto)
CANTIDADES_BUSCADAS = (
    "GrossArea",
    "NetArea",
    "GrossVolume",
    "NetVolume",
    "Length",
    "Height",
    "Width",
    "Thickness",
)


def _abrir_ifc(ifc_path: Path):
    """Abre el archivo IFC y devuelve el modelo. Lanza SystemExit si falta ifcopenshell."""
    try:
        import ifcopenshell
        import ifcopenshell.util.element as el_util
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise SystemExit(
            "ifcopenshell no está instalado. Instálelo con: pip install ifcopenshell"
        ) from exc

    model = ifcopenshell.open(str(ifc_path))
    return model, el_util


def _extraer_cantidad(
    el_util: Any, elemento: Any, nombre_cantidad: str
) -> Optional[Tuple[float, str]]:
    """Intenta obtener una cantidad de un elemento y devuelve (valor, unidad) o None."""
    try:
        q = el_util.get_quantity(elemento, nombre_cantidad)
    except Exception:
        return None
    if q is None:
        return None
    try:
        valor = float(getattr(q, "val", q))
    except (TypeError, ValueError):
        return None
    unidad = getattr(q, "unit", None) or ""
    return valor, str(unidad)


def _extraer_qto_sets(
    el_util: Any, elemento: Any
) -> List[Dict[str, Any]]:
    """Extrae todos los Qto sets y sus cantidades de un elemento."""
    resultado: List[Dict[str, Any]] = []
    try:
        qtos = el_util.get_psets(elemento).get("Qto_*", {}) if False else {}
    except Exception:
        qtos = {}

    # Usar ifcopenshell.util.element.get_qto_sets cuando esté disponible
    try:
        qto_sets = el_util.get_qto_sets(elemento)  # type: ignore[attr-defined]
    except Exception:
        qto_sets = {}

    if not qto_sets:
        return resultado

    for nombre_qto, cantidades in qto_sets.items():
        if not isinstance(cantidades, dict):
            continue
        for nombre_cant, valor in cantidades.items():
            try:
                valor_float = float(valor)
            except (TypeError, ValueError):
                continue
            unidad = ""
            try:
                # intentar resolver unidad del quantity
                q = el_util.get_quantity(elemento, nombre_cant)
                if q is not None:
                    unidad = str(getattr(q, "unit", "") or "")
            except Exception:
                pass
            resultado.append(
                {
                    "nombre_qto": nombre_qto,
                    "nombre_cantidad": nombre_cant,
                    "valor": round(valor_float, 4),
                    "unidad": unidad,
                }
            )
    return resultado


# Tipos Ifc que heredan de IfcElement y suelen aparecer en modelos BIM.
# Se recorren por separado porque by_type("IfcElement") no incluye subtipos
# en todas las versiones de ifcopenshell.
TIPOS_IFC_ELEMENTO = (
    "IfcElement",
    "IfcBuilding",
    "IfcBuildingStorey",
    "IfcSpace",
    "IfcWall",
    "IfcFloor",
    "IfcRoof",
    "IfcColumn",
    "IfcBeam",
    "IfcDoor",
    "IfcWindow",
    "IfcBuildingElementProxy",
    "IfcDistributionElement",
    "IfcFlowTerminal",
    "IfcFlowController",
    "IfcFlowMovingDevice",
    "IfcFlowStorageDevice",
    "IfcEnergyConversionDevice",
    "IfcCivilElement",
)


def _procesar_elemento(
    el_util: Any,
    elemento: Any,
    elementos: List[Dict[str, Any]],
    qto_sets: List[Dict[str, Any]],
    conteo_por_tipo: Dict[str, int],
    tipos_elemento: Dict[str, Dict[str, Any]],
    guids_vistos: set,
) -> None:
    """Procesa un único elemento Ifc: extrae guid, tipo, nombre, cantidades y Qto sets."""
    guid = getattr(elemento, "GlobalId", None) or ""
    if guid in guids_vistos:
        return
    guids_vistos.add(guid)

    tipo_ifc = elemento.is_a()
    nombre = getattr(elemento, "Name", None) or ""

    conteo_por_tipo[tipo_ifc] = conteo_por_tipo.get(tipo_ifc, 0) + 1

    # Registrar tipo de elemento
    if tipo_ifc not in tipos_elemento:
        tipos_elemento[tipo_ifc] = {
            "tipo_ifc": tipo_ifc,
            "nombre_tipo": nombre,
            "conteo": 0,
        }
    tipos_elemento[tipo_ifc]["conteo"] += 1

    # Extraer cantidades buscadas
    cantidades_encontradas: List[Dict[str, Any]] = []
    for nombre_cant in CANTIDADES_BUSCADAS:
        res = _extraer_cantidad(el_util, elemento, nombre_cant)
        if res is not None:
            valor, unidad = res
            cantidades_encontradas.append(
                {
                    "nombre_cantidad": nombre_cant,
                    "valor": round(valor, 4),
                    "unidad": unidad,
                }
            )

    elementos.append(
        {
            "guid": guid,
            "tipo_ifc": tipo_ifc,
            "nombre": nombre,
            "cantidades": cantidades_encontradas,
        }
    )

    # Qto sets del elemento
    qtos = _extraer_qto_sets(el_util, elemento)
    for q in qtos:
        qto_sets.append(
            {
                "guid": guid,
                "tipo_ifc": tipo_ifc,
                **q,
            }
        )


def leer_ifc(
    ifc_path: Path,
    json_out: Path,
    chip: str = DEFAULT_CHIP,
) -> Dict[str, Any]:
    """
    Lee un archivo IFC, extrae elementos, cantidades, Qto sets y tipos,
    escribe el JSON de salida en disco y lo devuelve.
    """
    model, el_util = _abrir_ifc(ifc_path)

    elementos: List[Dict[str, Any]] = []
    qto_sets: List[Dict[str, Any]] = []
    conteo_por_tipo: Dict[str, int] = {}
    tipos_elemento: Dict[str, Dict[str, Any]] = {}
    guids_vistos: set = set()

    for tipo_ifc in TIPOS_IFC_ELEMENTO:
        try:
            entidades = model.by_type(tipo_ifc)
        except RuntimeError:
            # El tipo no existe en el schema del IFC (ej. IfcFloor no existe en IFC4)
            continue
        for elemento in entidades:
            _procesar_elemento(
                el_util,
                elemento,
                elementos,
                qto_sets,
                conteo_por_tipo,
                tipos_elemento,
                guids_vistos,
            )

    salida = {
        "metadatos": {
            "chip": chip,
            "origen_ifc": str(ifc_path),
            "schema": model.schema,
            "total_elementos": len(elementos),
            "version": "v01.0",
        },
        "resumen": {
            "conteos_por_tipo": dict(sorted(conteo_por_tipo.items())),
            "total_tipos_distintos": len(conteo_por_tipo),
            "total_qto_sets": len(qto_sets),
        },
        "elementos": elementos,
        "qto_sets": qto_sets,
        "tipos_elemento": list(tipos_elemento.values()),
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lee un modelo IFC y extrae elementos, cantidades y Qto sets a JSON (RevitElectrico)."
    )
    parser.add_argument(
        "--ifc", type=str, required=True, help="Ruta al archivo IFC fuente"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de salida (default: data/<chip>_ifc.json)",
    )
    parser.add_argument(
        "--chip",
        type=str,
        default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    ifc_path = Path(args.ifc)
    if not ifc_path.exists():
        raise SystemExit(f"El archivo IFC no existe: {ifc_path}")

    chip = args.chip or DEFAULT_CHIP
    if args.json_out:
        json_out = Path(args.json_out)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        json_out = root / "data" / f"{chip}_ifc.json"

    resultado = leer_ifc(ifc_path, json_out, chip)

    print("=== Lectura IFC completada ===")
    print(f"Origen: {resultado['metadatos']['origen_ifc']}")
    print(f"Chip: {resultado['metadatos']['chip']}")
    print(f"Schema IFC: {resultado['metadatos']['schema']}")
    print(f"Total elementos: {resultado['metadatos']['total_elementos']}")
    print(f"Tipos distintos: {resultado['resumen']['total_tipos_distintos']}")
    print(f"Qto sets extraídos: {resultado['resumen']['total_qto_sets']}")
    print("Conteos por tipo:")
    for tipo, conteo in resultado["resumen"]["conteos_por_tipo"].items():
        print(f"  {conteo:5d}  {tipo}")
    print(f"JSON guardado en: {json_out}")


if __name__ == "__main__":
    main()

