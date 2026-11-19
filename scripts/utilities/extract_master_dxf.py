# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_MAESTRO_GLOBAL - Extrae dispositivos del DXF maestro
STM-T5-P5_bloques_electricos.dxf con coordenadas GLOBALES reales
"""

import ezdxf, json, os
from collections import defaultdict

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUTPUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global.json"

# Equivalencias bloque DXF -> familia Revit (de equivalencias_dxf_revit_v07.json)
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
    # Luces
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    # Comunicaciones
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-NET-PAU": ("M_Comunicaciones", "Datos"),
    # Extintor/EA
    "ELEC-EXT": ("EA", "Extintor"),
}

# Áreas de apartamentos en coordenadas GLOBALES (pies) - Piso 5
APARTAMENTOS_BOUNDS = {
    "F01": {"xmin": 30, "xmax": 50, "ymin": 0, "ymax": 30},
    "F02": {"xmin": 30, "xmax": 50, "ymin": 30, "ymax": 60},
    # Agregar más según layout real
}

def punto_en_apto(x, y, bounds):
    return bounds["xmin"] <= x <= bounds["xmax"] and bounds["ymin"] <= y <= bounds["ymax"]

def main():
    if not os.path.exists(MASTER_DXF):
        print("[ERROR] No existe: " + MASTER_DXF)
        return
    
    doc = ezdxf.readfile(MASTER_DXF)
    msp = doc.modelspace()
    
    # Estructura de salida
    result = {"apartamentos": {}}
    for apto in APARTAMENTOS_BOUNDS:
        result["apartamentos"][apto] = {"devices": [], "walls": [], "panels": []}
    
    stats = defaultdict(int)
    unmatched = set()
    
    for e in msp:
        if e.dxftype() == "INSERT":
            block_name = e.dxf.name
            x, y = e.dxf.insert.x, e.dxf.insert.y
            rotation = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
            
            # ¿En qué apartamento cae?
            apto_found = None
            for apto, bounds in APARTAMENTOS_BOUNDS.items():
                if punto_en_apto(x, y, bounds):
                    apto_found = apto
                    break
            
            if not apto_found:
                # Fuera de apartamentos conocidos - registrar para debug
                continue
            
            # Buscar equivalencia
            fam_typ = None
            for key, val in EQUIVALENCIAS.items():
                if key in block_name:
                    fam_typ = val
                    break
            
            if not fam_typ:
                unmatched.add(block_name)
                continue
            
            familia, tipo = fam_typ
            stats[block_name] += 1
            
            device = {
                "handle": e.dxf.handle,
                "name": block_name,
                "x": x,  # YA SON COORDENADAS GLOBALES
                "y": y,
                "rotation": rotation,
                "familia_revit": familia,
                "tipo_revit": tipo,
            }
            result["apartamentos"][apto_found]["devices"].append(device)
        
        elif e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE"):
            # Muros - opcional
            pass
    
    # Guardar
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("[OK] Guardado: " + OUTPUT_JSON)
    print("\n--- DISPOSITIVOS POR APARTAMENTO ---")
    for apto, data in result["apartamentos"].items():
        print("  {}: {} dispositivos".format(apto, len(data["devices"])))
        # Conteos por familia
        fam_counts = defaultdict(int)
        for d in data["devices"]:
            fam_counts[d["familia_revit"] + "/" + d["tipo_revit"]] += 1
        for ft, c in sorted(fam_counts.items()):
            print("    {}: {}".format(ft, c))
    
    print("\n--- BLOQUES SIN EQUIVALENCIA ---")
    for b in sorted(unmatched):
        print("  " + b)
    
    print("\n--- ESTADÍSTICAS BLOQUES ---")
    for b, c in sorted(stats.items()):
        print("  {}: {}".format(b, c))

if __name__ == "__main__":
    main()