# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_MAESTRO_GLOBAL v5 - DIRECTO DESDE DXF MAESTRO
Extrae TODOS los dispositivos usando coordenadas GLOBALES directas del DXF maestro.
El DXF maestro fue exportado del .rvt: modelspace = coordenadas globales .rvt.
"""

import ezdxf, json, os, math
from collections import defaultdict

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUTPUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

# Equivalencias bloque DXF -> familia Revit
EQUIVALENCIAS = {
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "ELEC-I-S-2-5A": ("M_Interruptores", "Doble"),
    "ELEC-F-CONTROL": ("M_Interruptores", "Control"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-NET-PAU": ("M_Comunicaciones", "Datos"),
    "ELEC-EXT": ("EA", "Extintor"),
}

EQUIV_KEYS = list(EQUIVALENCIAS.keys())

# Mapeo tipo apartamento -> prefijo tablero
APTO_TO_PANEL_PREFIX = {
    "F": "TF", "E": "TE", "D": "TD", "C": "TC", "B": "TB",
}

MM_TO_FT = 1.0 / 304.8
M_TO_FT = 3.280839895

def parse_apto_type_number(block_name):
    """Extrae tipo y número del nombre del bloque."""
    import re
    m = re.search(r'[Tt]ipo\s+([A-Z])\s*(\d+)', block_name)
    if m:
        return m.group(1), m.group(2).zfill(2)
    return None, None

def get_panel_name(block_name):
    apto_type, apto_num = parse_apto_type_number(block_name)
    if apto_type and apto_num:
        prefix = APTO_TO_PANEL_PREFIX.get(apto_type, "T" + apto_type)
        return prefix + " " + apto_num
    return None

def explore_block_devices(block, doc, x_local_offset=0, y_local_offset=0):
    """Extrae dispositivos recursivamente de una definición de bloque.
    Devuelve lista de dicts con coordenadas LOCALES al bloque raíz."""
    devices = []
    for e in block:
        if e.dxftype() == "INSERT":
            name = e.dxf.name
            x_local = e.dxf.insert.x + x_local_offset
            y_local = e.dxf.insert.y + y_local_offset
            rot = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
            
            # Buscar en equivalencias
            fam_typ = None
            matched_key = None
            for key in EQUIV_KEYS:
                if key in name:
                    fam_typ = EQUIVALENCIAS[key]
                    matched_key = key
                    break
            
            if fam_typ:
                devices.append({
                    "block_name": name,
                    "matched_key": matched_key,
                    "x_local_m": x_local,
                    "y_local_m": y_local,
                    "rotation": rot,
                    "familia_revit": fam_typ[0],
                    "tipo_revit": fam_typ[1],
                })
            
            # Recursivo en bloque anidado
            block_ref = doc.blocks.get(name)
            if block_ref:
                sub_devices = explore_block_devices(block_ref, doc, x_local, y_local)
                devices.extend(sub_devices)
    return devices

def main():
    if not os.path.exists(MASTER_DXF):
        print("[ERROR] No existe: " + MASTER_DXF)
        return
    
    doc = ezdxf.readfile(MASTER_DXF)
    msp = doc.modelspace()
    
    # 1. Encontrar TODAS las instancias de apartamento en modelspace (coordenadas GLOBALES .rvt)
    apto_instances = {}  # key -> (x_mm, y_mm, block_def_name, panel_name)
    
    for e in msp:
        if e.dxftype() == "INSERT":
            name = e.dxf.name
            if ("Apartamento" in name or "Apartamentos" in name or "ELEC-Apartamento" in name) and "Tipo" in name:
                apto_type, apto_num = parse_apto_type_number(name)
                if apto_type and apto_num:
                    key = apto_type + apto_num  # F01, E07, etc.
                    panel_name = get_panel_name(name)
                    apto_instances[key] = (
                        e.dxf.insert.x, 
                        e.dxf.insert.y, 
                        name,  # nombre de la definición de bloque
                        panel_name
                    )
                    print("Instancia GLOBAL: {} -> Key={} Panel={} @ ({:.1f}, {:.1f})mm".format(
                        name, key, panel_name, e.dxf.insert.x, e.dxf.insert.y))
    
    print("\nTotal instancias de apartamento: {}".format(len(apto_instances)))
    
    # 2. Extraer dispositivos de CADA definición de bloque única (coordenadas LOCALES)
    block_devices_cache = {}
    for key, (x_mm, y_mm, block_def_name, panel_name) in apto_instances.items():
        if block_def_name not in block_devices_cache:
            if block_def_name in doc.blocks:
                block = doc.blocks[block_def_name]
                devices = explore_block_devices(block, doc)
                block_devices_cache[block_def_name] = devices
                print("\n{} - Dispositivos LOCALES en '{}': {}".format(key, block_def_name, len(devices)))
            else:
                print("[WARN] Definición no encontrada: {}".format(block_def_name))
                block_devices_cache[block_def_name] = []
    
    # 3. Combinar: GLOBAL = APTO_GLOBAL + DISPOSITIVO_LOCAL
    result = {"apartamentos": {}}
    
    for key, (apto_x_mm, apto_y_mm, block_def_name, panel_name) in apto_instances.items():
        apto_x_ft = apto_x_mm * MM_TO_FT
        apto_y_ft = apto_y_mm * MM_TO_FT
        
        devices_out = []
        for d in block_devices_cache.get(block_def_name, []):
            # Coordenada global = apartamento global + dispositivo local (metros -> ft)
            x_global_ft = apto_x_ft + (d["x_local_m"] * M_TO_FT)
            y_global_ft = apto_y_ft + (d["y_local_m"] * M_TO_FT)
            
            mark_value = key + "|" + panel_name if panel_name else key
            
            devices_out.append({
                "handle": "",
                "name": d["block_name"],
                "x": x_global_ft,
                "y": y_global_ft,
                "rotation": d["rotation"],
                "familia_revit": d["familia_revit"],
                "tipo_revit": d["tipo_revit"],
                "apto_key": key,
                "apto_type": key[0],
                "apto_num": key[1:],
                "panel_name": panel_name,
                "mark": mark_value,
            })
        
        # AGREGAR CP: usar ELEC-NET-PAU local de esta definición como ancla
        # Buscar ELEC-NET-PAU en los dispositivos locales de este bloque
        cp_local = None
        for d in block_devices_cache.get(block_def_name, []):
            if d["matched_key"] == "ELEC-NET-PAU":
                cp_local = (d["x_local_m"], d["y_local_m"])
                break
        
        if cp_local:
            cp_x_ft = apto_x_ft + (cp_local[0] * M_TO_FT)
            cp_y_ft = apto_y_ft + (cp_local[1] * M_TO_FT)
            devices_out.append({
                "handle": "",
                "name": "ELEC-CONSOLIDATION",
                "x": cp_x_ft,
                "y": cp_y_ft,
                "rotation": 0,
                "familia_revit": "Consolidation_Point",
                "tipo_revit": "CPB12BL",
                "apto_key": key,
                "apto_type": key[0],
                "apto_num": key[1:],
                "panel_name": panel_name,
                "mark": key + "|" + panel_name + "|CP_01",
            })
            print("  CP agregado para {} @ ({:.2f}, {:.2f})ft".format(key, cp_x_ft, cp_y_ft))
        else:
            print("  [WARN] No hay ELEC-NET-PAU en {} para derivar CP".format(block_def_name))
        
        result["apartamentos"][key] = {
            "devices": devices_out,
            "walls": [],
            "panels": [],
            "panel_name": panel_name,
            "apto_type": key[0],
            "apto_num": key[1:],
            "base_x_ft": apto_x_ft,
            "base_y_ft": apto_y_ft,
        }
        print("\n{} - Dispositivos GLOBALES: {} (Panel: {})".format(key, len(devices_out), panel_name))
    
    # 4. Guardar JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("\n[OK] Guardado: " + OUTPUT_JSON)
    
    # Resumen
    print("\n=== RESUMEN ===")
    for key, data in result["apartamentos"].items():
        print("  {}: {} dispositivos".format(key, len(data["devices"])))

if __name__ == "__main__":
    main()