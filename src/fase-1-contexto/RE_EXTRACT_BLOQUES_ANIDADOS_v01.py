# -*- coding: utf-8 -*-
"""
RE_EXTRACT_BLOQUES_ANIDADOS_v01.py — Extrae bloques anidados de un DXF individual
de apartamento y genera la jerarquía para mapeo a familias de Revit.

Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)

OBJETIVO:
  Leer un DXF individual de apartamento (ej: "Apartamento Tipo F 02.dxf") que
  contiene definiciones de bloque con dispositivos eléctricos anidados
  (tomas, interruptores, luminarias, tableros, telefonía, datos, etc.) y
  generar un JSON con la jerarquía completa:

    bloque_apartamento (INSERT en modelo)
      └─ componente_interno (INSERT dentro de la definición de bloque)
           ├─ tipo (INSERT, ARC, LWPOLYLINE, TEXT, CIRCLE)
           ├─ capa
           ├─ punto_insert (XYZ)
           ├─ rotacion
           └─ escala

SALIDA:
  JSON con:
    - metadatos (origen DXF, chip, versión)
    - resumen (conteos)
    - bloques_apartamento: lista de INSERT del espacio de modelo con su
      definición de bloque y los componentes anidados dentro de cada definición.
    - definiciones_bloque: detalle de cada definición de bloque con sus
      entidades (tipo, capa, punto, rotación, escala).
    - mapeo_sugerido_revit: mapeo provisional nombre_bloque -> familia_revit
      basado en el mapeo existente del proyecto.

USO (Python 3.12, fuera de Revit):
    python src\\fase-1-contexto\\RE_EXTRACT_BLOQUES_ANIDADOS_v01.py `
      --dxf-in "3.-Proceso\\_prueba_modelado\\Apartamento Tipo F 02.dxf" `
      --json-out "data\\bloques_anidados_apto_F_02.json" `
      --chip SANTAMARTA_T5

Genera: data/bloques_anidados_<chip>.json (por defecto)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import ezdxf
except ImportError as exc:  # pragma: no cover - depende del entorno
    raise SystemExit(
        "ezdxf no está instalado. Instálelo con: pip install ezdxf"
    ) from exc

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_CHIP = "SANTAMARTA_T5"

# Prefijos de capas eléctricas identificables
CAPAS_ELECTRICAS = (
    "ELEC-",
    "Elec-",
    "E-Lite-",
    "Elec-Lite-",
    "TDT",
    "Apartamento",
    "Paneles",
    "tablero",
)

# Mapeo provisional de bloques anidados -> familias de Revit
MAPEO_BLOQUES_REVIT: Dict[str, str] = {
    "ELEC-T-D-t-15A": "Toma doble 15A",
    "ELEC-T-GFCI-t-15A": "Toma GFCI 15A",
    "ELEC-TIMBRE": "Timbre",
    "ELEC-CAMPANA": "Campana",
    "ELEC-I-S-1-5A": "Interruptor simple 1x 5A",
    "ELEC-I-S-2-5A": "Interruptor simple 2x 5A",
    "ELEC-F-VENT": "Ventilador de techo",
    "ELEC-F-CONTROL": "Control de ventilador",
    "ELEC-EXT": "Tomacorriente exterior",
    "TB-Parcial": "Tablero parcial",
    "ELEC-TEL": "Toma telefónica",
    "ELEC-NET-PAU": "Punto de acceso de red (PAU)",
    "Bala Stil Led 10W": "Luminaria LED 10W",
    "Bala Stil Led 22W": "Luminaria LED 22W",
    "Bala Stil Led 13W": "Luminaria LED 13W",
    "1FTN": "Luminaria tubular 1x",
    "1FTNR": "Luminaria tubular 1x con reflector",
    "1FTN2R": "Luminaria tubular 1x 2 lámparas",
    "1TN2R": "Luminaria tubular 1x 2 reflectores",
    "1FTR": "Luminaria tubular 1x reflector",
    "1TNR": "Luminaria tubular 1x reflector",
    "2FT2N": "Luminaria tubular 2x",
}


def _pertenece_a_capa_electrica(capa: str) -> bool:
    """Devuelve True si la capa es de sistema eléctrico."""
    c = (capa or "").strip()
    return any(c.startswith(pref) for pref in CAPAS_ELECTRICAS)


def _familia_revit_sugerida(nombre_bloque: str) -> str:
    """Devuelve la familia de Revit sugerida para un bloque anidado."""
    return MAPEO_BLOQUES_REVIT.get(nombre_bloque, "Familia por definir")


def _punto_a_lista(punto) -> List[float]:
    """Convierte un punto XYZ de ezdxf a lista [x, y, z] redondeada."""
    return [round(punto.x, 3), round(punto.y, 3), round(punto.z, 3)]


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def extraer_bloques_anidados(
    dxf_path: Path,
    chip: str = DEFAULT_CHIP,
) -> Dict[str, Any]:
    """
    Lee un DXF individual de apartamento y extrae la jerarquía de bloques
    anidados con todos sus componentes internos.
    """
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    # Indexar definiciones de bloque por nombre.
    # Saltar bloques del sistema de ezdxf (*Model_Space, *Paper_Space, etc.)
    # que no son definiciones de usuario.
    definiciones: Dict[str, List[Dict[str, Any]]] = {}
    for bdef in doc.blocks:
        nombre_bdef = bdef.name
        if nombre_bdef.startswith("*"):
            continue
        entidades: List[Dict[str, Any]] = []
        for e in bdef:
            entidad = _extraer_entidad(e)
            if entidad is not None:
                entidades.append(entidad)
        definiciones[nombre_bdef] = entidades

    # Recorrer INSERTs en el espacio de modelo (marcadores de apartamento)
    bloques_apartamento: List[Dict[str, Any]] = []
    for entity in msp:
        if entity.dxftype() != "INSERT":
            continue

        nombre_insert = entity.dxf.name
        capa = entity.dxf.layer
        punto_insert = _punto_a_lista(entity.dxf.insert)
        rotacion = round(float(getattr(entity.dxf, "rotation", 0.0) or 0.0), 3)
        escala_x = round(float(getattr(entity.dxf, "xscale", 1.0) or 1.0), 4)
        escala_y = round(float(getattr(entity.dxf, "yscale", 1.0) or 1.0), 4)
        escala_z = round(float(getattr(entity.dxf, "zscale", 1.0) or 1.0), 4)

        # Obtener componentes anidados de la definición de bloque
        componentes_internos = definiciones.get(nombre_insert, [])

        bloque_apto = {
            "nombre_bloque": nombre_insert,
            "capa": capa,
            "punto_insert": punto_insert,
            "rotacion": rotacion,
            "escala": [escala_x, escala_y, escala_z],
            "es_electrica": _pertenece_a_capa_electrica(capa),
            "definicion_bloque": nombre_insert,
            "componentes_internos": componentes_internos,
            "total_componentes": len(componentes_internos),
            "familia_revit_sugerida": _familia_revit_sugerida(nombre_insert),
        }
        bloques_apartamento.append(bloque_apto)

    # Construir detalle de definiciones de bloque (sin duplicar)
    detalle_definiciones: List[Dict[str, Any]] = []
    for nombre_bdef, entidades in definiciones.items():
        detalle_definiciones.append({
            "nombre_bloque": nombre_bdef,
            "total_entidades": len(entidades),
            "entidades": entidades,
        })

    # Conteo de tipos de componente internos (para el resumen)
    tipos_componentes: Dict[str, int] = {}
    for det in detalle_definiciones:
        for ent in det["entidades"]:
            t = ent["tipo"]
            tipos_componentes[t] = tipos_componentes.get(t, 0) + 1

    salida = {
        "metadatos": {
            "origen_dxf": str(dxf_path),
            "chip": chip,
            "version_dxf": doc.dxfversion,
            "unidades": doc.header.get("$INSUNITS", 6),
        },
        "resumen": {
            "bloques_apartamento_en_modelo": len(bloques_apartamento),
            "definiciones_bloque_distintas": len(detalle_definiciones),
            "total_componentes_internos": sum(d["total_entidades"] for d in detalle_definiciones),
            "tipos_componente": tipos_componentes,
        },
        "bloques_apartamento": bloques_apartamento,
        "definiciones_bloque": detalle_definiciones,
        "mapeo_sugerido_revit": MAPEO_BLOQUES_REVIT,
    }

    return salida


def _extraer_entidad(entity) -> Optional[Dict[str, Any]]:
    """Extrae los datos relevantes de una entidad DXF dentro de un bloque."""
    dxf_type = entity.dxftype()
    capa = getattr(entity.dxf, "layer", "") or ""

    base: Dict[str, Any] = {
        "tipo": dxf_type,
        "capa": capa,
        "es_electrica": _pertenece_a_capa_electrica(capa),
    }

    if dxf_type == "INSERT":
        base.update({
            "nombre_bloque": entity.dxf.name,
            "punto_insert": _punto_a_lista(entity.dxf.insert),
            "rotacion": round(float(getattr(entity.dxf, "rotation", 0.0) or 0.0), 3),
            "escala": [
                round(float(getattr(entity.dxf, "xscale", 1.0) or 1.0), 4),
                round(float(getattr(entity.dxf, "yscale", 1.0) or 1.0), 4),
                round(float(getattr(entity.dxf, "zscale", 1.0) or 1.0), 4),
            ],
            "familia_revit_sugerida": _familia_revit_sugerida(entity.dxf.name),
        })
        return base

    if dxf_type in ("LWPOLYLINE", "POLYLINE"):
        try:
            puntos = [
                _punto_a_lista(p[:3]) for p in entity.get_points()
            ]
        except Exception:
            puntos = []
        base.update({
            "puntos": puntos,
            "cerrada": bool(getattr(entity, "closed", False)),
        })
        return base

    if dxf_type == "LINE":
        base.update({
            "inicio": _punto_a_lista(entity.dxf.start),
            "fin": _punto_a_lista(entity.dxf.end),
        })
        return base

    if dxf_type == "ARC":
        base.update({
            "centro": _punto_a_lista(entity.dxf.center),
            "radio": round(float(entity.dxf.radius), 3),
            "angulo_inicio": round(float(entity.dxf.start_angle), 2),
            "angulo_fin": round(float(entity.dxf.end_angle), 2),
        })
        return base

    if dxf_type == "CIRCLE":
        base.update({
            "centro": _punto_a_lista(entity.dxf.center),
            "radio": round(float(entity.dxf.radius), 3),
        })
        return base

    if dxf_type == "TEXT":
        base.update({
            "texto": entity.dxf.text,
            "punto_insert": _punto_a_lista(entity.dxf.insert),
            "altura": round(float(entity.dxf.height), 3),
        })
        return base

    if dxf_type == "MTEXT":
        base.update({
            "texto": entity.text,
            "punto_insert": _punto_a_lista(entity.dxf.insert),
            "altura": round(float(entity.dxf.char_height), 3),
        })
        return base

    if dxf_type == "POINT":
        base.update({
            "punto": _punto_a_lista(entity.dxf.location),
        })
        return base

    # Entidades no mapeadas: solo registrar tipo y capa
    return base


def _resolver_ruta_salida(json_out: Optional[str], chip: str) -> Path:
    """Resuelve la ruta del JSON de salida contra $REVITELECTRICO_ROOT."""
    if json_out:
        p = Path(json_out)
        if p.is_absolute():
            return p
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        return root / p
    root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
    return root / "data" / f"bloques_anidados_{chip}.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrae bloques anidados de un DXF individual de apartamento."
    )
    parser.add_argument(
        "--dxf-in", type=str, required=True, help="Ruta al DXF individual de apartamento"
    )
    parser.add_argument(
        "--json-out", type=str, default="",
        help="Ruta del JSON de salida (default: data/bloques_anidados_<chip>.json)",
    )
    parser.add_argument(
        "--chip", type=str, default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    dxf_path = Path(args.dxf_in)
    if not dxf_path.exists():
        raise SystemExit(f"El archivo DXF no existe: {dxf_path}")

    salida_path = _resolver_ruta_salida(args.json_out, args.chip)

    resultado = extraer_bloques_anidados(dxf_path, args.chip)

    salida_path.parent.mkdir(parents=True, exist_ok=True)
    with open(salida_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("EXTRACCIÓN DE BLOQUES ANIDADOS COMPLETADA")
    print("Origen DXF: {}".format(resultado['metadatos']['origen_dxf']))
    print("Chip: {}".format(resultado['metadatos']['chip']))
    print("Bloques apartamento en modelo: {}".format(
        resultado['resumen']['bloques_apartamento_en_modelo']))
    print("Definiciones de bloque distintas: {}".format(
        resultado['resumen']['definiciones_bloque_distintas']))
    print("Total componentes internos: {}".format(
        resultado['resumen']['total_componentes_internos']))
    print("Tipos de componente: {}".format(resultado['resumen']['tipos_componente']))
    print("JSON guardado en: {}".format(salida_path))
    print("=" * 60)


if __name__ == "__main__":
    main()

