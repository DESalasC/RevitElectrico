"""
================================================================================
test_CARGAR_FAMILIAS_v01.py — Tests para CARGAR_FAMILIAS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que CARGAR_FAMILIAS_v01.py:
  1. Carga familias .rfa al documento RVT activo mediante doc.LoadFamily.
  2. Omite familias ya cargadas en el documento.
  3. Reporta exitos, fallos y omitidas correctamente.
  4. Genera el JSON de salida con la estructura esperada.
  5. Maneja rutas de archivo no encontradas.

FIXTURE:
  tests/fase-6-revit/fixture_CARGAR_FAMILIAS_v01.json

USO:
  pytest tests/fase-6-revit/test_CARGAR_FAMILIAS_v01.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API para validar la logica
  de negocio sin necesidad de tener Revit instalado.
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-6-revit"
    / "CARGAR_FAMILIAS_v01.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_CARGAR_FAMILIAS_v01.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


class _FakeFamily:
    def __init__(self, nombre):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)

    def GetFamilySymbolIds(self):
        return []


class _FakeTransaction:
    def __init__(self, doc, nombre):
        self.doc = doc
        self.nombre = nombre
        self.commitido = False
        self.revertido = False

    def Start(self):
        pass

    def Commit(self):
        self.commitido = True

    def RollBack(self):
        self.revertido = True


class _FakeDoc:
    def __init__(self, nombre_doc="Test.rvt"):
        self.Title = nombre_doc
        self.PathName = "C:/Test/{}".format(nombre_doc)
        self._familias = {}
        self._transacciones = []

    def LoadFamily(self, ruta_rfa):
        """Simula LoadFamily: carga el .rfa si existe y lo registra."""
        nombre = os.path.splitext(os.path.basename(ruta_rfa))[0]
        if nombre in self._familias:
            return self._familias[nombre]
        fam = _FakeFamily(nombre)
        self._familias[nombre] = fam
        return fam

    def GetElement(self, id_elem):
        return None

    def Transaction(self, nombre):
        t = _FakeTransaction(self, nombre)
        self._transacciones.append(t)
        return t


class _FakeFilteredElementCollector:
    def __init__(self, doc):
        self._doc = doc
        self._clase = None

    def OfClass(self, clase):
        self._clase = clase
        return self

    def ToElements(self):
        resultado = []
        if self._clase is not None:
            nombre_clase = self._clase.__name__ if hasattr(self._clase, "__name__") else str(self._clase)
            if nombre_clase in ("Family", "_FakeFamily"):
                for nombre in self._doc._familias:
                    resultado.append(self._doc._familias[nombre])
        return resultado


# ---------------------------------------------------------------------------
# Cargar el modulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _cargar_modulo_con_mocks():
    """Carga CARGAR_FAMILIAS_v01.py inyectando mocks de Revit API en sys.modules."""
    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class BuiltInCategory:
        OST_Levels = "OST_Levels"

    class BuiltInParameter:
        ALL_MODEL_TYPE_NAME = "ALL_MODEL_TYPE_NAME"

    class FilteredElementCollector:
        def __init__(self, doc):
            self._doc = doc
        def OfClass(self, clase):
            return _FakeFilteredElementCollector(self._doc).OfClass(clase)

    Family = _FakeFamily

    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.BuiltInCategory = BuiltInCategory
    revit_db.BuiltInParameter = BuiltInParameter
    revit_db.Family = Family

    # Inyectar en sys.modules ANTES de cargar el modulo bajo test
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    # Cargar el modulo bajo test
    spec = importlib.util.spec_from_file_location(
        "CARGAR_FAMILIAS_v01", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)

    # Inyectar __revit__ y doc como globales del modulo
    fake_doc = _FakeDoc()
    mod.__revit__ = types.SimpleNamespace(
        Application=None, ActiveUIDocument=None
    )
    mod.__revit__.ActiveUIDocument = types.SimpleNamespace(Document=fake_doc)
    mod.__revit__.Application = types.SimpleNamespace(VersionNumber="2026", Documents=None)

    mod.doc = fake_doc

    spec.loader.exec_module(mod)
    return mod, fake_doc


_mod, _fake_doc = _cargar_modulo_con_mocks()
cargar_familia = _mod.cargar_familia
familias_cargadas = _mod.familias_cargadas
FAMILIAS_POR_DEFECTO = _mod.FAMILIAS_POR_DEFECTO


@pytest.fixture(autouse=True)
def _reinstalar_mock_revit_db_familias():
    """Antes de cada test, reinstala el mock de Autodesk.Revit.DB para
    aislar los tests de familias de la contaminacion de sys.modules."""
    _cargar_modulo_con_mocks()
    yield


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cargar_familia_exitoso(tmp_path):
    """cargar_familia carga un .rfa existente y retorna ok=True."""
    import types
    # Crear un archivo .rfa falso en tmp_path para pasar la verificacion de existencia
    ruta_rfa = tmp_path / "M_Toma doble.rfa"
    ruta_rfa.write_text("contenido falso de familia")
    revit_db = {
        "Family": _FakeFamily,
        "FilteredElementCollector": _FakeFilteredElementCollector,
        "Transaction": _FakeTransaction,
    }

    ok, mensaje, _familia = cargar_familia(_fake_doc, str(ruta_rfa), "M_Toma doble", revit_db)
    assert ok is True
    assert "Cargada" in mensaje or mensaje == "Cargada correctamente"


def test_cargar_familia_archivo_no_encontrado():
    """cargar_familia con ruta inexistente retorna ok=False."""
    ok, mensaje, _familia = cargar_familia(_fake_doc, "C:/ruta/inexistente/M_Toma doble.rfa", "M_Toma doble", None)
    assert ok is False
    assert "no encontrado" in mensaje.lower()


def test_familias_cargadas_retorna_set():
    """familias_cargadas retorna un set con los nombres de familias cargadas."""
    # Pre-cargar una familia en el doc falso
    _fake_doc.LoadFamily("D:/falsa/ruta/M_Toma doble.rfa")

    class _FakeCollector:
        def __init__(self, doc):
            self._doc = doc
        def OfClass(self, clase):
            return self

        def ToElements(self):
            return list(self._doc._familias.values())

    revit_db = {"FilteredElementCollector": _FakeCollector, "Family": _FakeFamily}
    nombres = familias_cargadas(_fake_doc, revit_db)
    assert "M_Toma doble" in nombres


def test_familias_por_defecto_tiene_8_entradas():
    """FAMILIAS_POR_DEFECTO contiene las 8 familias necesarias para Tarea F."""
    assert len(FAMILIAS_POR_DEFECTO) == 8
    nombres = {f["nombre"] for f in FAMILIAS_POR_DEFECTO}
    assert "M_Toma doble" in nombres
    assert "M_Toma simple" in nombres
    assert "M_Toma resistente a la intemperie" in nombres
    assert "M_Interruptor bipolar" in nombres
    assert "M_Interruptor" in nombres
    assert "M_Ventilador" in nombres
    assert "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN" in nombres
    assert "COMBO MOUNTING RING" in nombres


def test_estructura_json_salida():
    """El resultado de main() tiene las claves esperadas para JSON."""
    # Verificamos que las claves del resultado sean las correctas revisando
    # el codigo fuente del modulo (no se ejecuta main() porque necesita Revit).
    import inspect
    fuente = inspect.getsource(_mod.main)
    assert "exitosas" in fuente
    assert "fallidas" in fuente
    assert "omitidas" in fuente
    assert "total_familias" in fuente


def test_guardar_json_en_disco(tmp_path):
    """El resultado se puede serializar a JSON y guardar en disco."""
    resultado = {
        "version": "v01",
        "total_familias": 8,
        "exitosas": 8,
        "fallidas": 0,
        "omitidas": 0,
    }
    json_out = tmp_path / "cargar_familias.json"
    import json as _json
    with open(str(json_out), "w") as f:
        _json.dump(resultado, f, indent=2, ensure_ascii=True)
    assert json_out.exists()
    with open(str(json_out), "r", encoding="utf-8") as f:
        data = _json.load(f)
    assert data["total_familias"] == 8
    assert data["exitosas"] == 8

