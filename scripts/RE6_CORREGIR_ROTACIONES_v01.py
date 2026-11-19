#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =====================================================================
# RE6_CORREGIR_ROTACIONES_v01.py  |  SCRIPT_ID = COR-ROT  |  VERSION 1.0.0
# Lee el oraculo de orientacion E06, actualiza config/rotaciones_familias_v01.json
# y propaga la correccion a inventarios F01/F02.
# =====================================================================
# USO: python RE6_CORREGIR_ROTACIONES_v01.py
# =====================================================================

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------
ROOT = Path(r"D:\Work\PROJECTS\RevitElectrico")
ORACULO_PATH = ROOT / "data" / "oraculo_orientacion_E06_v01.json"
ROT_CONFIG_PATH = ROOT / "config" / "rotaciones_familias_v01.json"
F01_INV_DIR = ROOT / "data" / "inventarios"
F02_INV_DIR = ROOT / "data" / "inventarios"

# ---------------------------------------------------------------------
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------
def analyze_oraculo(oraculo):
    """Extrae el delta recomendado para M_Comunicaciones | Datos"""
    firmas = oraculo.get("firmas_por_familia_tipo", {})

    target_key = "M_Comunicaciones | Datos"
    if target_key not in firmas:
        print("[ERROR] No se encontro 'M_Comunicaciones | Datos' en el oraculo")
        return None

    data = firmas[target_key]
    delta_mode = data.get("delta_moda_grados")
    delta_avg = data.get("delta_promedio_grados")
    bbox = data.get("bbox_tipico_mm")

    print("\n>>> ANÁLISIS ORÁCULO: M_Comunicaciones | Datos <<<")
    print("  Instancias: {}".format(data["n_instancias"]))
    print("  Delta moda: {}".format(delta_mode))
    print("  Delta promedio: {}".format(delta_avg))
    print("  BBox típico (mm): {}".format(bbox))

    # Analisis de instancias individuales
    for inst in data.get("instancias", []):
        h = inst.get("handle_dxf")
        delta = inst.get("delta_dxf_vs_real")
        rot_loc = inst.get("rotacion_location_deg")
        rot_dxf = inst.get("rotacion_dxf_grados")
        ang_host = inst.get("angulo_relativo_host_deg")
        print("    Handle {:>4}  rot_loc={:>6}  rot_dxf={:>6}  delta={:>6}  ang_host={}".format(
            h, rot_loc, rot_dxf, delta, ang_host))

    # El delta que hay que poner en config es el que hace que:
    # rotacion_final = rotacion_bloque_dxf + delta_familia
    # coincida con la orientacion REAL medida en Revit (oraculo)
    #
    # En el inventario actual F01/F02:
    #   rotacion_final_grados = rotacion_bloque_grados + delta_rotacion_familia_grados
    #   donde delta_rotacion_familia_grados = 0.0 para M_Comunicaciones
    #
    # El oraculo nos dice que la rotacion REAL en Revit (location.Rotation) difiere
    # de rotacion_dxf por delta_dxf_vs_real.
    #
    # Pero OJO: para familias face-based, la rotacion en Revit HEREDA del host.
    # El delta de familia solo aplica cuando NO hay host.
    # En E06, las tomas de datos ESTAN hosteadas a muros.
    #
    # La regla en rotaciones_familias_v01.json dice:
    #   "Rotación: si la familia es hosted, se hereda del host. El delta por familia
    #    solo se aplica cuando no hay host; en familias hosted el delta esperado es 0
    #    y sirve para verificar, no para corregir."
    #
    # PERO el problema detectado es que 7 de 10 tomas de datos en E06 estan "volteadas"
    # visualmente. Esto significa que la ORIENTACION DE LA PLACA (bbox largo) esta
    # invertida respecto a lo esperado.
    #
    # La solucion: el delta de familia debe compensar la orientacion intrinseca de
    # la familia (como se hizo con M_Toma doble: +90 porque la familia trae la placa vertical).
    #
    # Si M_Comunicaciones trae la placa en orientacion "equivocada" respecto al
    # bloque DXF, el delta debe ser 180 (para voltear) o 90 (para rotar 90).
    #
    # Vamos a usar el delta_moda del oraculo como delta recomendado.
    # Pero normalizado: si delta_moda ~ 180 -> delta_familia = 180
    #                    si delta_moda ~ 90  -> delta_familia = 90
    #                    si delta_moda ~ -90 -> delta_familia = -90 (o 270)

    if delta_mode is None:
        print("[ERROR] No hay delta_moda calculable")
        return None

    # Normalizar delta_mode a [0, 360)
    dm = delta_mode % 360
    if dm > 180:
        dm -= 360

    # Determinar delta_familia recomendado
    # Si el bbox muestra que la familia esta "volteada" (eje largo en Z para placa horizontal)
    # o girada 90/180 respecto a lo que el bloque DXF espera.
    if abs(dm - 180) < 30:
        delta_familia = 180.0
        interpretacion = "VOLTEADA_180"
    elif abs(abs(dm) - 90) < 30:
        delta_familia = 90.0 if dm > 0 else -90.0
        interpretacion = "ROTADA_90"
    elif abs(dm) < 15:
        delta_familia = 0.0
        interpretacion = "OK"
    else:
        delta_familia = dm
        interpretacion = "OTRA_{}".format(int(dm))

    print("\n>>> DELTA FAMILIA RECOMENDADO: {:.1f}° ({})".format(delta_familia, interpretacion))

    return {
        "familia": "M_Comunicaciones",
        "tipo": "Datos",
        "delta_familia_grados": delta_familia,
        "interpretacion": interpretacion,
        "delta_moda_oraculo": delta_mode,
        "delta_promedio_oraculo": delta_avg,
        "bbox_tipico_mm": bbox
    }

# ---------------------------------------------------------------------
def update_rot_config(config, recommendation):
    """Actualiza config/rotaciones_familias_v01.json"""
    print("\n>>> ACTUALIZANDO config/rotaciones_familias_v01.json <<<")

    # Agregar/actualizar delta_rot_por_familia
    if "delta_rot_por_familia" not in config:
        config["delta_rot_por_familia"] = {}

    old_delta = config["delta_rot_por_familia"].get("M_Comunicaciones")
    new_delta = recommendation["delta_familia_grados"]
    config["delta_rot_por_familia"]["M_Comunicaciones"] = new_delta

    # Actualizar familias_no_afectadas -> quitar M_Comunicaciones de pendientes
    if "familias_no_afectadas" in config:
        if "M_Comunicaciones" in config["familias_no_afectadas"]:
            del config["familias_no_afectadas"]["M_Comunicaciones"]

    # Agregar evidencia medida
    if "evidencia_medida" not in config:
        config["evidencia_medida"] = {}

    config["evidencia_medida"]["M_Comunicaciones"] = {
        "tipo": "Datos",
        "fuente": "oraculo_orientacion_E06_v01",
        "delta_moda_grados": recommendation["delta_moda_oraculo"],
        "delta_promedio_grados": recommendation["delta_promedio_oraculo"],
        "bbox_tipico_mm": recommendation["bbox_tipico_mm"],
        "interpretacion": recommendation["interpretacion"],
        "fecha": datetime.now().isoformat()
    }

    # Actualizar version y fecha
    config["version"] = "1.1"
    config["fecha"] = datetime.now().strftime("%Y-%m-%d")

    print("  M_Comunicaciones: {} -> {}".format(old_delta, new_delta))
    return config

# ---------------------------------------------------------------------
def update_inventario(inv_path, new_delta):
    """Actualiza delta_rotacion_familia_grados en un inventario F01/F02"""
    inv = load_json(inv_path)
    updated = 0
    for disp in inv.get("dispositivos", []):
        if disp.get("familia_revit") == "M_Comunicaciones" and disp.get("tipo_revit") == "Datos":
            old = disp.get("delta_rotacion_familia_grados", 0.0)
            disp["delta_rotacion_familia_grados"] = new_delta
            # Recalcular rotacion_final_grados
            rot_bloque = disp.get("rotacion_bloque_grados", 0.0)
            disp["rotacion_final_grados"] = (rot_bloque + new_delta) % 360.0
            updated += 1
            print("    {}: delta {} -> {}, rot_final {}".format(
                disp.get("handle"), old, new_delta, disp["rotacion_final_grados"]))

    # Actualizar metadata
    if "metadatos" in inv:
        inv["metadatos"]["version_rotaciones"] = "1.1"
        inv["metadatos"]["fecha_actualizacion_rotaciones"] = datetime.now().isoformat()

    save_json(inv_path, inv)
    return updated

# ---------------------------------------------------------------------
def main():
    print("=" * 78)
    print("RE6_CORREGIR_ROTACIONES_v01")
    print("=" * 78)

    # 1. Cargar oraculo
    if not ORACULO_PATH.exists():
        print("[ERROR] No existe oraculo: {}".format(ORACULO_PATH))
        print("      Ejecuta primero RE6_ORACULO_ORIENTACION_E06_v01.py en pyRevit")
        return 1

    oraculo = load_json(ORACULO_PATH)
    recommendation = analyze_oraculo(oraculo)
    if recommendation is None:
        return 1

    # 2. Actualizar config
    config = load_json(ROT_CONFIG_PATH)
    config = update_rot_config(config, recommendation)
    save_json(ROT_CONFIG_PATH, config)
    print("  Guardado: {}".format(ROT_CONFIG_PATH))

    # 3. Propagar a inventarios F01/F02 (ultimas versiones)
    new_delta = recommendation["delta_familia_grados"]

    # Buscar ultimos inventarios F01 y F02
    f01_files = sorted(F01_INV_DIR.glob("inventario_dispositivos_F01_v*.json"))
    f02_files = sorted(F02_INV_DIR.glob("inventario_dispositivos_F02_v*.json"))

    if not f01_files:
        print("[WARN] No se encontraron inventarios F01")
    else:
        latest_f01 = f01_files[-1]
        print("\n>>> ACTUALIZANDO F01: {} <<<".format(latest_f01.name))
        n = update_inventario(latest_f01, new_delta)
        print("  Dispositivos actualizados: {}".format(n))

    if not f02_files:
        print("[WARN] No se encontraron inventarios F02")
    else:
        latest_f02 = f02_files[-1]
        print("\n>>> ACTUALIZANDO F02: {} <<<".format(latest_f02.name))
        n = update_inventario(latest_f02, new_delta)
        print("  Dispositivos actualizados: {}".format(n))

    print("\n" + "=" * 78)
    print("COMPLETADO")
    print("=" * 78)
    return 0

if __name__ == "__main__":
    sys.exit(main())