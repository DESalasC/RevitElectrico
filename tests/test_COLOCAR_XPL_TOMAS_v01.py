"""
test_COLOCAR_XPL_TOMAS_v01.py - Fixture para COLOCAR_XPL_TOMAS_v01.py
"""

import json
import os

FIXTURE = {
    "version": "1.0_TEST",
    "fecha": "2026-11-22",
    "unidades": "mm",
    "dispositivos": [
        {"nombre_dxf": "ELEC-T-GFCI-t-15A", "familia_revit": "M_Toma doble", "tipo_revit": "GFCI", "x_mm": 10000.0, "y_mm": 10000.0, "z_mm": 0, "rotacion_grados": 0, "handle": "T001", "layer": "ELEC-APPL-TOMAS", "apto_asignado": "B15", "dist_panel_mm": 5000.0},
        {"nombre_dxf": "ELEC-T-D-t-15A", "familia_revit": "M_Toma doble", "tipo_revit": "Normal", "x_mm": 11000.0, "y_mm": 11000.0, "z_mm": 0, "rotacion_grados": 90.0, "handle": "T002", "layer": "ELEC-APPL-TOMAS", "apto_asignado": "B15", "dist_panel_mm": 4000.0},
        {"nombre_dxf": "ELEC-TEL", "familia_revit": "M_Comunicaciones", "tipo_revit": "Datos", "x_mm": 12000.0, "y_mm": 12000.0, "z_mm": 0, "rotacion_grados": 180.0, "handle": "T003", "layer": "ELEC-APPL-TOMAS", "apto_asignado": "TF_01b", "dist_panel_mm": 3000.0},
        {"nombre_dxf": "ELEC-T-GFCI-t-15A", "familia_revit": "M_Toma doble", "tipo_revit": "GFCI", "x_mm": 20000.0, "y_mm": 20000.0, "z_mm": 0, "rotacion_grados": 270.0, "handle": "T004", "layer": "ELEC-APPL-TOMAS", "apto_asignado": "TF_01b", "dist_panel_mm": 6000.0},
    ]
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "test_fixture_tomas_v01.json")
    with open(out, 'w') as f:
        json.dump(FIXTURE, f, indent=2)
    print("Fixture:", out)
    print("Total:", len(FIXTURE["dispositivos"]))
    for a in sorted(set(d["apto_asignado"] for d in FIXTURE["dispositivos"])):
        print("  {}: {}".format(a, sum(1 for d in FIXTURE["dispositivos"] if d["apto_asignado"] == a)))