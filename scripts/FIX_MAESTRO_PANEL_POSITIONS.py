# -*- coding: utf-8 -*-
"""
FIX_MAESTRO_PANEL_POSITIONS.py
==============================
Corrige panel_revit_m en maestro_colocacion_piso5.json usando posiciones REALES
del parámetro "Panel Name" en Revit (obtenidas por MCP).
"""

import json
import os

DATA_DIR = r"D:\Work\PROJECTS\RevitElectrico\data"

# Posiciones REALES de paneles en Revit (ft) - desde MCP output
# Panel Name -> (x_ft, y_ft, z_ft)
PANEL_POSITIONS_REAL_FT = {
    "TF 01":  (38.048144642, 24.581793313, 47.309711286),
    "TF 02":  (38.041582962, 33.302641675, 47.309711286),
    "TF 17":  (28.853262752, 24.668244082, 47.309711286),
    "TF 18":  (28.853262752, 33.329661405, 47.309711286),
    "TE 05":  (21.457715545, 22.497196285, 47.309711286),
    "TE 06":  (21.349268564, 35.473877181, 47.309711286),
    "TE 07":  (-18.600734105, 23.957986357, 47.309711286),
    "TE 08":  (-18.601897622, 34.064118472, 47.309711286),
    "TB 15":  (-151.885040002, 26.628073178, 47.309711286),
    "TB 16":  (-152.045784202, 31.397755696, 47.309711286),
    "TC 14":  (-96.440486779, 22.742281300, 47.309711286),
    "TD 13":  (-96.373229561, 35.437172774, 47.309711286),
    # Variantes a/b (si existen en Revit)
    "TF 01a": (-46.987814537, 24.556772293, 47.309711286),
    "TF 01b": (-46.987814537, 24.556772293, 47.309711286),  # aprox
    "TF 02a": (-46.977759887, 33.311164633, 47.309711286),
    "TF 02b": (-72.499774379, 33.391918058, 47.309711286),
    "TF 17a": (-56.130248871, 24.691175115, 47.309711286),
    "TF 18a": (-56.115555162, 33.378964919, 47.309711286),
    "TE 07a": (-141.312169634, 22.584904332, 47.309711286),
    "TE 08a": (-141.336323131, 35.455422165, 47.309711286),
}

FT_TO_M = 0.3048

with open(os.path.join(DATA_DIR, "maestro_colocacion_piso5.json"), 'r', encoding='utf-8') as f:
    maestro = json.load(f)

print("=== CORRIGIENDO POSICIONES DE PANELES EN MAESTRO ===\n")

for apto_key, apto_data in maestro["apartamentos"].items():
    panel_real = apto_data.get("panel_name_revit")
    if panel_real in PANEL_POSITIONS_REAL_FT:
        x_ft, y_ft, z_ft = PANEL_POSITIONS_REAL_FT[panel_real]
        x_m = x_ft * FT_TO_M
        y_m = y_ft * FT_TO_M
        
        old_x = apto_data["panel_revit_m"]["x"]
        old_y = apto_data["panel_revit_m"]["y"]
        
        print("{}: '{}'".format(apto_key, panel_real))
        print("  ANTES: ({:.3f}, {:.3f}) m  [{:.2f}, {:.2f}] ft".format(old_x, old_y, old_x/FT_TO_M, old_y/FT_TO_M))
        print("  AHORA: ({:.3f}, {:.3f}) m  [{:.2f}, {:.2f}] ft".format(x_m, y_m, x_ft, y_ft))
        
        # Actualizar panel_revit_m
        apto_data["panel_revit_m"]["x"] = x_m
        apto_data["panel_revit_m"]["y"] = y_m
        
        # Recalcular offset_m y offset_mm
        base_dxf_m = apto_data["base_dxf_m"]
        offset_x_m = x_m - base_dxf_m["x"]
        offset_y_m = y_m - base_dxf_m["y"]
        apto_data["offset_m"]["x"] = offset_x_m
        apto_data["offset_m"]["y"] = offset_y_m
        apto_data["offset_mm"]["x"] = round(offset_x_m * 1000)
        apto_data["offset_mm"]["y"] = round(offset_y_m * 1000)
        
        # Recalcular posiciones de dispositivos
        for dev in apto_data["dispositivos"]:
            rel = dev["posicion_rel_panel_m"]
            dev["posicion_revit_m"]["x"] = x_m + rel["x"]
            dev["posicion_revit_m"]["y"] = y_m + rel["y"]
        
        print("  Offset nuevo: ({}, {}) mm".format(apto_data["offset_mm"]["x"], apto_data["offset_mm"]["y"]))
    else:
        print("[WARN] {}: panel '{}' no en lista de posiciones reales".format(apto_key, panel_real))

# Actualizar versión
maestro["version"] = "v06_PANEL_POSITIONS_REALES_MCP"

# Guardar
output_path = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(maestro, f, indent=2, ensure_ascii=False)

print("\n[OK] Maestro actualizado: {}".format(output_path))

# Verificación rápida F17, F18
for k in ["F17", "F18"]:
    d = maestro["apartamentos"][k]
    px, py = d["panel_revit_m"]["x"], d["panel_revit_m"]["y"]
    print("\n{} verificacion: Panel @ ({:.3f}, {:.3f}) m = ({:.2f}, {:.2f}) ft".format(k, px, py, px/FT_TO_M, py/FT_TO_M))
    # Primer dispositivo
    if d["dispositivos"]:
        dev = d["dispositivos"][0]
        dx, dy = dev["posicion_revit_m"]["x"], dev["posicion_revit_m"]["y"]
        print("  1er disp: ({:.3f}, {:.3f}) m = ({:.2f}, {:.2f}) ft".format(dx, dy, dx/FT_TO_M, dy/FT_TO_M))