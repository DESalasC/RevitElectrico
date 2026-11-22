"""
test_F6_COLOCAR_XPL_TODOS_APTOS_INTERRUPTORES_v01.py
Test fixture for F6_COLOCAR_XPL_TODOS_APTOS_INTERRUPTORES_v01.py
"""

import json
import os

# Fixture JSON para testing - simulando un subset del JSON XPL
FIXTURE_INTERRUPTORES = {
    "version": "1.0_TEST",
    "fecha": "2026-11-21",
    "unidades": "mm",
    "dispositivos": [
        # Interruptores en B15
        {
            "nombre_dxf": "ELEC-I-S-1-5A",
            "familia_revit": "M_Interruptores",
            "tipo_revit": "Simple",
            "x_mm": 10000.0,
            "y_mm": 10000.0,
            "z_mm": 0,
            "rotacion_grados": 0,
            "handle": "TEST101",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "B15",
            "dist_panel_mm": 5000.0
        },
        {
            "nombre_dxf": "ELEC-I-S-2-5A",
            "familia_revit": "M_Interruptores",
            "tipo_revit": "Doble",
            "x_mm": 11000.0,
            "y_mm": 11000.0,
            "z_mm": 0,
            "rotacion_grados": 90.0,
            "handle": "TEST102",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "B15",
            "dist_panel_mm": 4000.0
        },
        {
            "nombre_dxf": "ELEC-I-S-C1-5A",
            "familia_revit": "M_Interruptores",
            "tipo_revit": "Triple conmutable",
            "x_mm": 12000.0,
            "y_mm": 12000.0,
            "z_mm": 0,
            "rotacion_grados": 180.0,
            "handle": "TEST103",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "B15",
            "dist_panel_mm": 3000.0
        },
        # Pulsador/Timbre en B15
        {
            "nombre_dxf": "ELEC-TIMBRE",
            "familia_revit": "M_Pulsador - Interruptor",
            "tipo_revit": "Timbre",
            "x_mm": 13000.0,
            "y_mm": 13000.0,
            "z_mm": 0,
            "rotacion_grados": 0,
            "handle": "TEST104",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "B15",
            "dist_panel_mm": 2000.0
        },
        # Interruptores en TF 01b
        {
            "nombre_dxf": "ELEC-I-S-1-5A",
            "familia_revit": "M_Interruptores",
            "tipo_revit": "Simple",
            "x_mm": 20000.0,
            "y_mm": 20000.0,
            "z_mm": 0,
            "rotacion_grados": 270.0,
            "handle": "TEST105",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "TF 01b",
            "dist_panel_mm": 6000.0
        },
        {
            "nombre_dxf": "ELEC-I-S-2-5A",
            "familia_revit": "M_Interruptores",
            "tipo_revit": "Doble",
            "x_mm": 21000.0,
            "y_mm": 21000.0,
            "z_mm": 0,
            "rotacion_grados": 0,
            "handle": "TEST106",
            "layer": "ELEC-APPL-ILUM",
            "apto_asignado": "TF 01b",
            "dist_panel_mm": 5000.0
        },
    ]
}


def write_fixture():
    """Escribe el fixture JSON a disco para testing manual."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "test_fixture_interruptores.json"
    )
    with open(fixture_path, 'w') as f:
        json.dump(FIXTURE_INTERRUPTORES, f, indent=2)
    print("Fixture escrito a:", fixture_path)


if __name__ == "__main__":
    write_fixture()

    # Verificaciones basicas del fixture
    print("\n--- Verificaciones del Fixture ---")
    print("Total dispositivos:", len(FIXTURE_INTERRUPTORES["dispositivos"]))
    
    aptos = set(d["apto_asignado"] for d in FIXTURE_INTERRUPTORES["dispositivos"])
    print("Apartamentos:", sorted(aptos))
    
    familias = set(d["familia_revit"] for d in FIXTURE_INTERRUPTORES["dispositivos"])
    print("Familias:", sorted(familias))
    
    for apto in sorted(aptos):
        count = sum(1 for d in FIXTURE_INTERRUPTORES["dispositivos"] if d["apto_asignado"] == apto)
        print("  {}: {}".format(apto, count))
    
    # Verificar alturas esperadas
    ALTURAS_MM = {
        'M_Interruptores': 1100,
        'M_Pulsador - Interruptor': 1100,
    }
    for d in FIXTURE_INTERRUPTORES["dispositivos"]:
        fam = d["familia_revit"]
        altura = ALTURAS_MM.get(fam, "DESCONOCIDA")
        print("  {} {} -> altura {} mm".format(fam, d["tipo_revit"], altura))
    
    # Verificar rotaciones esperadas (+90° para placa horizontal)
    print("\nRotaciones esperadas (DXF + 90°):")
    for d in FIXTURE_INTERRUPTORES["dispositivos"]:
        rot_dxf = d["rotacion_grados"]
        rot_final = (rot_dxf + 90) % 360
        print("  {} {}: DXF={}° -> Final={}°".format(
            d["familia_revit"], d["tipo_revit"], rot_dxf, rot_final))

    print("\nFixture valido para testing.")