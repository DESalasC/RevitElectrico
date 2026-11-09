"""
================================================================================
test_RE_NIVELES_RVT_v01.py — Tests para RE_NIVELES_RVT_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que RE_NIVELES_RVT_v01.py:
  1. Lista los niveles del documento con nombre, id y elevación.
  2. Detecta si existe un nivel por nombre (case-insensitive).
  3. Crea el nivel "Piso 5" si falta (13.22 m / 43.37 pies).
  4. Mapea un nivel desde un RVT referenciado (elevación en metros).
  5. Genera el resultado consolidado listo para JSON.

FIXTURE:
  tests/fase-6-revit/fixture_RE_NIVELES_RVT_v01.json

USO:
  pytest tests/fase-6-revit/test_RE_NIVELES_RVT_v01.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API para validar la lógica
  de negocio sin necesidad de tener Revit instalado.
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-6-revit"
    / "RE_NIVELES_RVT_v01.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_RE_NIVELES_RVT_v01.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


class _FakeLevel:
    def __init__(self, nombre, elevacion_pies):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self.IsElementType = False
        self.Elevation = elevacion_pies

    @staticmethod
    def Create(doc, elevacion_pies):
        """Crea un nivel y lo registra en el documento falso."""
        nombre = "Nivel {}".format(elevacion_pies)
        # Evitar duplicados por nombre
        for nombre_existente, nivel_existente in doc._niveles.items():
            if abs(nivel_existente.Elevation - elevacion_pies) < 0.001:
                return nivel_existente
        nivel = _FakeLevel(nombre, elevacion_pies)
        doc._niveles[nombre] = nivel
        return nivel


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
        self._niveles = {}
        self._siguiente_id = 1000
        self.Create = _FakeDocCreate(self)

    def registrar_nivel(self, nombre, elevacion_m):
        elevacion_pies = elevacion_m / 0.3048
        self._niveles[nombre] = _FakeLevel(nombre, elevacion_pies)

    def GetElement(self, id_elem):
        return None

    def Regenerate(self):
        pass


class _FakeDocCreate:
    def __init__(self, doc):
        self._doc = doc

    def NewFamilyInstance(self, *args, **kwargs):
        return None


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
            if nombre_clase in ("Level", "_FakeLevel"):
                for nombre in self._doc._niveles:
                    resultado.append(self._doc._niveles[nombre])
        return resultado


class _FakeUnitUtils:
    @staticmethod
    def ConvertToInternalUnits(valor, tipo_id):
        # mm -> pies: valor / 304.8
        return valor / 304.8


class _FakeUnitTypeId:
    Millimeters = "Millimeters"


# ---------------------------------------------------------------------------
# Cargar el módulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _cargar_modulo_con_mocks():
    """Carga RE_NIVELES_RVT_v01.py inyectando mocks de Revit API en sys.modules."""

    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class BuiltInCategory:
        OST_Levels = "OST_Levels"

    class BuiltInParameter:
        ALL_MODEL_TYPE_NAME = "ALL_MODEL_TYPE_NAME"

    class Structure:
        class StructuralType:
            NonStructural = "NonStructural"

    class FilteredElementCollector:
        def __init__(self, doc):
            self._doc = doc
        def OfClass(self, clase):
            return _FakeFilteredElementCollector(self._doc).OfClass(clase)
        def OfCategory(self, categoria):
            return _FakeFilteredElementCollector(self._doc).OfCategory(categoria)

    Level = _FakeLevel

    class Transaction:
        def __init__(self, doc, nombre):
            self._doc = doc
            self._nombre = nombre
        def Start(self):
            pass
        def Commit(self):
            pass
        def RollBack(self):
            pass

    class XYZ:
        def __init__(self, x, y, z):
            self.X = x
            self.Y = y
            self.Z = z

    UnitUtils = _FakeUnitUtils

    UnitTypeId = _FakeUnitTypeId

    revit_db.BuiltInCategory = BuiltInCategory
    revit_db.BuiltInParameter = BuiltInParameter
    revit_db.Structure = Structure
    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.Level = Level
    revit_db.Transaction = Transaction
    revit_db.XYZ = XYZ
    revit_db.UnitUtils = UnitUtils
    revit_db.UnitTypeId = UnitTypeId

    # Inyectar en sys.modules ANTES de cargar el módulo bajo test
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    # Cargar el módulo bajo test
    spec = importlib.util.spec_from_file_location(
        "RE_NIVELES_RVT_v01", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)

    # Inyectar __revit__ y doc como globales del módulo
    fake_doc = _FakeDoc()
    mod.__revit__ = types.SimpleNamespace(Application=None, ActiveUIDocument=None)
    mod.__revit__.ActiveUIDocument = types.SimpleNamespace(Document=fake_doc)
    mod.__revit__.Application = types.SimpleNamespace(VersionNumber="2026", Documents=None)

    mod.doc = fake_doc

    spec.loader.exec_module(mod)
    return mod, fake_doc


_mod, _fake_doc = _cargar_modulo_con_mocks()
_listar_niveles = _mod._listar_niveles
_nivel_existe = _mod._nivel_existe
_obtener_nivel_por_nombre = _mod._obtener_nivel_por_nombre
_crear_nivel = _mod._crear_nivel
asegurar_nivel_piso5 = _mod.asegurar_nivel_piso5
mapear_nivel_referenciado = _mod.mapear_nivel_referenciado
listar_niveles_resultado = _mod.listar_niveles_resultado
mm_a_pies = _mod._mm_a_pies
_nivel_coincide = _mod._nivel_coincide


@pytest.fixture(autouse=True)
def _reinstalar_mock_revit_db_niveles():
    """Antes de cada test, reinstala el mock de Autodesk.Revit.DB para
    aislar los tests de niveles de la contaminacion de sys.modules dejada
    por otros modulos de prueba (por ejemplo, test_CREAR_TIPOS_CONDUIT_v04)."""
    _cargar_modulo_con_mocks()
    yield


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _registrar_niveles_fixture(doc, fixture):
    """Registra los niveles del fixture en el doc falso."""
    for n in fixture.get("niveles_entrada", []):
        doc.registrar_nivel(n["nombre"], n["elevacion_m"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_listar_niveles_retorna_lista_con_nombre_elevacion():
    """_listar_niveles devuelve una lista de dicts con id, nombre y elevacion_m."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    niveles = _listar_niveles(_fake_doc)
    assert isinstance(niveles, list)
    assert len(niveles) == len(fixture["niveles_entrada"])

    nombres = {n["nombre"] for n in niveles}
    for esperado in fixture["niveles_esperados"]:
        assert esperado in nombres

    # Cada nivel debe tener id, nombre, elevacion_pies, elevacion_m
    for n in niveles:
        assert "id" in n
        assert "nombre" in n
        assert "elevacion_pies" in n
        assert "elevacion_m" in n


def test_nivel_existe_devuelve_true_para_piso5():
    """_nivel_existe devuelve True para un nivel que existe (case-insensitive)."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    assert _nivel_existe(_fake_doc, "Piso 5") is True
    assert _nivel_existe(_fake_doc, "piso 5") is True  # case-insensitive
    assert _nivel_existe(_fake_doc, "PISO 5") is True


def test_nivel_existe_devuelve_false_para_nivel_ausente():
    """_nivel_existe devuelve False para un nivel que no existe."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    assert _nivel_existe(_fake_doc, fixture["nivel_ausente"]) is False
    assert _nivel_existe(_fake_doc, "Inexistente") is False


def test_obtener_nivel_por_nombre_retorna_elemento():
    """_obtener_nivel_por_nombre retorna el elemento Level o None."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    nivel = _obtener_nivel_por_nombre(_fake_doc, "Piso 5")
    assert nivel is not None
    assert _nivel_coincide(nivel.Name, "Piso 5")

    assert _obtener_nivel_por_nombre(_fake_doc, "Inexistente") is None


def test_crear_nivel_dentro_transaccion():
    """_crear_nivel crea un nivel dentro de una Transaction y lo registra."""
    doc = _FakeDoc()
    revit_db = sys.modules["Autodesk.Revit.DB"]

    antes = len(doc._niveles)
    nuevo = _crear_nivel(doc, "Nivel Nuevo", 10.0)
    despues = len(doc._niveles)

    assert despues == antes + 1
    assert nuevo is not None
    assert nuevo.Name == "Nivel Nuevo"
    assert doc.Create  # transacción usada


def test_asegurar_nivel_piso5_crea_si_falta():
    """asegurar_nivel_piso5 crea el nivel si no existe y retorna su ElementId."""
    doc = _FakeDoc()
    # Sin "Piso 5" registrado
    assert _nivel_existe(doc, "Piso 5") is False

    piso5_id = asegurar_nivel_piso5(doc, elevacion_m=13.22)
    assert piso5_id is not None
    assert _nivel_existe(doc, "Piso 5") is True


def test_asegurar_nivel_piso5_no_duplica_si_ya_existe():
    """asegurar_nivel_piso5 no crea duplicado si el nivel ya existe."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    antes = len(_fake_doc._niveles)
    piso5_id = asegurar_nivel_piso5(_fake_doc, elevacion_m=13.22)
    despues = len(_fake_doc._niveles)

    assert antes == despues  # no se creó duplicado
    assert piso5_id is not None


def test_mapear_nivel_referenciado_retorna_elevacion():
    """mapear_nivel_referenciado busca el nivel en el RVT referenciado y retorna elevación."""
    doc_ref = _FakeDoc()
    doc_ref.registrar_nivel("Piso 5", 13.22)
    doc_ref.registrar_nivel("Nivel 1", 0.0)

    elevacion, encontrado = mapear_nivel_referenciado(
        _fake_doc, doc_ref, "Piso 5"
    )
    assert encontrado is True
    assert elevacion is not None
    assert abs(elevacion - 13.22) < 0.01

    # Nivel que no existe en el referenciado
    elevacion2, encontrado2 = mapear_nivel_referenciado(
        _fake_doc, doc_ref, "Piso 99"
    )
    assert encontrado2 is False


def test_listar_niveles_resultado_estructura_json():
    """listar_niveles_resultado devuelve un dict listo para JSON."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    resultado = listar_niveles_resultado(_fake_doc)
    assert "niveles" in resultado
    assert "total_niveles" in resultado
    assert "nivel_piso5" in resultado
    assert "piso5_existe" in resultado
    assert "piso5_id" in resultado
    assert "elevacion_piso5_m" in resultado
    assert "elevacion_piso5_pies" in resultado
    assert resultado["total_niveles"] == len(fixture["niveles_entrada"])
    assert resultado["nivel_piso5"] == "Piso 5"
    assert resultado["piso5_existe"] is True


def test_mm_a_pies_conversion():
    """_mm_a_pies convierte correctamente milimetros a pies."""
    revit_db = sys.modules["Autodesk.Revit.DB"]
    # 304.8 mm = 1 pie
    pies = mm_a_pies(304.8, revit_db)
    assert abs(pies - 1.0) < 0.001

    # 13.22 m = 13220 mm -> ~43.37 pies
    pies_13m22 = mm_a_pies(13220.0, revit_db)
    assert abs(pies_13m22 - 43.37) < 0.1


def test_guardar_json_en_disco(tmp_path):
    """El resultado se puede serializar a JSON y guardar en disco."""
    fixture = _cargar_fixture()
    _registrar_niveles_fixture(_fake_doc, fixture)

    resultado = listar_niveles_resultado(_fake_doc)
    json_out = tmp_path / "niveles.json"

    import os

    dirpath = os.path.dirname(str(json_out))
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)

    import json as _json
    with open(str(json_out), "w") as f:
        _json.dump(resultado, f, indent=2, ensure_ascii=True)

    assert json_out.exists()
    with open(str(json_out), "r", encoding="utf-8") as f:
        data = _json.load(f)
    assert data["total_niveles"] == len(fixture["niveles_entrada"])
    assert data["piso5_existe"] is True
