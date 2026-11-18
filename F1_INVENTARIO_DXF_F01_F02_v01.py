#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F1_INVENTARIO_DXF_F01_F02_v01.py
================================
Procedimiento ESTÁNDAR para generar inventario canónico de dispositivos eléctricos
desde archivos DXF de apartamentos tipo.

Reglas de trazabilidad:
- Nombre canónico: inventario_dispositivos_<TIPO>_v<VERSION>_<YYYYMMDD>_<HHMMSS>.json
- Incluye hash SHA256 del DXF origen para validar frescura contra fecha de modificación del archivo
- Incluye timestamp de generación, versión de reglas aplicadas, y metadatos completos de origen
- Reutiliza config/alturas_tomas_v01.json, config/equivalencias_dxf_revit_v02.json, config/rotaciones_familias_v01.json
- Aplicable a cualquier apartamento tipo (E05-E08, F01-F02, F17-F18, B15-B16, C14, D13)

Uso:
    python F1_INVENTARIO_DXF_F01_F02_v01.py --dxf "Apartamento Tipo F 01.dxf" --tipo "F 01"
    python F1_INVENTARIO_DXF_F01_F02_v01.py --dxf "Apartamento Tipo F 02.dxf" --tipo "F 02"
    python F1_INVENTARIO_DXF_F01_F02_v01.py --dxf "Apartamento Tipo F 01.dxf" --tipo "F 01" --salida-dir data/inventarios
"""

import ezdxf
import json
import hashlib
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ─── Rutas base ──────────────────────────────────────────────────────────────
REVITELECTRICO_ROOT = Path(os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico"))
ARCHIVOS_BASE_DIR = REVITELECTRICO_ROOT / "ArchivosBase"
CONFIG_DIR = REVITELECTRICO_ROOT / "config"
DATA_DIR = REVITELECTRICO_ROOT / "data"
DEFAULT_OUTPUT_DIR = DATA_DIR / "inventarios"

# ─── Configuración de capas eléctricas (DXF) ────────────────────────────────
CAPAS_ELECTRICAS = [
    "ELEC-APPL-TOMAS",
    "ELEC-APPL-ILUM",
    "ELEC-APPL-NETWORD",
    "ELEC-Data-Service",
    "ELEC-CONTROL ILUM",
]

# ─── Cargar configuraciones ──────────────────────────────────────────────────
def cargar_config(ruta: Path, nombre: str) -> dict:
    """Carga un archivo de configuración JSON con manejo de errores."""
    if not ruta.exists():
        raise FileNotFoundError(f"Config no encontrada: {ruta}")
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  ✓ Config cargada: {nombre} v{data.get('version', '?')} ({data.get('fecha', 'sin fecha')})")
    return data


ALTURAS_CONFIG = cargar_config(CONFIG_DIR / "alturas_tomas_v01.json", "alturas_tomas")
EQUIVALENCIAS_CONFIG = cargar_config(CONFIG_DIR / "equivalencias_dxf_revit_v07.json", "equivalencias_dxf_revit")
ROTACIONES_CONFIG = cargar_config(CONFIG_DIR / "rotaciones_familias_v01.json", "rotaciones_familias")

# ─── Utilidades ──────────────────────────────────────────────────────────────
def sha256_file(path: Path) -> str:
    """Calcula SHA256 de un archivo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def normalizar_capa(capa: str) -> str:
    """Normaliza nombre de capa para matching."""
    return capa.strip().upper()


def obtener_altura_dispositivo(nombre_bloque: str, handle: str, x: float, y: float, apartamento: str) -> dict:
    """
    Determina la altura local de montaje aplicando la jerarquía:
    1. Excepción por handle (excepciones_por_handle)
    2. Excepción por apartamento + coordenadas (excepciones_por_apartamento)
    3. Anotación DXF (si existe y no está en ignoradas)
    4. Regla base por tipo de bloque (regla_base_altura_m)
    """
    resultado = {
        "altura_local_m": None,
        "altura_nominal_m": None,
        "origen_altura": "desconocido",
        "excepcion_aplicada": None,
        "conflicto_anotacion": False,
    }

    # 1. Excepción por handle
    exc_handle = ALTURAS_CONFIG.get("excepciones_por_handle", {}).get(handle.upper())
    if exc_handle:
        resultado["altura_local_m"] = exc_handle["altura_m"]
        resultado["altura_nominal_m"] = exc_handle["altura_m"]
        resultado["origen_altura"] = "excepcion_handle"
        resultado["excepcion_aplicada"] = f"handle:{handle}"
        return resultado

    # 2. Excepción por apartamento + coordenadas (con tolerancia)
    exc_apto = ALTURAS_CONFIG.get("excepciones_por_apartamento", {}).get(apartamento.upper().replace(" ", ""), [])
    for exc in exc_apto:
        dx = abs(exc["x"] - x)
        dy = abs(exc["y"] - y)
        if dx <= 0.5 and dy <= 0.5:  # tolerancia 50 cm
            if exc["codigo"] == nombre_bloque or exc["codigo"] == "ALL":
                resultado["altura_local_m"] = exc["altura_m"]
                resultado["altura_nominal_m"] = exc["altura_m"]
                resultado["origen_altura"] = "excepcion_apartamento"
                resultado["excepcion_aplicada"] = f"apto:{apartamento} codigo:{exc['codigo']} pos:({exc['x']},{exc['y']})"
                return resultado

    # 3. Regla base por tipo de bloque
    regla_base = ALTURAS_CONFIG.get("regla_base_altura_m", {})
    if nombre_bloque in regla_base:
        resultado["altura_local_m"] = regla_base[nombre_bloque]
        resultado["altura_nominal_m"] = regla_base[nombre_bloque]
        resultado["origen_altura"] = "regla_base"
        return resultado

    # 4. Fallback genérico
    resultado["altura_local_m"] = 0.3
    resultado["altura_nominal_m"] = 0.3
    resultado["origen_altura"] = "fallback_0.30"
    return resultado


def obtener_mapeo_revit(nombre_bloque: str, capa: str) -> dict:
    """Obtiene familia, tipo y símbolo Revit desde equivalencias."""
    por_bloque = EQUIVALENCIAS_CONFIG.get("por_bloque", {})
    por_capa = EQUIVALENCIAS_CONFIG.get("por_capa", {})
    simbolos = EQUIVALENCIAS_CONFIG.get("simbolo_por_bloque", {})

    # Prioridad: bloque explícito > capa
    familia = por_bloque.get(nombre_bloque) or por_capa.get(normalizar_capa(capa))
    simbolo = simbolos.get(nombre_bloque, "Estandar")

    return {
        "familia_revit": familia,
        "tipo_revit": simbolo,
        "mapeo_fuente": "bloque" if nombre_bloque in por_bloque else ("capa" if normalizar_capa(capa) in por_capa else "ninguno"),
    }


def obtener_delta_rotacion(familia_revit: str) -> float:
    """Obtiene delta de rotación por familia (norma colombiana: placa horizontal)."""
    deltas = ROTACIONES_CONFIG.get("delta_rot_por_familia", {})
    return deltas.get(familia_revit, 0.0)


def extraer_bloques_dxf(ruta_dxf: Path) -> list:
    """Extrae todas las entidades INSERT (bloques) con atributos del DXF."""
    doc = ezdxf.readfile(str(ruta_dxf))
    msp = doc.modelspace()

    bloques = []
    for entity in msp:
        if entity.dxftype() != "INSERT":
            continue

        capa = normalizar_capa(entity.dxf.layer)
        if not any(capa.startswith(pref.upper()) for pref in CAPAS_ELECTRICAS):
            continue

        insert = entity.dxf.insert
        x, y, z = round(float(insert.x), 4), round(float(insert.y), 4), round(float(insert.z), 4)
        rotacion = round(float(entity.dxf.rotation), 2) if hasattr(entity.dxf, "rotation") else 0.0
        nombre_bloque = entity.dxf.name
        handle = entity.dxf.handle if hasattr(entity.dxf, "handle") else "SIN_HANDLE"

        # Extraer atributos del bloque
        atributos = {}
        for attrib in entity.attribs:
            tag = attrib.dxf.tag.strip().upper()
            valor = attrib.dxf.text.strip()
            atributos[tag] = valor

        bloques.append({
            "handle": handle,
            "nombre_bloque": nombre_bloque,
            "capa": capa,
            "x": x,
            "y": y,
            "z": z,
            "rotacion_bloque_grados": rotacion,
            "atributos": atributos,
        })

    return bloques


def generar_inventario_canonico(bloques_dxf: list, dxf_path: Path, dxf_hash: str, dxf_mtime: datetime,
                                 apartamento_tipo: str, nivel_elevacion_m: float = 13.22) -> dict:
    """Genera el inventario canónico completo con trazabilidad."""
    timestamp_gen = datetime.now()
    timestamp_str = timestamp_gen.strftime("%Y%m%d_%H%M%S")
    fecha_iso = timestamp_gen.isoformat()

    dispositivos = []
    stats = defaultdict(int)

    for blk in bloques_dxf:
        handle = blk["handle"]
        nombre_bloque = blk["nombre_bloque"]
        capa = blk["capa"]
        x, y, z = blk["x"], blk["y"], blk["z"]
        rot_bloque = blk["rotacion_bloque_grados"]

        # Altura
        altura_info = obtener_altura_dispositivo(nombre_bloque, handle, x, y, apartamento_tipo)
        altura_local = altura_info["altura_local_m"]
        z_absoluta = round(nivel_elevacion_m + altura_local, 3)

        # Mapeo Revit
        mapeo = obtener_mapeo_revit(nombre_bloque, capa)
        familia = mapeo["familia_revit"]
        simbolo = mapeo["tipo_revit"]

        # Rotación final (bloque + delta familia)
        delta_rot = obtener_delta_rotacion(familia) if familia else 0.0
        rot_final = round((rot_bloque + delta_rot) % 360, 2)

        dispositivo = {
            "handle": handle,
            "nombre_dxf": nombre_bloque,
            "capa_dxf": capa,
            "x": x,
            "y": y,
            "z": z,
            "z_absoluta_m": z_absoluta,
            "rotacion_bloque_grados": rot_bloque,
            "rotacion_final_grados": rot_final,
            "delta_rotacion_familia_grados": delta_rot,
            "altura_local_m": altura_local,
            "altura_nominal_m": altura_info["altura_nominal_m"],
            "origen_altura": altura_info["origen_altura"],
            "excepcion_aplicada": altura_info["excepcion_aplicada"],
            "familia_revit": familia,
            "tipo_revit": simbolo,
            "mapeo_fuente": mapeo["mapeo_fuente"],
            "atributos_dxf": blk["atributos"],
        }

        dispositivos.append(dispositivo)
        stats[altura_info["origen_altura"]] += 1
        if not familia:
            stats["sin_mapeo"] += 1

    # Nombre canónico del archivo
    nombre_base = f"inventario_dispositivos_{apartamento_tipo.replace(' ', '').replace('.', '')}"
    version = ALTURAS_CONFIG.get("version", "1.0")
    archivo_canonico = f"{nombre_base}_v{version}_{timestamp_str}.json"

    inventario = {
        "metadatos": {
            "proyecto": "RE",
            "fase": "F1",
            "tipo_documento": "inventario_dispositivos",
            "version_esquema": "1.0",
            "version_reglas_altura": ALTURAS_CONFIG.get("version"),
            "version_equivalencias": EQUIVALENCIAS_CONFIG.get("version"),
            "version_rotaciones": ROTACIONES_CONFIG.get("version"),
            "fecha_generacion": fecha_iso,
            "timestamp_generacion": timestamp_str,
            "apartamento_tipo": apartamento_tipo,
            "tablero": f"T{apartamento_tipo.split()[1]}" if " " in apartamento_tipo else f"T{apartamento_tipo}",
            "nivel_elevacion_m": nivel_elevacion_m,
            "origen_dxf": {
                "archivo": dxf_path.name,
                "ruta_completa": str(dxf_path),
                "hash_sha256": dxf_hash,
                "fecha_modificacion_dxf": dxf_mtime.isoformat(),
                "tamano_bytes": dxf_path.stat().st_size,
            },
            "estadisticas": {
                "total_dispositivos": len(dispositivos),
                "por_origen_altura": dict(stats),
                "con_mapeo_revit": sum(1 for d in dispositivos if d["familia_revit"]),
                "sin_mapeo_revit": sum(1 for d in dispositivos if not d["familia_revit"]),
            },
            "archivo_canonico": archivo_canonico,
        },
        "dispositivos": dispositivos,
    }

    return inventario, archivo_canonico


def validar_frescura_dxf(inventario: dict, dxf_path: Path) -> dict:
    """Valida si el inventario está fresco respecto al DXF actual."""
    actual_hash = sha256_file(dxf_path)
    actual_mtime = datetime.fromtimestamp(dxf_path.stat().st_mtime)

    inventario_hash = inventario["metadatos"]["origen_dxf"]["hash_sha256"]
    inventario_mtime_str = inventario["metadatos"]["origen_dxf"]["fecha_modificacion_dxf"]
    inventario_mtime = datetime.fromisoformat(inventario_mtime_str)

    hash_coincide = (actual_hash == inventario_hash)
    mtime_diferencia = abs((actual_mtime - inventario_mtime).total_seconds())

    return {
        "dxf_actual_hash": actual_hash,
        "dxf_actual_mtime": actual_mtime.isoformat(),
        "inventario_hash": inventario_hash,
        "inventario_mtime": inventario_mtime_str,
        "hash_coincide": hash_coincide,
        "diferencia_segundos": mtime_diferencia,
        "fresco": hash_coincide and mtime_diferencia < 60,  # menos de 1 min = fresco
        "recomendacion": "USAR_INVENTARIO" if hash_coincide else "REGENERAR_INVENTARIO",
    }


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Genera inventario canónico de dispositivos desde DXF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python F1_INVENTARIO_DXF_F01_F02_v01.py --dxf "Apartamento Tipo F 01.dxf" --tipo "F 01"
  python F1_INVENTARIO_DXF_F01_F02_v01.py --dxf "Apartamento Tipo F 02.dxf" --tipo "F 02" --salida-dir data/inventarios
  python F1_INVENTARIO_DXF_F01_F02_v01.py --validar data/inventarios/inventario_dispositivos_F01_v1.0_20261117_143000.json
        """
    )
    parser.add_argument("--dxf", help="Nombre del archivo DXF en ArchivosBase/")
    parser.add_argument("--tipo", help="Tipo de apartamento (ej: 'F 01', 'F 02', 'E 06')")
    parser.add_argument("--salida-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directorio de salida")
    parser.add_argument("--nivel-elevacion", type=float, default=13.22, help="Elevación del nivel en metros")
    parser.add_argument("--validar", help="Validar frescura de un inventario existente contra su DXF origen")
    parser.add_argument("--listar", action="store_true", help="Listar DXF disponibles en ArchivosBase/")

    args = parser.parse_args()

    if args.listar:
        print("\nDXF disponibles en ArchivosBase/:")
        for f in sorted(ARCHIVOS_BASE_DIR.glob("Apartamento Tipo *.dxf")):
            stat = f.stat()
            print(f"  {f.name}  ({stat.st_size:,} bytes, modificado: {datetime.fromtimestamp(stat.st_mtime).isoformat()})")
        return

    if args.validar:
        # Validar inventario existente
        with open(args.validar, "r", encoding="utf-8") as f:
            inv = json.load(f)
        dxf_name = inv["metadatos"]["origen_dxf"]["archivo"]
        dxf_path = ARCHIVOS_BASE_DIR / dxf_name
        if not dxf_path.exists():
            print(f"✗ DXF origen no encontrado: {dxf_path}")
            return
        resultado = validar_frescura_dxf(inv, dxf_path)
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        if resultado["fresco"]:
            print("\n✓ INVENTARIO FRESCO — se puede usar directamente")
        else:
            print(f"\n⚠ INVENTARIO DESACTUALIZADO — {resultado['recomendacion']}")
        return

    if not args.dxf or not args.tipo:
        parser.error("--dxf y --tipo son requeridos (o usa --validar / --listar)")

    dxf_path = ARCHIVOS_BASE_DIR / args.dxf
    if not dxf_path.exists():
        print(f"✗ DXF no encontrado: {dxf_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"GENERANDO INVENTARIO CANÓNICO")
    print(f"{'='*60}")
    print(f"DXF origen:     {dxf_path.name}")
    print(f"Apartamento:    {args.tipo}")
    print(f"Nivel elevación: {args.nivel_elevacion} m")

    # Hash y mtime del DXF
    dxf_hash = sha256_file(dxf_path)
    dxf_mtime = datetime.fromtimestamp(dxf_path.stat().st_mtime)
    print(f"DXF SHA256:     {dxf_hash[:16]}... ({dxf_hash})")
    print(f"DXF modificado: {dxf_mtime.isoformat()}")

    # Extraer bloques
    print(f"\nExtrayendo bloques del DXF...")
    bloques = extraer_bloques_dxf(dxf_path)
    print(f"  Bloques eléctricos encontrados: {len(bloques)}")

    # Generar inventario
    print(f"\nGenerando inventario canónico...")
    inventario, archivo_canonico = generar_inventario_canonico(
        bloques, dxf_path, dxf_hash, dxf_mtime, args.tipo, args.nivel_elevacion
    )

    # Guardar
    salida_dir = Path(args.salida_dir)
    salida_dir.mkdir(parents=True, exist_ok=True)
    salida_path = salida_dir / archivo_canonico

    with open(salida_path, "w", encoding="utf-8") as f:
        json.dump(inventario, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✓ INVENTARIO GENERADO")
    print(f"{'='*60}")
    print(f"Archivo:        {salida_path}")
    print(f"Dispositivos:   {inventario['metadatos']['estadisticas']['total_dispositivos']}")
    print(f"Con mapeo:      {inventario['metadatos']['estadisticas']['con_mapeo_revit']}")
    print(f"Sin mapeo:      {inventario['metadatos']['estadisticas']['sin_mapeo_revit']}")
    print(f"Por altura:     {dict(inventario['metadatos']['estadisticas']['por_origen_altura'])}")
    print(f"\nNombre canónico: {archivo_canonico}")
    print(f"  → Incluye: versión reglas, timestamp, hash DXF, apartamento, tablero")
    print(f"\nPara validar frescura futura:")
    print(f"  python {Path(__file__).name} --validar {salida_path}")


if __name__ == "__main__":
    main()