"""
test_COLOCAR_XPL_INTERRUPTORES_v01.py - Fixture para COLOCAR_XPL_INTERRUPTORES_v01.py
"""

import json
import os

FIXTURE = {
    "version": "1.0_TEST",
    "fecha": "2026-11-22",
    "unidades": "mm",
    "dispositivos": [
        {"nombre_dxf": "ELEC-I-S-1-5A", "familia_revit": "M_Interruptores", "tipo_revit": "Simple", "x_mm": 10000.0, "y_mm": 10000.0, "z_mm": 0, "rotacion_grados": 0, "handle": "I001", "layer": "ELEC-APPL-ILUM", "apto_asignado": "B15", "dist_panel_mm": 5000.0},
        {"nombre_dxf": "ELEC-I-S-2-5A", "familia_revit": "M_Interruptores", "tipo_revit": "Doble", "x_mm": 11000.0, "y_mm": 11000.0, "z_mm": 0, "rotacion_grados": 90.0, "handle": "I002", "layer": "ELEC-APPL-ILUM", "apto_asignado": "B15", "dist_panel_mm": 4000.0},
        {"nombre_dxf": "ELEC-I-S-C1-5A", "familia_revit": "M_Interruptores", "tipo_revit": "Triple conmutable", "x_mm": 12000.0, "y_mm": 12000.0, "z_mm": 0, "rotacion_grados": 180.0, "handle": "I003", "layer": "ELEC-APPL-ILUM", "apto_asignado": "TF_01b", "dist_panel_mm": 3000.0},
        {"nombre_dxf": "ELEC-TIMBRE", "familia_revit": "M_Pulsador - Interruptor", "tipo_revit": "Timbre", "x_mm": 13000.0, "y_mm": 13000.0, "z_mm": 0, "rotacion_grados": 0, "handle": "I004", "layer": "ELEC-APPL-ILUM", "apto_asignado": "TF_01b", "dist_panel_mm": 2000.0},
        {"nombre_dxf": "ELEC-I-S-1-5A", "familia_revit": "M_Interruptores", "tipo_revit": "Simple", "x_mm": 20000.0, "y_mm": 20000.0, "z_mm": 0, "rotacion_grados": 270.0, "handle": "I005", "layer": "ELEC-APPL-ILUM", "apto_asignado": "TF_01b", "dist_panel_mm": 6000.0},
    ]
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "test_fixture_interruptores_v01.json")
    with open(out, 'w') as f:
        json.dump(FIXTURE, f, indent=2)
    print("Fixture:", out)
    print("Total:", len(FIXTURE["dispositivos"]))
    print("Rotaciones esperadas (DXF + 90°):")
    for d in FIXTURE["dispositivos"]:
        r = (d["rotacion_grados"] + 90) % 360
        print("  {} {}: {}° -> {}°".format(d["familia_revit"], d["tipo_revit"], d["rotacion_grados"], r))