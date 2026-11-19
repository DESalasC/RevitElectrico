# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_MAESTRO_GLOBAL v4 - TODOS LOS APARTAMENTOS (F, E, D, C, B)
Extrae TODAS las instancias de apartamento del DXF maestro para Piso 5
y genera JSON maestro global con coordenadas globales directas.
"""

import ezdxf, json, os, math
from collections import defaultdict

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUTPUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

# Equivalencias bloque DXF -> familia Revit (CON LUMINARIAS)
EQUIVALENCIAS = {
    # Tomas
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    # Interruptores
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "ELEC-I-S-2-5A": ("M_Interruptores", "Doble"),
    "ELEC-F-CONTROL": ("M_Interruptores", "Control"),
    # Campana/Timbre
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    # Ventilación
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    # LUMINARIAS
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    # Comunicaciones
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-NET-PAU": ("M_Comunicaciones", "Datos"),
    # Extintor/EA
    "ELEC-EXT": ("EA", "Extintor"),
}

EQUIV_KEYS = list(EQUIVALENCIAS.keys())

# Mapeo tipo apartamento -> prefijo tablero
APTO_TO_PANEL_PREFIX = {
    "F": "TF",
    "E": "TE",
    "D": "TD",
    "C": "TC",
    "B": "TB",
}

# Coordenadas LOCALES del CP (Consolidation_Point) por DEFINICIÓN DE BLOQUE (metros)
# Basado en posición real de ELEC-NET-PAU dentro de cada definición de bloque
# CP global = INSERT_apartamento_master + ELEC-NET-PAU_local_definicion
# Medido directamente en STM-T5-P5_bloques_electricos.dxf
CP_LOCAL_BY_BLOCK_DEF = {
    "Apartamento Tipo F 02": (-2.34, 2.84),
    "Apartamento Tipo F 01": (-2.30, -2.84),
    "Apartamento Tipo F 02a": (-2.34, 2.84),
    "Apartamento Tipo F 02b": (-2.34, 2.84),
    "Apartamento Tipo F 01a": (-2.30, -2.84),
    "Apartamento Tipo F 01b": (-2.30, -2.84),
    "Apartamentos Tipo F 18": (-2.34, 2.84),
    "Apartamentos Tipo F 18a": (-2.34, 2.84),
    "Apartamento Tipo F 17": (-2.34, 2.84),
    "Apartamento Tipo F 17a": (-2.34, 2.84),
    "Apartamento Tipo E 06": (2.82, 2.02),
    "Apartamento Tipo E 07": (-2.27, -2.02),
    "Apartamento Tipo E 07a": (-2.27, -2.02),
    "Apartamento Tipo E 08": (-3.11, 1.94),
    "Apartamento Tipo E 08a": (-2.86, 1.94),
    "ELEC-Apartamento Tipo D 13": (3.84, 2.02),
    "ELEC-Apartamento Tipo C 14": (0.84, 0.26),
    "Apartamento Tipo B 16": (-2.05, 2.00),
    "Apartamento Tipo B 15": (-2.13, -2.00),
}

MM_TO_FT = 1.0 / 304.8
M_TO_FT = 3.280839895

def parse_apto_type_number(block_name):
    """Extrae tipo y número de apartamento del nombre del bloque.
    Ej: 'Apartamento Tipo F 01' -> ('F', '01')
        'Apartamentos Tipo F 18' -> ('F', '18')
        'ELEC-Apartamento Tipo D 13' -> ('D', '13')
        'Apartamento Tipo B 15' -> ('B', '15')
    """
    import re
    # Patrones: "Tipo X NN" o "Tipo X NN" con s al final
    m = re.search(r'[Tt]ipo\s+([A-Z])\s*(\d+)', block_name)
    if m:
        return m.group(1), m.group(2).zfill(2)
    return None, None

def get_panel_name(block_name):
    """Genera nombre del tablero basado en tipo y número de apartamento."""
    apto_type, apto_num = parse_apto_type_number(block_name)
    if apto_type and apto_num:
        prefix = APTO_TO_PANEL_PREFIX.get(apto_type, "T" + apto_type)
        return prefix + " " + apto_num
    return None

def explore_block_devices(block, doc, prefix=""):
    """Extrae dispositivos conocidos recursivamente de una definición de bloque"""
    devices = []
    for e in block:
        if e.dxftype() == "INSERT":
            block_ref = doc.blocks.get(e.dxf.name)
            if block_ref:
                name = e.dxf.name
                x_local = e.dxf.insert.x
                y_local = e.dxf.insert.y
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
                
                # Recursivo
                sub_devices = explore_block_devices(block_ref, doc, prefix + name + "->")
                devices.extend(sub_devices)
    return devices

def main():
    if not os.path.exists(MASTER_DXF):
        print("[ERROR] No existe: " + MASTER_DXF)
        return
    
    doc = ezdxf.readfile(MASTER_DXF)
    msp = doc.modelspace()
    
    # 1. Encontrar TODAS las instancias de apartamentos en modelspace
    apto_instances = {}  # key: "F01", "E07", etc. -> (x_mm, y_mm, block_def_name, panel_name)
    
    for e in msp:
        if e.dxftype() == "INSERT":
            name = e.dxf.name
            # Filtrar solo bloques de apartamento (no muebles, sanitarios, etc.)
            if ("Apartamento" in name or "Apartamentos" in name or "ELEC-Apartamento" in name) and "Tipo" in name:
                apto_type, apto_num = parse_apto_type_number(name)
                if apto_type and apto_num:
                    key = apto_type + apto_num  # F01, E07, D13, etc.
                    panel_name = get_panel_name(name)
                    apto_instances[key] = (
                        e.dxf.insert.x, 
                        e.dxf.insert.y, 
                        name,  # nombre de la definición de bloque
                        panel_name
                    )
                    print("Instancia: {} -> Key={} Panel={} @ ({:.1f}, {:.1f})mm".format(
                        name, key, panel_name, e.dxf.insert.x, e.dxf.insert.y))
    
    print("\nTotal instancias de apartamento: {}".format(len(apto_instances)))
    
    # 2. Extraer dispositivos de CADA definición de bloque única
    block_devices_cache = {}
    for key, (x_mm, y_mm, block_def_name, panel_name) in apto_instances.items():
        if block_def_name not in block_devices_cache:
            if block_def_name in doc.blocks:
                block = doc.blocks[block_def_name]
                devices = explore_block_devices(block, doc)
                block_devices_cache[block_def_name] = devices
                print("\n{} - Dispositivos en definición '{}': {}".format(key, block_def_name, len(devices)))
            else:
                print("[WARN] Definición de bloque no encontrada: {}".format(block_def_name))
                block_devices_cache[block_def_name] = []
    
    # 3. Combinar: coordenadas globales = apartamento (mm->ft) + dispositivo (m->ft)
    result = {"apartamentos": {}}
    
    for key, (apto_x_mm, apto_y_mm, block_def_name, panel_name) in apto_instances.items():
        apto_x_ft = apto_x_mm * MM_TO_FT
        apto_y_ft = apto_y_mm * MM_TO_FT
        
        devices_out = []
        for d in block_devices_cache.get(block_def_name, []):
            x_global_ft = apto_x_ft + d["x_local_m"] * M_TO_FT
            y_global_ft = apto_y_ft + d["y_local_m"] * M_TO_FT
            
            # Mark para Identity Data: "F01|TF 01" o "E07|TE 07"
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
        
        # AÑADIR CP (Consolidation_Point) - coordenadas locales por definición de bloque
        cp_local_m = CP_LOCAL_BY_BLOCK_DEF.get(block_def_name, (-2.34, 2.84))
        cp_x_local_m, cp_y_local_m = cp_local_m
        cp_x_global_ft = apto_x_ft + cp_x_local_m * M_TO_FT
        cp_y_global_ft = apto_y_ft + cp_y_local_m * M_TO_FT
        
        devices_out.append({
            "handle": "",
            "name": "ELEC-CONSOLIDATION",
            "x": cp_x_global_ft,
            "y": cp_y_global_ft,
            "rotation": 0,
            "familia_revit": "Consolidation_Point",
            "tipo_revit": "CPB12BL",
            "apto_key": key,
            "apto_type": key[0],
            "apto_num": key[1:],
            "panel_name": panel_name,
            "mark": key + "|" + panel_name + "|CP_01",
        })
        
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
        print("\n{} - Dispositivos globales: {} (Panel: {})".format(key, len(devices_out), panel_name))
    
    # 4. Guardar JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("\n[OK] Guardado: " + OUTPUT_JSON)
    
    # Resumen por tipo
    print("\n=== RESUMEN POR TIPO DE APARTAMENTO ===")
    tipo_counts = defaultdict(int)
    tipo_devices = defaultdict(lambda: defaultdict(int))
    for key, data in result["apartamentos"].items():
        tipo = key[0]
        tipo_counts[tipo] += 1
        for d in data["devices"]:
            ft = d["familia_revit"] + "/" + d["tipo_revit"]
            tipo_devices[tipo][ft] += 1
    
    for tipo in sorted(tipo_counts.keys()):
        print("\nTipo {}: {} apartamentos".format(tipo, tipo_counts[tipo]))
        for ft, c in sorted(tipo_devices[tipo].items()):
            print("  {}: {}".format(ft, c))
    
    total_devices = sum(len(d["devices"]) for d in result["apartamentos"].values())
    print("\nTOTAL DISPOSITIVOS: {}".format(total_devices))
    print("APARTAMENTOS: {}".format(len(result["apartamentos"])))

if __name__ == "__main__":
    main()