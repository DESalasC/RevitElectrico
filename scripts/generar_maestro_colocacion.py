# -*- coding: utf-8 -*-
"""
generar_maestro_colocacion.py
=============================
Genera maestro_colocacion_piso5.json cruzando por PANEL REAL DE REVIT.
Usa mapeo directo: inventario panel_name -> Panel Name real de Revit (verificado por MCP).
"""

import json
import os

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")

FT_TO_M = 0.3048

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Mapeo DIRECTO: panel_name del INVENTARIO -> Panel Name REAL en Revit (parámetro "Panel Name")
# Inventario tiene: "TAB-F-01-P5", "TAB-F-17 y 03-P5", "TAB-E-06-P5", etc.
# Revit real (MCP): "TF 01", "TF 17", "TE 06", etc.
INVENTARIO_PANEL_TO_REVIT_REAL = {
    "TAB-F-01-P5": "TF 01",
    "TAB-F-17 y 03-P5": "TF 17",
    "TAB-F-18 y 04-P5": "TF 18",
    "TAB-E-05-P5": "TE 05",
    "TAB-E-06-P5": "TE 06",
    "TAB-E-07-P5": "TE 07",
    "TAB-E-08-P5": "TE 08",
    "TAB-E-09-P5": "TE 09",  # si existe
    "TAB-E-10-P5": "TE 10",
    "TAB-E-20-P5": "TE 20",
    "TAB-E2-19-P5": "TE 19",  # o similar
    "TAB-E2-21-P5": "TE 21",
    "TAB-B-15-P5": "TB 15",
    "TAB-B-16-P5": "TB 16",
    "TAB-C-11-P5": "TC 14",
    "TAB-D-12-P5": "TD 13",
    # Variantes a/b (si están en inventario)
    "TAB-F-01a-P5": "TF 01a",
    "TAB-F-01b-P5": "TF 01b",
    "TAB-F-02-P5": "TF 02",
    "TAB-F-02a-P5": "TF 02a",
    "TAB-F-02b-P5": "TF 02b",
    "TAB-F-17a-P5": "TF 17a",
    "TAB-F-18a-P5": "TF 18a",
    "TAB-E-07a-P5": "TE 07a",
    "TAB-E-08a-P5": "TE 08a",
}

# Mapeo DXF apto_key -> Panel Name REAL en Revit (para cruzar con inventario)
APTO_KEY_MAP = {
    "F01": "TF 01", "F01A": "TF 01a", "F01B": "TF 01b",
    "F02": "TF 02", "F02A": "TF 02a", "F02B": "TF 02b",
    "F17": "TF 17", "F17A": "TF 17a",
    "F18": "TF 18", "F18A": "TF 18a",
    "E05": "TE 05", "E06": "TE 06", "E07": "TE 07", "E07A": "TE 07a",
    "E08": "TE 08", "E08A": "TE 08a",
    "B15": "TB 15", "B16": "TB 16",
    "C14": "TC 14", "D13": "TD 13",
}

# 1. Cargar inventario -> mapa por panel_name REAL (traducido)
inv_apto = load_json(os.path.join(DATA_DIR, "inventario_apartamentos_v01.json"))
panel_inv_real = {}  # Panel Name REAL -> info
for apto in inv_apto["apartamentos"]:
    panel = apto.get("tablero", {})
    insert_revit = apto.get("insert_revit", {})
    panel_name_inventario = panel.get("nombre_panel_atributo") or panel.get("panel_name_revit_sugerido") or panel.get("identificador_ancla")
    if panel_name_inventario and insert_revit:
        panel_name_real = INVENTARIO_PANEL_TO_REVIT_REAL.get(panel_name_inventario)
        if panel_name_real:
            panel_inv_real[panel_name_real] = {
                "inv_key": apto["identificador_apartamento"],
                "panel_name_inventario": panel_name_inventario,
                "panel_name_real": panel_name_real,
                "panel_x_m": insert_revit.get("x", 0),
                "panel_y_m": insert_revit.get("y", 0),
                "tipo": apto["tipo"],
                "nro": apto["nro"],
            }

print("[INFO] Paneles INVENTARIO -> REAL (Revit):")
for pn_inv, v in sorted(panel_inv_real.items()):
    print("  '{}' -> '{}' @ ({:.3f}, {:.3f}) m".format(v["panel_name_inventario"], pn_inv, v["panel_x_m"], v["panel_y_m"]))

# 2. Cargar maestro DXF global
dxf_master = load_json(os.path.join(DATA_DIR, "dxf_master_global_all.json"))

# 3. Mapear cada apartamento DXF
maestro = {
    "version": "v05_PANEL_NAMES_REALES_VERIFICADOS",
    "fecha_generacion": "2026-11-19",
    "proyecto": "RevitElectrico - T5-SantaMarta",
    "nivel": "Piso 5",
    "elevacion_nivel_m": 13.22,
    "fuente_dxf": "STM-T5-P5_bloques_electricos.dxf (FUENTE DE VERDAD ABSOLUTA - regla fija)",
    "nota": "pos_revit_m = panel_revit_m + device_rel_m (device_rel en pies -> metros)",
    "apartamentos": {}
}

ALTURAS = {
    "M_Toma doble": 0.30, "M_Comunicaciones": 1.00, "M_Interruptores": 1.10,
    "M_Pulsador - Interruptor": 1.10, "M_Timbre": 2.40, "M_ClimatizacionV": 2.60,
    "M_Iluminacion": 2.60, "Consolidation_Point": 2.70, "EA": 1.50,
    "M_Caja de conexiones hexagonal": 0.30, "M_Toma de telefono - Datos": 1.00,
}

matched_dxf = set()
matched_inv = set()

for dxf_key, dxf_data in dxf_master["apartamentos"].items():
    panel_name_real = APTO_KEY_MAP.get(dxf_key)
    if not panel_name_real:
        print("[WARN] DXF '{}': sin mapeo en APTO_KEY_MAP".format(dxf_key))
        continue
    
    if panel_name_real not in panel_inv_real:
        print("[WARN] DXF '{}': panel real '{}' no en inventario mapeado".format(dxf_key, panel_name_real))
        continue
    
    inv_info = panel_inv_real[panel_name_real]
    matched_dxf.add(dxf_key)
    matched_inv.add(panel_name_real)
    
    base_x_ft = dxf_data.get("base_x_ft", 0)
    base_y_ft = dxf_data.get("base_y_ft", 0)
    base_x_m = base_x_ft * FT_TO_M
    base_y_m = base_y_ft * FT_TO_M
    
    panel_x_m = inv_info["panel_x_m"]
    panel_y_m = inv_info["panel_y_m"]
    
    offset_x_m = panel_x_m - base_x_m
    offset_y_m = panel_y_m - base_y_m
    
    devices = []
    for dev in dxf_data.get("devices", []):
        x_m = dev.get("x", 0) * FT_TO_M
        y_m = dev.get("y", 0) * FT_TO_M
        fam = dev.get("familia_revit", "")
        devices.append({
            "nombre_dxf": dev.get("name", ""),
            "familia_revit": fam,
            "tipo_revit": dev.get("tipo_revit", ""),
            "rotacion_grados": dev.get("rotation", 0),
            "posicion_revit_m": {"x": panel_x_m + x_m, "y": panel_y_m + y_m},
            "posicion_rel_panel_m": {"x": x_m, "y": y_m},
            "altura_local_m": ALTURAS.get(fam, 0.30),
        })
    
    maestro["apartamentos"][dxf_key] = {
        "inventario_key": inv_info["inv_key"],
        "panel_name_dxf": dxf_data.get("panel_name", ""),
        "panel_name_inventario": inv_info["panel_name_inventario"],
        "panel_name_revit": panel_name_real,
        "panel_revit_m": {"x": panel_x_m, "y": panel_y_m},
        "base_dxf_m": {"x": base_x_m, "y": base_y_m},
        "base_dxf_ft": {"x": base_x_ft, "y": base_y_ft},
        "offset_m": {"x": offset_x_m, "y": offset_y_m},
        "offset_mm": {"x": round(offset_x_m * 1000), "y": round(offset_y_m * 1000)},
        "dispositivos": devices,
        "total_dispositivos": len(devices),
    }
    
    print("\n[INFO] {} -> panel REAL '{}' (inventario: '{}'):".format(dxf_key, panel_name_real, inv_info["panel_name_inventario"]))
    print("  Panel Revit @ ({:.3f}, {:.3f}) m".format(panel_x_m, panel_y_m))
    print("  Base DXF @ ({:.3f}, {:.3f}) m  [({:.2f}, {:.2f}) ft]".format(base_x_m, base_y_m, base_x_ft, base_y_ft))
    print("  Offset = ({:.3f}, {:.3f}) m  ->  ({}, {}) mm".format(
        offset_x_m, offset_y_m, round(offset_x_m*1000), round(offset_y_m*1000)))
    print("  Dispositivos: {}".format(len(devices)))

# 4. Guardar
output_path = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")
save_json(maestro, output_path)
print("\n[OK] Maestro guardado en: {}".format(output_path))

# 5. Resumen
total_devs = sum(a["total_dispositivos"] for a in maestro["apartamentos"].values())
print("\n=== RESUMEN ===")
print("Apartamentos procesados: {}".format(len(maestro["apartamentos"])))
print("Total dispositivos: {}".format(total_devs))
for k, v in sorted(maestro["apartamentos"].items()):
    print("  {}: {} disp, offset=({},{}) mm, panel_revit='{}'".format(
        k, v["total_dispositivos"], v["offset_mm"]["x"], v["offset_mm"]["y"], v["panel_name_revit"]))