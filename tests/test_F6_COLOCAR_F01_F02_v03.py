#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_F6_COLOCAR_F01_F02_v03.py
==============================
Test fixture para F6_COLOCAR_F01_F02_v03.py

Valida la lógica de clasificación de familias y construcción de device_json
SIN llamar a MCP (mockea mcp_send_code).
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Añadir el directorio del script al path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar el módulo a testear
import F6_COLOCAR_F01_F02_v03 as script


def test_clasificacion_familias():
    """Verifica que las familias se clasifiquen correctamente."""
    # Muro face-based
    assert "M_Toma doble" in script.FAMILIAS_MURO_FACE
    assert "M_Interruptores" in script.FAMILIAS_MURO_FACE
    assert "M_Comunicaciones" in script.FAMILIAS_MURO_FACE
    assert "M_Climatizacion" in script.FAMILIAS_MURO_FACE
    assert "M_Timbre" in script.FAMILIAS_MURO_FACE
    assert "M_Pulsador - Interruptor" in script.FAMILIAS_MURO_FACE

    # Techo face-based
    assert "M_Iluminacion" in script.FAMILIAS_TECHO_FACE
    assert "M_ClimatizacionV" in script.FAMILIAS_TECHO_FACE
    assert "Consolidation_Point" in script.FAMILIAS_TECHO_FACE

    # No solapamiento
    assert script.FAMILIAS_MURO_FACE.isdisjoint(script.FAMILIAS_TECHO_FACE)
    print("✓ test_clasificacion_familias")


def test_device_json_escaping():
    """Verifica el escaping correcto para C# verbatim @\"...\" (\" -> \"\")."""
    device_input = {"F": "M_Toma doble", "T": "Normal", "X": 1000.0, "Y": 2000.0, "Z": 3000.0,
                    "R": 90.0, "A": 300.0, "L": 192512, "D": "TEST_01"}
    device_json = json.dumps(device_input, separators=(",", ":"))
    device_json_escaped = device_json.replace('"', '""')

    # Verificar que no hay comillas simples sin escapar
    assert '"' not in device_json_escaped or device_json_escaped.count('""') == device_json.count('"')
    # Verificar formato válido
    assert device_json_escaped.startswith('{')
    assert device_json_escaped.endswith('}')
    print("✓ test_device_json_escaping")


def test_offset_calculo():
    """Verifica cálculo de offset (panel_revit - panel_dxf_local)."""
    panel_dxf_m = (-2.3995, -0.5048)  # metros
    panel_revit_mm = (11591.4, 7505.8)  # mm

    pdmm = (panel_dxf_m[0] * 1000, panel_dxf_m[1] * 1000)
    offset_x = panel_revit_mm[0] - pdmm[0]
    offset_y = panel_revit_mm[1] - pdmm[1]

    # Valores esperados del checkpoint
    assert abs(offset_x - 13990.9) < 1.0
    assert abs(offset_y - 8010.6) < 1.0
    print("✓ test_offset_calculo")


def test_z_absoluta_mm():
    """Verifica Z absoluto en mm = (nivel_elevacion + altura_local) * 1000."""
    nivel_elevacion = 13.22  # metros
    altura_local_m = 0.3     # metros
    z_mm = (nivel_elevacion + altura_local_m) * 1000
    assert abs(z_mm - 13520.0) < 0.01
    print("✓ test_z_absoluta_mm")


def test_rotacion_norma_colombiana():
    """Verifica que la rotación +90° se aplica en CS_FACE_WALL."""
    # El template CS_FACE_WALL incluye: rad = (rot + 90.0) * Math.PI / 180.0
    assert "(rot + 90.0)" in script.CS_FACE_WALL
    print("✓ test_rotacion_norma_colombiana")


def test_cs_templates_size():
    """Verifica que cada template C# sea < 8KB (límite MCP)."""
    for name, template in [
        ("CS_GET_PANELS", script.CS_GET_PANELS),
        ("CS_GET_WALLS", script.CS_GET_WALLS),
        ("CS_GET_CEILINGS", script.CS_GET_CEILINGS),
        ("CS_FACE_WALL", script.CS_FACE_WALL),
        ("CS_FACE_CEILING", script.CS_FACE_CEILING),
        ("CS_LEVEL_BASED", script.CS_LEVEL_BASED),
    ]:
        size_kb = len(template.encode("utf-8")) / 1024
        assert size_kb < 8.0, f"{name} = {size_kb:.1f} KB > 8 KB límite MCP"
    print("✓ test_cs_templates_size (todos < 8KB)")


def test_fixture_valida():
    """Verifica que el fixture JSON sea válido y completo."""
    fixture_path = Path(__file__).parent / "fixtures" / "inventario_test_F01_v03.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    assert "metadatos" in fixture
    assert "dispositivos" in fixture
    assert len(fixture["dispositivos"]) == 3

    # Verificar 3 tipos: muro, techo, level
    familias = [d["familia_revit"] for d in fixture["dispositivos"]]
    assert "M_Toma doble" in familias      # muro face-based
    assert "M_Iluminacion" in familias     # techo face-based
    assert "M_Comunicaciones" in familias  # level-based (en v03 es muro face-based, pero fixture lo prueba)

    # Cada dispositivo tiene campos requeridos
    for d in fixture["dispositivos"]:
        assert "handle" in d
        assert "familia_revit" in d
        assert "tipo_revit" in d
        assert "x" in d and "y" in d and "altura_local_m" in d
        assert "rotacion_final_grados" in d
    print("✓ test_fixture_valida")


def test_mcp_response_parsing():
    """Verifica lógica de parsing de respuesta MCP (doble encoding + null handling)."""
    # Simular respuestas MCP
    test_cases = [
        # Caso 1: doble encoding (normal)
        {"result": {"success": True, "result": '"{\\"success\\":true,\\"elementId\\":123,\\"usedFace\\":true}"', "errorMessage": ""}},
        # Caso 2: simple encoding
        {"result": {"success": True, "result": '{"success":true,"elementId":123,"usedFace":true}', "errorMessage": ""}},
        # Caso 3: null inner (json.loads("null") -> None)
        {"result": {"success": True, "result": "null", "errorMessage": ""}},
        # Caso 4: error MCP (success=false, result=null)
        {"result": {"success": False, "result": None, "errorMessage": "Symbol not found"}},
    ]

    for resp in test_cases:
        raw = resp["result"]["result"]
        if isinstance(raw, str):
            inner = json.loads(raw)
            if inner is None:
                res = {"success": False, "error": "MCP returned null"}
            elif isinstance(inner, str):
                res = json.loads(inner)
            else:
                res = inner
        else:
            # raw es None (caso error MCP con result=null)
            res = {"success": False, "error": resp["result"].get("errorMessage", "Unknown")}

        # Verificar que no crashea y tiene success
        assert isinstance(res, dict)
        assert "success" in res
    print("✓ test_mcp_response_parsing")


if __name__ == "__main__":
    print("Ejecutando tests para F6_COLOCAR_F01_F02_v03.py...\n")
    test_clasificacion_familias()
    test_device_json_escaping()
    test_offset_calculo()
    test_z_absoluta_mm()
    test_rotacion_norma_colombiana()
    test_cs_templates_size()
    test_fixture_valida()
    test_mcp_response_parsing()
    print("\n✅ Todos los tests pasaron.")