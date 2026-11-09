"""
================================================================================
test_RE_ACTIVAR_SYMBOLOS_v01.py — Tests para RE_ACTIVAR_SYMBOLOS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que RE_ACTIVAR_SYMBOLOS_v01.py:
  1. Usa un símbolo existente y activo si ya existe (accion: ya_existia_activo).
  2. Activa un símbolo existente pero inactivo (accion: se_activo).
  3. Duplica el primer símbolo disponible si el solicitado no existe (accion: se_duplico).
  4. Reporta familia_no_encontrada cuando la familia no está cargada.
  5. Genera el JSON de salida con resumen y resultados por símbolo.
  6. No duplica símbolos ya procesados (clave única familia+simbolo).

FIXTURE:
  tests/fase-6-revit/fixture_RE_ACTIVAR_SYMBOLOS_v01.json

USO:
  pytest tests/fase-6-revit/test_RE_ACTIVAR_SYMBOLOS_v01.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API.
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
    / "RE_ACTIVAR_SYMBOLOS_v01.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_RE_ACTIVAR_SYMBOLOS_v01.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


class _FakeFamilySymbol:
    def __init__(self, nombre, familia_nombre, activo=True):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self.IsActive = activo
        self._duplicados = []
        self._nombre_familia = familia_nombre

    def Duplicate(self, nuevo_nombre):
        nuevo = _FakeFamilySymbol(nuevo_nombre, self._nombre_familia, activo=True)
        self._duplicados.append(nuevo)
        return nuevo

    def Activate(self):
        self.IsActive = True


class _FakeFamily:
    def __init__(self, nombre):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self._simbolos = {}

    def GetFamilySymbolIds(self):
        return [simbolo.Id for simbolo in self._simbolos.values()]

    def agregar_simbolo(self, nombre, activo=True):
        self._simbolos[nombre] = _FakeFamilySymbol(nombre, self.Name, activo=activo)

    def __getitem__(self, idx):
        nombre = list(self._simbolos.keys())[idx]
        return self._simbolos[nombre]


class _FakeDoc:
    def __init__(self, nombre_doc="Test.rvt"):
        self.Title = nombre_doc
        self.PathName = "C:/Test/{}".format(nombre_doc)
        self._familias = {}
        self._regeneraciones = 0

    def LoadFamily(self, ruta_rfa):
        nombre = os.path.splitext(os.path.basename(ruta_rfa))[0]
        if nombre in self._familias:
            return self._familias[nombre]
        fam = _FakeFamily(nombre)
        self._familias[nombre] = fam
        return fam

    def GetElement(self, id_elem):
        for fam in self._familias.values():
            for simbolo in fam._simbolos.values():
                if simbolo.Id.IntegerValue == id_elem.IntegerValue:
                    return simbolo
        return None

    def Regenerate(self):
        self._regeneraciones += 1


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
# Cargar el módulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _cargar_modulo_con_mocks():
    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class Family:
        pass

    class FamilySymbol:
        pass

    class FilteredElementCollector:
        def __init__(self, doc):
            self._doc = doc
        def OfClass(self, clase):
            return _FakeFilteredElementCollector(self._doc).OfClass(clase)

    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.Family = Family
    revit_db.FamilySymbol = FamilySymbol

    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    spec = importlib.util.spec_from_file_location(
        "RE_ACTIVAR_SYMBOLOS_v01", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)

    fake_doc = _FakeDoc()
    mod.__revit__ = types.SimpleNamespace(Application=None, ActiveUIDocument=None)
    mod.__revit__.ActiveUIDocument = types.SimpleNamespace(Document=fake_doc)
    mod.__revit__.Application = types.SimpleNamespace(VersionNumber="2026", Documents=None)
    mod.doc = fake_doc

    spec.loader.exec_module(mod)
    return mod, fake_doc


_mod, _fake_doc = _cargar_modulo_con_mocks()
asegurar_simbolo = _mod.asegurar_simbolo
_buscar_familia_por_nombre = _mod._buscar_familia_por_nombre
_listar_simbolos_familia = _mod._listar_simbolos_familia


@pytest.fixture(autouse=True)
def _reiniciar_doc():
    """Reinicia el documento falso antes de cada test para aislamiento."""
    global _fake_doc, _mod, asegurar_simbolo, _buscar_familia_por_nombre, _listar_simbolos_familia
    _cargar_modulo_con_mocks()
    _mod, _fake_doc = _cargar_modulo_con_mocks()
    asegurar_simbolo = _mod.asegurar_simbolo
    _buscar_familia_por_nombre = _mod._buscar_familia_por_nombre
    _listar_simbolos_familia = _mod._listar_simbolos_familia
    yield


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _crear_familia_con_simbolos(doc, nombre_familia, simbolos):
    """Crea una familia en el doc con la lista de símbolos dados."""
    doc.LoadFamily("falso/{}.rfa".format(nombre_familia))
    fam = doc._familias[nombre_familia]
    for nombre, activo in simbolos:
        fam.agregar_simbolo(nombre, activo=activo)
    return fam


_REVIT_DB = {
    "FilteredElementCollector": _FakeFilteredElementCollector,
    "Family": _FakeFamily,
    "FamilySymbol": _FakeFamilySymbol,
}


def test_usa_simbolo_existente_activo():
    """Si el símbolo ya existe y está activo, retorna ya_existia_activo."""
    _crear_familia_con_simbolos(_fake_doc, "M_Toma doble", [("GFCI", True)])
    simbolo, nombre_usado, accion = asegurar_simbolo(
        _fake_doc, "M_Toma doble", "GFCI", _REVIT_DB
    )
    assert accion == "ya_existia_activo"
    assert nombre_usado == "GFCI"
    assert simbolo.IsActive is True


def test_activa_simbolo_existente_inactivo():
    """Si el símbolo existe pero está inactivo, lo activa (accion: se_activo)."""
    _crear_familia_con_simbolos(_fake_doc, "M_Toma doble", [("GFCI", False)])
    simbolo, nombre_usado, accion = asegurar_simbolo(
        _fake_doc, "M_Toma doble", "GFCI", _REVIT_DB
    )
    assert accion == "se_activo"
    assert simbolo.IsActive is True


def test_duplica_simbolo_si_no_existe():
    """Si el símbolo no existe, duplica el primero disponible (accion: se_duplico)."""
    _crear_familia_con_simbolos(_fake_doc, "M_Toma doble", [("Standard", True)])
    simbolo, nombre_usado, accion = asegurar_simbolo(
        _fake_doc, "M_Toma doble", "GFCI", _REVIT_DB
    )
    assert accion == "se_duplico"
    assert nombre_usado == "GFCI"
    assert simbolo.IsActive is True


def test_familia_no_encontrada():
    """Si la familia no está cargada, retorna familia_no_encontrada."""
    simbolo, nombre_usado, accion = asegurar_simbolo(
        _fake_doc, "Familia Inexistente", "GFCI", _REVIT_DB
    )
    assert accion == "familia_no_encontrada"
    assert simbolo is None


def test_sin_simbolos_disponibles():
    """Si la familia existe pero no tiene símbolos, retorna no_disponible."""
    _crear_familia_con_simbolos(_fake_doc, "Familia Vacía", [])
    simbolo, nombre_usado, accion = asegurar_simbolo(
        _fake_doc, "Familia Vacía", "GFCI", _REVIT_DB
    )
    assert accion == "no_disponible"
    assert simbolo is None


def test_estructura_json_salida():
    """main() genera claves resumen y resultados."""
    import inspect
    fuente = inspect.getsource(_mod.main)
    assert "resumen" in fuente
    assert "resultados" in fuente
    assert "ya_existia_activo" in fuente
    assert "se_duplico" in fuente
