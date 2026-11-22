"""
test_F6_COLOCAR_XPL_TODOS_APTOS_TOMAS_v01.py
Test fixture for F6_COLOCAR_XPL_TODOS_APTOS_TOMAS_v01.py
"""

import json
import os

# Fixture JSON para testing - simulando un subset del JSON XPL
FIXTURE_TOMAS = {
    "version": "1.0_TEST",
    "fecha": "2026-11-21",
    "unidades": "mm",
    "dispositivos": [
        # Tomas en B15
        {
            "nombre_dxf": "ELEC-T-GFCI-t-15A",
            "familia_revit": "M_Toma doble",
            "tipo_revit": "GFCI",
            "x_mm": 10000.0,
            "y_mm": 10000.0,
            "z_mm": 0,
            "rotacion_grados": 0,
            "handle": "TEST001",
            "layer": "ELEC-APPL-TOMAS",
            "apto_asignado": "B15",
            "dist_panel_mm": 5000.0
        },
        {
            "nombre_dxf": "ELEC-T-D-t-15A",
            "familia_revit": "M_Toma doble",
            "tipo_revit": "Normal",
            "x_mm": 11000.0,
            "y_mm": 11000.0,
            "z_mm": 0,
            "rotacion_grados": 90.0,
            "handle": "TEST002",
            "layer": "ELEC-APPL-TOMAS",
            "apto_asignado": "B15",
            "dist_panel_mm": 4000.0
        },
        {
            "nombre_dxf": "ELEC-TEL",
            "familia_revit": "M_Comunicaciones",
            "tipo_revit": "Datos",
            "x_mm": 12000.0,
            "y_mm": 12000.0,
            "z_mm": 0,
            "rotacion_grados": 180.0,
            "handle": "TEST003",
            "layer": "ELEC-APPL-TOMAS",
            "apto_asignado": "B15",
            "dist_panel_mm": 3000.0
        },
        # Tomas en TF 01b
        {
            "nombre_dxf": "ELEC-T-GFCI-t-15A",
            "familia_revit": "M_Toma doble",
            "tipo_revit": "GFCI",
            "x_mm": 20000.0,
            "y_mm": 20000.0,
            "z_mm": 0,
            "rotacion_grados": 270.0,
            "handle": "TEST004",
            "layer": "ELEC-APPL-TOMAS",
            "apto_asignado": "TF 01b",
            "dist_panel_mm": 6000.0
        },
    ]
}


def write_fixture():
    """Escribe el fixture JSON a disco para testing manual."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "test_fixture_tomas.json"
    )
    with open(fixture_path, 'w') as f:
        json.dump(FIXTURE_TOMAS, f, indent=2)
    print("Fixture escrito a:", fixture_path)


if __name__ == "__main__":
    write_fixture()

    # Verificaciones basicas del fixture
    print("\n--- Verificaciones del Fixture ---")
    print("Total dispositivos:", len(FIXTURE_TOMAS["dispositivos"]))
    
    aptos = set(d["apto_asignado"] for d in FIXTURE_TOMAS["dispositivos"])
    print("Apartamentos:", sorted(aptos))
    
    familias = set(d["familia_revit"] for d in FIXTURE_TOMAS["dispositivos"])
    print("Familias:", sorted(familias))
    
    for apto in sorted(aptos):
        count = sum(1 for d in FIXTURE_TOMAS["dispositivos"] if d["apto_asignado"] == apto)
        print("  {}: {}".format(apto, count))
    
    # Verificar alturas esperadas
    ALTURAS_MM = {
        'M_Toma doble': 1000,
        'M_Comunicaciones': 1000,
    }
    for d in FIXTURE_TOMAS["dispositivos"]:
        fam = d["familia_revit"]
        altura = ALTURAS_MM.get(fam, "DESCONOCIDA")
        print("  {} {} -> altura {} mm".format(fam, d["tipo_revit"], altura))

    print("\nFixture valido para testing.")