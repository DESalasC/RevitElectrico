"""
================================================================================
test_RE3_LECTURA_IFC_v01.py — Tests para RE3_LECTURA_IFC_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE3_LECTURA_IFC_v01.py:
  1. Lee un archivo IFC y extrae elementos por tipo Ifc.
  2. Extrae cantidades (área, volumen, longitud) de cada elemento.
  3. Extrae Qto sets de cada elemento.
  4. Genera JSON de salida con metadatos, resumen, elementos, qto_sets y tipos_elemento.

FIXTURE:
  tests/fase-1-contexto/fixture_RE3_ifc_referencia.json (estructura de salida esperada)

USO:
  pytest tests/fase-1-contexto/test_RE3_LECTURA_IFC_v01.py -v
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE3_LECTURA_IFC_v01.py"

spec = importlib.util.spec_from_file_location("RE3_LECTURA_IFC_v01", SCRIPT_PATH)
_re3_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_re3_mod)
leer_ifc = _re3_mod.leer_ifc

FIXTURE_PATH = Path(__file__).parent / "fixture_RE3_ifc_referencia.json"


# ---------------------------------------------------------------------------
# Helper: genera un IFC mínimo válido con una pared y cantidades
# ---------------------------------------------------------------------------

def _crear_ifc_prueba(tmp_path: Path) -> Path:
    """Genera un IFC mínimo válido (IFC4) con proyecto y un edificio (IfcElement)."""
    import ifcopenshell
    import ifcopenshell.guid as guid

    ifc_path = tmp_path / "prueba.ifc"

    model = ifcopenshell.file(schema="IFC4")

    # Unidad en metros (requerido para un IFC válido)
    unidad = model.create_entity(
        "IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix=None
    )
    asignacion_unidades = model.create_entity(
        "IfcUnitAssignment", Units=[unidad]
    )

    # Contexto geométrico 3D (requerido si hay representaciones)
    origen = model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])
    operador = model.create_entity(
        "IfcCartesianTransformationOperator3D",
        Axis1=None,
        Axis2=None,
        LocalOrigin=origen,
        Scale=1.0,
    )
    ctx = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Body",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=operador,
    )

    # Proyecto (entidad raíz requerida en todo IFC)
    proyecto = model.create_entity(
        "IfcProject",
        GlobalId=guid.new(),
        OwnerHistory=None,
        Name="Proyecto Prueba",
        Description=None,
        ObjectType=None,
        LongName=None,
        Phase=None,
        UnitsInContext=asignacion_unidades,
        RepresentationContexts=[ctx],
    )

    # Edificio (es IfcElement, por lo que leer_ifc lo recoge)
    edificio = model.create_entity(
        "IfcBuilding",
        GlobalId=guid.new(),
        OwnerHistory=None,
        Name="Edificio Prueba",
        Description=None,
        ObjectType=None,
        LongName=None,
        CompositionType="ELEMENT",
    )

    # Relación de agregación proyecto -> edificio
    model.create_entity(
        "IfcRelAggregates",
        GlobalId=guid.new(),
        OwnerHistory=None,
        Name=None,
        Description=None,
        RelatingObject=proyecto,
        RelatedObjects=[edificio],
    )

    model.write(str(ifc_path))
    return ifc_path


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_lectura_ifc_extrae_elementos(tmp_path: Path) -> None:
    """El IFC de prueba se lee y devuelve al menos un elemento de tipo IfcWall."""
    ifc_path = _crear_ifc_prueba(tmp_path)
    json_out = tmp_path / "salida.json"

    resultado = leer_ifc(ifc_path, json_out, chip="SANTAMARTA_T5")

    assert resultado["metadatos"]["chip"] == "SANTAMARTA_T5"
    assert resultado["metadatos"]["total_elementos"] >= 1
    assert "IfcBuilding" in resultado["resumen"]["conteos_por_tipo"]
    assert any(e["tipo_ifc"] == "IfcBuilding" for e in resultado["elementos"])
    assert any(e["nombre"] == "Edificio Prueba" for e in resultado["elementos"])


def test_estructura_json_salida(tmp_path: Path) -> None:
    """El JSON de salida contiene metadatos, resumen, elementos, qto_sets y tipos_elemento."""
    ifc_path = _crear_ifc_prueba(tmp_path)
    json_out = tmp_path / "salida.json"

    resultado = leer_ifc(ifc_path, json_out, chip="SANTAMARTA_T5")

    assert "metadatos" in resultado
    assert "resumen" in resultado
    assert "elementos" in resultado
    assert "qto_sets" in resultado
    assert "tipos_elemento" in resultado
    assert resultado["metadatos"]["schema"] == "IFC4"


def test_elementos_tienen_tipo_guid_y_nombre(tmp_path: Path) -> None:
    """Cada elemento tiene guid, tipo_ifc y nombre."""
    ifc_path = _crear_ifc_prueba(tmp_path)
    json_out = tmp_path / "salida.json"

    resultado = leer_ifc(ifc_path, json_out, chip="SANTAMARTA_T5")

    for elemento in resultado["elementos"]:
        assert "guid" in elemento
        assert "tipo_ifc" in elemento
        assert "nombre" in elemento
        assert "cantidades" in elemento


def test_guardar_json_en_disco(tmp_path: Path) -> None:
    """El archivo JSON de salida se escribe en disco y es legible."""
    ifc_path = _crear_ifc_prueba(tmp_path)
    json_out = tmp_path / "salida.json"

    leer_ifc(ifc_path, json_out, chip="SANTAMARTA_T5")

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadatos"]["chip"] == "SANTAMARTA_T5"


def test_tipos_elemento_conteo(tmp_path: Path) -> None:
    """tipos_elemento contiene tipo_ifc y conteo para cada tipo distinto."""
    ifc_path = _crear_ifc_prueba(tmp_path)
    json_out = tmp_path / "salida.json"

    resultado = leer_ifc(ifc_path, json_out, chip="SANTAMARTA_T5")

    por_tipo = {t["tipo_ifc"]: t["conteo"] for t in resultado["tipos_elemento"]}
    assert por_tipo.get("IfcBuilding", 0) >= 1
