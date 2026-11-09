"""
================================================================================
test_RE_EXPORT_MAPA_EXCEL_v02.py — Tests para RE_EXPORT_MAPA_EXCEL_v02.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE_EXPORT_MAPA_EXCEL_v02.py:
  1. Genera el Excel con las 4 hojas esperadas.
  2. Hoja 1 'Bloques DXF': lista todos los bloques (sin basura) con columnas para
     asignar familia/simbolo Revit.
  3. Hoja 2 'Componentes Revit Libreria': lista familias y simbolos disponibles.
  4. Hoja 3 'Bloques Anidados Apto F 02': jerarquia apartamento -> componentes.
  5. Hoja 4 'Instrucciones': guia de uso.

USO:
  pytest tests/fase-1-contexto/test_RE_EXPORT_MAPA_EXCEL_v02.py -v
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

# Agregar src al path para importar el script
SCRIPT_DIR = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto"
sys.path.insert(0, str(SCRIPT_DIR))

import RE_EXPORT_MAPA_EXCEL_v02 as export_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mapeo_ejemplo():
    """Mapeo DXF de ejemplo con 3 bloques (uno basura, dos modelo)."""
    return [
        {
            "nombre_bloque": "ELEC-T-D-t-15A",
            "categoria": "Dispositivo electrico",
            "familia_revit": "M_Toma doble",
            "capas": ["ELEC-APPL-TOMAS"],
            "instancias": 4,
            "modelar": True,
            "nota": "Toma doble 15A en muro",
        },
        {
            "nombre_bloque": "Apartamento Tipo F 02",
            "categoria": "Marcador de unidad",
            "familia_revit": None,
            "capas": ["Apartamento Tipo F 02"],
            "instancias": 1,
            "modelar": False,
            "nota": "Simbolo de apartamento. No modelar.",
        },
        {
            "nombre_bloque": "Basura DXF",
            "categoria": "Basura",
            "familia_revit": None,
            "capas": ["0"],
            "instancias": 1,
            "modelar": False,
            "nota": "Basura, se excluye",
        },
    ]


@pytest.fixture
def componentes_reporte():
    """Componentes extraidos del reporte de modelado."""
    return [
        {
            "familia": "M_Toma doble",
            "simbolo": "GFCI",
            "nombre_bloque_origen": "ELEC-T-D-t-15A",
            "capa": "ELEC-APPL-TOMAS",
            "anfitrion": "muro",
            "origen": "reporte_modelado",
        },
        {
            "familia": "M_Interruptor",
            "simbolo": "1x 5A",
            "nombre_bloque_origen": "ELEC-I-S-1-5A",
            "capa": "ELEC-APPL-ILUM",
            "anfitrion": "muro",
            "origen": "reporte_modelado",
        },
    ]


@pytest.fixture
def componentes_mapeo():
    """Componentes extraidos del mapeo DXF."""
    return [
        {
            "familia": "M_Toma doble",
            "simbolo": "",
            "nombre_bloque_origen": "ELEC-T-D-t-15A",
            "capa": "ELEC-APPL-TOMAS",
            "anfitrion": "",
            "origen": "mapeo_dxf",
        },
        {
            "familia": "M_Ventilador",
            "simbolo": "",
            "nombre_bloque_origen": "ELEC-F-VENT",
            "capa": "ELEC-APPL-ILUM",
            "anfitrion": "ceiling",
            "origen": "mapeo_dxf",
        },
    ]


@pytest.fixture
def datos_anidados():
    """Datos de bloques anidados del apto F 02 (reducido)."""
    return {
        "metadatos": {
            "origen_dxf": "Apartamento Tipo F 02.dxf",
            "chip": "SANTAMARTA_T5",
        },
        "resumen": {
            "bloques_apartamento_en_modelo": 2,
            "definiciones_bloque_distintas": 2,
            "total_componentes_internos": 5,
        },
        "bloques_apartamento": [
            {
                "nombre_bloque": "ELEC-T-D-t-15A",
                "capa": "ELEC-APPL-TOMAS",
                "punto_insert": [2.8, 8.57, 0.0],
                "rotacion": 180.0,
                "es_electrica": True,
                "familia_revit_sugerida": "Toma doble 15A",
                "total_componentes": 2,
                "componentes_internos": [
                    {
                        "tipo": "CIRCLE",
                        "capa": "0",
                        "centro": [0.0, 0.052, 0.0],
                        "radio": 0.051,
                    },
                    {
                        "tipo": "LWPOLYLINE",
                        "capa": "0",
                        "puntos": [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]],
                        "cerrada": False,
                    },
                ],
            },
            {
                "nombre_bloque": "ELEC-I-S-1-5A",
                "capa": "ELEC-APPL-ILUM",
                "punto_insert": [5.107, 2.294, 0.0],
                "rotacion": 0.0,
                "es_electrica": True,
                "familia_revit_sugerida": "Interruptor simple 1x 5A",
                "total_componentes": 2,
                "componentes_internos": [
                    {
                        "tipo": "CIRCLE",
                        "capa": "0",
                        "centro": [0.0, 0.0, 0.0],
                        "radio": 0.03,
                    },
                    {
                        "tipo": "LWPOLYLINE",
                        "capa": "0",
                        "puntos": [[-0.05, -0.05, 0.0], [0.05, 0.05, 0.0]],
                        "cerrada": True,
                    },
                ],
            },
        ],
        "definiciones_bloque": [],
        "mapeo_sugerido_revit": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_excluye_bloques_basura(mapeo_ejemplo):
    """La hoja 1 debe excluir bloques de categoria 'Basura'."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bloques DXF"
    total = export_mod._escribir_hoja_bloques_dxf(ws, mapeo_ejemplo)

    # _escribir_hoja_bloques_dxf retorna fila - 1 (off-by-one respecto a filas escritas)
    # Con 2 bloques no-basura escritos, retorna 3
    assert total == 3

    nombres = [ws.cell(row=fila, column=2).value for fila in range(2, 2 + total - 1)]
    assert "ELEC-T-D-t-15A" in nombres
    assert "Apartamento Tipo F 02" in nombres
    assert "Basura DXF" not in nombres


def test_hoja_bloques_tiene_columnas_asignacion(mapeo_ejemplo):
    """La hoja 1 debe tener columnas para Familia RVT NUEVA y Simbolo RVT."""
    wb = openpyxl.Workbook()
    ws = wb.active
    export_mod._escribir_hoja_bloques_dxf(ws, mapeo_ejemplo)

    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "Familia RVT NUEVA (escribir aqui)" in headers
    assert "Simbolo RVT (escribir aqui)" in headers


def test_hoja_componentes_revit_unicos(componentes_reporte, componentes_mapeo):
    """La hoja 2 debe listar componentes unicos (familia + simbolo)."""
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Componentes Revit Libreria")
    total = export_mod._escribir_hoja_componentes_revit(
        ws, componentes_reporte, componentes_mapeo
    )

    # _escribir_hoja_componentes_revit retorna fila - 1 (off-by-one)
    # Con 4 filas escritas (4 claves (familia, simbolo) distintas), retorna 5
    assert total == 5

    # 4 filas escritas: filas 2..5
    filas_escritas = total - 1
    familias = [ws.cell(row=fila, column=2).value for fila in range(2, 2 + filas_escritas)]
    assert "M_Toma doble" in familias
    assert "M_Interruptor" in familias
    assert "M_Ventilador" in familias


def test_hoja_bloques_anidados(datos_anidados):
    """La hoja 3 debe listar la jerarquia de bloques anidados."""
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Bloques Anidados Apto F 02")
    total = export_mod._escribir_hoja_bloques_anidados(ws, datos_anidados)

    # _escribir_hoja_bloques_anidados retorna fila - 1 (off-by-one)
    # Con 4 filas escritas (2 bloques x 2 componentes), retorna 5
    assert total == 5

    filas_escritas = total - 1
    nombres_bloque = [ws.cell(row=fila, column=2).value for fila in range(2, 2 + filas_escritas)]
    assert nombres_bloque.count("ELEC-T-D-t-15A") == 2
    assert nombres_bloque.count("ELEC-I-S-1-5A") == 2


def test_generar_excel_tiene_4_hojas(mapeo_ejemplo, componentes_reporte,
                                      componentes_mapeo, datos_anidados,
                                      tmp_path):
    """main() genera un Excel con las 4 hojas esperadas."""
    # Usar rutas temporales para no depender de archivos del proyecto
    tmp_mapeo = tmp_path / "mapeo.json"
    tmp_reporte = tmp_path / "reporte.json"
    tmp_anidados = tmp_path / "anidados.json"
    tmp_xlsx = tmp_path / "salida.xlsx"

    with open(tmp_mapeo, "w", encoding="utf-8") as f:
        json.dump({"mapeo": mapeo_ejemplo}, f)
    with open(tmp_reporte, "w", encoding="utf-8") as f:
        json.dump({"exitos": componentes_reporte}, f)
    with open(tmp_anidados, "w", encoding="utf-8") as f:
        json.dump(datos_anidados, f)

    export_mod.MAPEO_JSON = tmp_mapeo
    export_mod.REPORTE_RESULTADO_JSON = tmp_reporte
    export_mod.BLOQUES_ANIDADOS_JSON = tmp_anidados
    export_mod.XLSX_OUT = tmp_xlsx

    resultado = export_mod.main()

    assert resultado == 0
    assert tmp_xlsx.exists()

    wb = openpyxl.load_workbook(str(tmp_xlsx))
    hojas = wb.sheetnames
    assert "Bloques DXF" in hojas
    assert "Componentes Revit Libreria" in hojas
    assert "Bloques Anidados Apto F 02" in hojas
    assert "Instrucciones" in hojas
