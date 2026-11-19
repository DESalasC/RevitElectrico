#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# test_RE6_CORREGIR_ROTACIONES_v01.py
import json
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from RE6_CORREGIR_ROTACIONES_v01 import analyze_oraculo, update_rot_config, update_inventario

def test_analyze_oraculo():
    # Simular oraculo con M_Comunicaciones volteada (delta ~180)
    oraculo = {
        "firmas_por_familia_tipo": {
            "M_Comunicaciones | Datos": {
                "n_instancias": 10,
                "delta_moda_grados": 178.5,
                "delta_promedio_grados": 175.2,
                "bbox_tipico_mm": {"x_mm": 70, "y_mm": 115, "z_mm": 40},
                "instancias": [
                    {"handle_dxf": "1F2", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "83", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "7A", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "1F6", "rotacion_location_deg": 270, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "D9", "rotacion_location_deg": 270, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "D8", "rotacion_location_deg": 270, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "106", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "1F3", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "1F4", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                    {"handle_dxf": "1F5", "rotacion_location_deg": 90, "rotacion_dxf_grados": 90, "delta_dxf_vs_real": 180},
                ]
            }
        }
    }
    rec = analyze_oraculo(oraculo)
    assert rec is not None
    assert rec["delta_familia_grados"] == 180.0
    assert rec["interpretacion"] == "VOLTEADA_180"
    print("test_analyze_oraculo: OK")

def test_analyze_oraculo_rot90():
    # Simular oraculo con M_Comunicaciones rotada 90
    oraculo = {
        "firmas_por_familia_tipo": {
            "M_Comunicaciones | Datos": {
                "n_instancias": 5,
                "delta_moda_grados": 92.0,
                "delta_promedio_grados": 91.5,
                "bbox_tipico_mm": {"x_mm": 115, "y_mm": 70, "z_mm": 40},
                "instancias": []
            }
        }
    }
    rec = analyze_oraculo(oraculo)
    assert rec is not None
    assert rec["delta_familia_grados"] == 90.0
    assert rec["interpretacion"] == "ROTADA_90"
    print("test_analyze_oraculo_rot90: OK")

def test_update_rot_config():
    config = {
        "version": "1.0",
        "delta_rot_por_familia": {"M_Toma doble": 90.0},
        "familias_no_afectadas": {
            "M_Comunicaciones": "Sin medicion todavia"
        }
    }
    rec = {
        "familia": "M_Comunicaciones",
        "tipo": "Datos",
        "delta_familia_grados": 180.0,
        "interpretacion": "VOLTEADA_180",
        "delta_moda_oraculo": 178.5,
        "delta_promedio_oraculo": 175.2,
        "bbox_tipico_mm": {"x_mm": 70, "y_mm": 115, "z_mm": 40}
    }
    updated = update_rot_config(config, rec)
    assert updated["delta_rot_por_familia"]["M_Comunicaciones"] == 180.0
    assert "M_Comunicaciones" not in updated["familias_no_afectadas"]
    assert "M_Comunicaciones" in updated["evidencia_medida"]
    assert updated["version"] == "1.1"
    print("test_update_rot_config: OK")

def test_update_inventario():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        inv = {
            "metadatos": {"version_rotaciones": "1.0"},
            "dispositivos": [
                {"handle": "1F2", "familia_revit": "M_Comunicaciones", "tipo_revit": "Datos",
                 "rotacion_bloque_grados": 90.0, "delta_rotacion_familia_grados": 0.0,
                 "rotacion_final_grados": 90.0},
                {"handle": "83", "familia_revit": "M_Comunicaciones", "tipo_revit": "Datos",
                 "rotacion_bloque_grados": 90.0, "delta_rotacion_familia_grados": 0.0,
                 "rotacion_final_grados": 90.0},
                {"handle": "63", "familia_revit": "M_Toma doble", "tipo_revit": "GFCI",
                 "rotacion_bloque_grados": 180.0, "delta_rotacion_familia_grados": 90.0,
                 "rotacion_final_grados": 270.0},
            ]
        }
        json.dump(inv, f)
        temp_path = f.name

    try:
        n = update_inventario(temp_path, 180.0)
        assert n == 2
        with open(temp_path, 'r') as f:
            updated = json.load(f)
        # Verificar M_Comunicaciones actualizados
        for d in updated["dispositivos"]:
            if d["familia_revit"] == "M_Comunicaciones":
                assert d["delta_rotacion_familia_grados"] == 180.0
                assert d["rotacion_final_grados"] == 270.0  # 90 + 180
            else:
                assert d["delta_rotacion_familia_grados"] == 90.0  # sin cambios
        assert updated["metadatos"]["version_rotaciones"] == "1.1"
        print("test_update_inventario: OK")
    finally:
        os.unlink(temp_path)

if __name__ == "__main__":
    test_analyze_oraculo()
    test_analyze_oraculo_rot90()
    test_update_rot_config()
    test_update_inventario()
    print("\n>>> TODOS LOS TESTS PASARON <<<")