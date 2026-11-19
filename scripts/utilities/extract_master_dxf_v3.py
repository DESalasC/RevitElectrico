# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_MAESTRO_GLOBAL v3 - Incluye luminarias (Bala Stil Led)
"""

import ezdxf, json, os, math
from collections import defaultdict

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUTPUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global.json"

# Equivalencias bloque DXF -> familia Revit (ACTUALIZADO CON LUMINARIAS)
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

# Claves para búsqueda rápida
EQUIV_KEYS = list(EQUIVALENCIAS.keys())

MM_TO_FT = 1.0 / 304.8
M_TO_FT = 3.280839895

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
                
                # Buscar en equivalencias (cualquier clave contenida en el nombre)
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
    
    # 1. Encontrar instancias de apartamentos Tipo F 01 y 02 en modelspace
    apto_instances = {}
    for e in msp:
        if e.dxftype() == "INSERT":
            name = e.dxf.name
            if name == "Apartamento Tipo F 01":
                apto_instances["F01"] = (e.dxf.insert.x, e.dxf.insert.y)
            elif name == "Apartamento Tipo F 02":
                apto_instances["F02"] = (e.dxf.insert.x, e.dxf.insert.y)
    
    print("Instancias de apartamento encontradas:")
    for apto, (x_mm, y_mm) in apto_instances.items():
        print("  {}: X={:.1f}mm Y={:.1f}mm -> X={:.3f}ft Y={:.3f}ft".format(
            apto, x_mm, y_mm, x_mm * MM_TO_FT, y_mm * MM_TO_FT))
    
    # 2. Extraer dispositivos de las definiciones de bloque
    block_devices = {}
    for apto, block_name in [("F01", "Apartamento Tipo F 01"), ("F02", "Apartamento Tipo F 02")]:
        if block_name in doc.blocks:
            block = doc.blocks[block_name]
            devices = explore_block_devices(block, doc)
            block_devices[apto] = devices
            print("\n{} - Dispositivos en definición de bloque: {}".format(apto, len(devices)))
            for d in devices:
                print("  {} @ ({:.2f}, {:.2f})m rot={:.1f} -> {}/{} (key: {})".format(
                    d["block_name"], d["x_local_m"], d["y_local_m"], d["rotation"],
                    d["familia_revit"], d["tipo_revit"], d["matched_key"]))
        else:
            print("[ERROR] Bloque {} no encontrado".format(block_name))
            block_devices[apto] = []
    
    # 3. Combinar: coordenadas globales = apartamento (mm->ft) + dispositivo (m->ft)
    result = {"apartamentos": {}}
    for apto in ["F01", "F02"]:
        if apto not in apto_instances:
            print("[WARN] No hay instancia de {} en modelspace".format(apto))
            result["apartamentos"][apto] = {"devices": []}
            continue
        
        apto_x_mm, apto_y_mm = apto_instances[apto]
        apto_x_ft = apto_x_mm * MM_TO_FT
        apto_y_ft = apto_y_mm * MM_TO_FT
        
        devices_out = []
        for d in block_devices.get(apto, []):
            x_global_ft = apto_x_ft + d["x_local_m"] * M_TO_FT
            y_global_ft = apto_y_ft + d["y_local_m"] * M_TO_FT
            
            devices_out.append({
                "handle": "",
                "name": d["block_name"],
                "x": x_global_ft,
                "y": y_global_ft,
                "rotation": d["rotation"],
                "familia_revit": d["familia_revit"],
                "tipo_revit": d["tipo_revit"],
            })
        
        result["apartamentos"][apto] = {"devices": devices_out, "walls": [], "panels": []}
        print("\n{} - Dispositivos globales calculados: {}".format(apto, len(devices_out)))
        for d in devices_out:
            print("  {} @ ({:.2f}, {:.2f})ft rot={:.1f}".format(d["name"], d["x"], d["y"], d["rotation"]))
    
    # 4. Guardar JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("\n[OK] Guardado: " + OUTPUT_JSON)
    
    # Resumen
    for apto, data in result["apartamentos"].items():
        fam_counts = defaultdict(int)
        for d in data["devices"]:
            fam_counts[d["familia_revit"] + "/" + d["tipo_revit"]] += 1
        print("\n{} - Resumen:".format(apto))
        for ft, c in sorted(fam_counts.items()):
            print("  {}: {}".format(ft, c))

if __name__ == "__main__":
    main()