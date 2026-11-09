"""
================================================================================
test_CREAR_TIPOS_CONDUIT_v04.py — Tests para CREAR_TIPOS_CONDUIT_v04.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que CREAR_TIPOS_CONDUIT_v04.py:
  1. Define el mapeo TIPO_CONDUIT_MAP con los 5 tipos de conducto.
  2. Convierte mm <-> pies internos de Revit correctamente.
  3. Obtiene el nombre de un tipo de conducto (Name o SYMBOL_NAME_PARAM).
  4. Crea los 5 tipos de conducto en un documento que ya tiene categoria
     OST_Conduit disponible (rama feliz por duplicacion).
  5. No crea duplicados si el tipo ya existe (rama existente).
  6. Maneja el documento sin categoria ConduitType (categoria no disponible).
  7. Guarda el reporte JSON en disco.

FIXTURE:
  tests/fase-6-revit/fixture_CREAR_TIPOS_CONDUIT_v04.json

USO:
  pytest tests/fase-6-revit/test_CREAR_TIPOS_CONDUIT_v04.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API para validar la lógica
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
    / "CREAR_TIPOS_CONDUIT_v04.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_CREAR_TIPOS_CONDUIT_v04.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeElementId:
    InvalidElementId = None  # se inicializa abajo

    def __init__(self, valor):
        self.IntegerValue = valor

    def __eq__(self, other):
        if isinstance(other, _FakeElementId):
            return self.IntegerValue == other.IntegerValue
        return False

    def __hash__(self):
        return hash(self.IntegerValue)

    def ToString(self):
        return str(self.IntegerValue)


_FakeElementId.InvalidElementId = _FakeElementId(-1)


class _FakeParameter:
    def __init__(self, nombre, valor=None, readonly=False):
        self.Definition = _FakeDefinition(nombre)
        self._valor = valor
        self.IsReadOnly = readonly

    def AsString(self):
        return self._valor if isinstance(self._valor, str) else None

    def AsDouble(self):
        try:
            return float(self._valor)
        except Exception:
            return None

    def Set(self, valor):
        if self.IsReadOnly:
            return False
        self._valor = valor
        return True


class _FakeDefinition:
    def __init__(self, nombre):
        self.Name = nombre


class _FakeConduitType:
    def __init__(self, nombre, id_entero, doc):
        self.Name = nombre
        self.Id = _FakeElementId(id_entero)
        self.IsElementType = True
        self._doc = doc
        self._parametros = {
            "RBS_CONDUIT_DIAMETER_PARAM": _FakeParameter(
                "RBS_CONDUIT_DIAMETER_PARAM", None, readonly=False
            ),
            "SYMBOL_NAME_PARAM": _FakeParameter("SYMBOL_NAME_PARAM", nombre),
        }

    def Duplicate(self, nuevo_nombre):
        nuevo_id = self._doc._siguiente_id_conduit()
        nuevo = _FakeConduitType(nuevo_nombre, nuevo_id, self._doc)
        self._doc._conduit_types[nuevo_nombre] = nuevo
        return nuevo.Id

    def get_Parameter(self, param_builtin):
        # BuiltInParameter se recibe como enum; comparar por valor/ nombre
        nombre_param = str(param_builtin)
        return self._parametros.get(nombre_param)

    @property
    def Parameters(self):
        return list(self._parametros.values())


class _FakeFilteredElementCollector:
    def __init__(self, doc):
        self._doc = doc
        self._clase = None
        self._filtro = None
        self._categoria = None
        self._element_type_only = False

    def OfClass(self, clase):
        self._clase = clase
        return self

    def OfCategory(self, categoria):
        self._categoria = categoria
        return self

    def WhereElementIsElementType(self):
        self._element_type_only = True
        return self

    def WherePasses(self, filtro):
        self._filtro = filtro
        return self

    def ToElements(self):
        # Filtro por categoria OST_Conduit (simbolos de familia de conducto)
        if self._categoria is not None and str(self._categoria) == _FakeBuiltInCategory.OST_Conduit:
            if self._element_type_only:
                return list(self._doc._conduit_types.values())
            return list(self._doc._conduit_types.values())
        # Filtro por clase ConduitType
        nombre_clase = (
            self._clase.__name__ if hasattr(self._clase, "__name__") else str(self._clase)
        )
        if (
            self._filtro is not None
            and hasattr(self._filtro, "categoria")
            and self._filtro.categoria == _FakeBuiltInCategory.OST_ConduitType
        ):
            return list(self._doc._conduit_types.values())
        if nombre_clase in ("ConduitType", "_FakeConduitType"):
            return list(self._doc._conduit_types.values())
        if nombre_clase in ("Level", "_FakeLevel"):
            return list(self._doc._niveles.values())
        return []

    def FirstElement(self):
        elementos = self.ToElements()
        return elementos[0] if elementos else None


class _FakeLevel:
    def __init__(self, nombre, elevacion_pies):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self.Elevation = elevacion_pies


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
    def __init__(self, nombre_doc="Test.rvt", con_categoria_conduit=True):
        self.Title = nombre_doc
        self.PathName = "C:/Test/{}".format(nombre_doc)
        self._niveles = {}
        self._conduit_types = {}
        self._contador_id_conduit = 1000
        self.Create = _FakeDocCreate(self)
        self.con_categoria_conduit = con_categoria_conduit

    def _siguiente_id_conduit(self):
        self._contador_id_conduit += 1
        return self._contador_id_conduit

    def registrar_conduit_tipo(self, nombre):
        self._conduit_types[nombre] = _FakeConduitType(
            nombre, self._siguiente_id_conduit(), self
        )

    def registrar_nivel(self, nombre, elevacion_m):
        elevacion_pies = elevacion_m / 0.3048
        self._niveles[nombre] = _FakeLevel(nombre, elevacion_pies)

    def GetElement(self, id_elem):
        id_val = getattr(id_elem, "IntegerValue", id_elem)
        for ct in self._conduit_types.values():
            if ct.Id.IntegerValue == id_val:
                return ct
        for niv in self._niveles.values():
            if niv.Id.IntegerValue == id_val:
                return niv
        return None

    def Regenerate(self):
        pass


class _FakeDocCreate:
    def __init__(self, doc):
        self._doc = doc

    def NewFamilyInstance(self, *args, **kwargs):
        return None


class _FakeLine:
    @staticmethod
    def CreateBound(p1, p2):
        return _FakeCurve(p1, p2)


class _FakeCurve:
    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2


class _FakeXYZ:
    def __init__(self, x, y, z):
        self.X = x
        self.Y = y
        self.Z = z


class _FakeUnitUtils:
    @staticmethod
    def ConvertToInternalUnits(valor, tipo_id):
        # mm -> pies: valor / 304.8
        return valor / 304.8

    @staticmethod
    def ConvertFromInternalUnits(pies, tipo_id):
        return pies * 304.8


class _FakeUnitTypeId:
    Millimeters = "Millimeters"


class _FakeStructure:
    class StructuralType:
        NonStructural = "NonStructural"


class _FakeBuiltInCategory:
    OST_Conduit = "OST_Conduit"
    OST_ConduitType = "OST_ConduitType"
    OST_Ceilings = "OST_Ceilings"
    OST_Levels = "OST_Levels"


class _FakeBuiltInParameter:
    RBS_CONDUIT_DIAMETER_PARAM = "RBS_CONDUIT_DIAMETER_PARAM"
    SYMBOL_NAME_PARAM = "SYMBOL_NAME_PARAM"
    ALL_MODEL_INSTANCE_COMMENTS = "ALL_MODEL_INSTANCE_COMMENTS"


class _FakeFilteredElementCollectorMod:
    def __init__(self, doc):
        self._doc = doc

    def OfClass(self, clase):
        return _FakeFilteredElementCollector(self._doc).OfClass(clase)

    def OfCategory(self, categoria):
        return _FakeFilteredElementCollector(self._doc).OfCategory(categoria)

    def WherePasses(self, filtro):
        return _FakeFilteredElementCollector(self._doc).WherePasses(filtro)


class _FakeElementCategoryFilter:
    def __init__(self, categoria):
        self.categoria = categoria


# ---------------------------------------------------------------------------
# Cargar el módulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _mock_revit_db_completo():
    """Construye un mock completo de Autodesk.Revit.DB (incluye UnitUtils y
    UnitTypeId) para no dejar el modulo compartido contaminado para los tests
    de niveles (test_RE_NIVELES_RVT_v01.py), que leen sys.modules."""

    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class _FakeFilteredElementCollectorMod:
        def __init__(self, doc):
            self._doc = doc

        def OfClass(self, clase):
            return _FakeFilteredElementCollector(self._doc).OfClass(clase)

        def OfCategory(self, categoria):
            return _FakeFilteredElementCollector(self._doc).OfCategory(categoria)

        def WherePasses(self, filtro):
            return _FakeFilteredElementCollector(self._doc).WherePasses(filtro)

    revit_db.FilteredElementCollector = _FakeFilteredElementCollectorMod
    revit_db.BuiltInCategory = _FakeBuiltInCategory
    revit_db.BuiltInParameter = _FakeBuiltInParameter
    revit_db.Transaction = _FakeTransaction
    revit_db.ElementId = _FakeElementId
    revit_db.ElementCategoryFilter = _FakeElementCategoryFilter
    revit_db.UnitUtils = _FakeUnitUtils
    revit_db.UnitTypeId = _FakeUnitTypeId
    revit_db.XYZ = _FakeXYZ
    revit_db.Line = _FakeLine
    revit_db.Curve = _FakeCurve
    revit_db.Level = _FakeLevel
    revit_db.FamilySymbol = object
    revit_db.FamilyInstance = object
    revit_db.Structure = _FakeStructure
    revit_db.ConduitType = _FakeConduitType
    revit_db.Conduit = object

    return revit_db


@pytest.fixture(autouse=True)
def _reinstalar_mock_revit_db_completo():
    """Antes de cada test, reinstala un mock completo de Autodesk.Revit.DB para
    evitar que el mock de conduit (sin UnitUtils) contamine a los tests de
    niveles que comparten sys.modules."""
    _instalado = _mock_revit_db_completo()
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = _instalado
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"
    yield
    # Restaurar al finalizar para no afectar a otros modulos de test
    sys.modules["Autodesk.Revit.DB"] = _mock_revit_db_completo()


def _cargar_modulo_con_mocks():
    """Carga CREAR_TIPOS_CONDUIT_v04.py inyectando mocks de Revit API en sys.modules."""

    # Mock de 'clr' (no existe en CPython)
    clr_mock = types.ModuleType("clr")
    clr_mock.AddReference = lambda *args: None
    sys.modules["clr"] = clr_mock

    # Mock de 'System' (Int64)
    system_mock = types.ModuleType("System")
    system_mock.Int64 = int
    sys.modules["System"] = system_mock

    revit_db = _mock_revit_db_completo()

    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    spec = importlib.util.spec_from_file_location(
        "CREAR_TIPOS_CONDUIT_v04", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)

    fake_doc = _FakeDoc()
    mod.__revit__ = types.SimpleNamespace(
        Application=None,
        ActiveUIDocument=types.SimpleNamespace(Document=fake_doc),
    )
    mod.doc = fake_doc

    spec.loader.exec_module(mod)
    return mod, fake_doc


_mod, _fake_doc = _cargar_modulo_con_mocks()

TIPO_CONDUIT_MAP = _mod.TIPO_CONDUIT_MAP
crear_tipos_conduit = _mod.crear_tipos_conduit
_mm_a_pies = _mod._mm_a_pies
_pies_a_mm = _mod._pies_a_mm
_nombre_tipo_elemento = _mod._nombre_tipo_elemento
_buscar_param_comentario = _mod._buscar_param_comentario


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tipo_conduit_map_tiene_5_tipos():
    """TIPO_CONDUIT_MAP define exactamente 5 tipos de conducto."""
    assert len(TIPO_CONDUIT_MAP) == 5
    nombres = [t[0] for t in TIPO_CONDUIT_MAP]
    assert "Conduit 3/4\"" in nombres
    assert "Conduit 1\"" in nombres
    assert "Conduit 1-1/4\"" in nombres
    assert "Conduit 2\"" in nombres
    assert "Conduit 3\"" in nombres


def test_tipo_conduit_map_rangos_y_diametros():
    """Cada entrada del mapeo tiene rango de mm, pulgadas y diametro mm correctos."""
    esperado = {
        "Conduit 3/4\"":   (3, 4, "3/4\"",   19.05),
        "Conduit 1\"":     (5, 6, "1\"",     25.40),
        "Conduit 1-1/4\"": (7, 8, "1-1/4\"", 31.75),
        "Conduit 2\"":     (9, 11, "2\"",    50.80),
        "Conduit 3\"":    (12, 15, "3\"",    76.20),
    }
    for nombre, mm_min, mm_max, pulgadas, diametro_mm in TIPO_CONDUIT_MAP:
        assert (mm_min, mm_max, pulgadas, diametro_mm) == esperado[nombre]


def test_mm_a_pies_conversion():
    """_mm_a_pies convierte milimetros a pies internos de Revit."""
    # 304.8 mm = 1 pie
    pies = _mm_a_pies(304.8)
    assert abs(pies - 1.0) < 0.001

    # 19.05 mm (3/4") -> ~0.0625 pies
    pies_34 = _mm_a_pies(19.05)
    assert abs(pies_34 - (19.05 / 304.8)) < 0.001


def test_pies_a_mm_conversion():
    """_pies_a_mm convierte pies internos a milimetros."""
    mm = _pies_a_mm(1.0)
    assert abs(mm - 304.8) < 0.001


def test_nombre_tipo_conduit_usa_name():
    """_nombre_tipo_elemento retorna Name si existe."""
    ct = _FakeConduitType("Conduit 3/4\"", 1, _FakeDoc())
    assert _nombre_tipo_elemento(ct) == "Conduit 3/4\""


def test_crear_tipos_conduit_crea_los_cinco_tipos():
    """En un doc con categoria Conduit disponible y un tipo base, crea los 5 tipos."""
    doc = _FakeDoc("ConduitTest.rvt", con_categoria_conduit=True)
    # Registrar un tipo base para que conduit_type_disponible quede True
    # y Duplicate funcione
    doc.registrar_conduit_tipo("Conduit Base Existente")

    resultado = crear_tipos_conduit(doc)

    assert resultado["creados"] == 5
    assert resultado["existentes"] == 0
    assert resultado["fallos"] == 0
    nombres_creados = {d["tipo"] for d in resultado["detalle"] if d["motivo"] == "OK — creado"}
    assert nombres_creados == {
        "Conduit 3/4\"",
        "Conduit 1\"",
        "Conduit 1-1/4\"",
        "Conduit 2\"",
        "Conduit 3\"",
    }
    # Verificar que se registraron en el doc falso
    for nombre in nombres_creados:
        assert nombre in doc._conduit_types


def test_crear_tipos_conduit_no_duplica_tipos_existentes():
    """Si un tipo ya existe, se cuenta como existente y no se duplica."""
    doc = _FakeDoc("ConduitTest2.rvt", con_categoria_conduit=True)
    doc.registrar_conduit_tipo("Conduit Base Existente")
    doc.registrar_conduit_tipo("Conduit 3/4\"")  # ya existe

    resultado = crear_tipos_conduit(doc)

    assert resultado["existentes"] == 1
    assert resultado["creados"] == 4  # los otros 4 se crean
    assert resultado["fallos"] == 0


def test_crear_tipos_conduit_sin_categoria_conduit():
    """Sin categoria ConduitType y sin tipo base, retorna 0 creados y motivo."""
    doc = _FakeDoc("Arquitectonico.rvt", con_categoria_conduit=False)
    # Sin tipos de conduit registrados -> simbolos_conduit vacio
    # El codigo entra en la rama len(simbolos_conduit) == 0
    resultado = crear_tipos_conduit(doc)

    assert resultado["creados"] == 0
    assert resultado["existentes"] == 0
    assert "No hay tipos de conducto disponibles para duplicar en el documento" in resultado["detalle"][0]["motivo"]


def test_crear_tipos_conduit_guarda_json_en_disco(tmp_path):
    """El resultado se serializa a JSON y se guarda en disco cuando se pasa json_out."""
    doc = _FakeDoc("ConduitTest3.rvt", con_categoria_conduit=True)
    doc.registrar_conduit_tipo("Conduit Base Existente")

    json_out = str(tmp_path / "conduit_tipos.json")
    resultado = crear_tipos_conduit(doc, json_out=json_out)

    assert os.path.exists(json_out)
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["creados"] == 5
    assert data["documento"] == "ConduitTest3.rvt"
    assert "fecha_ejecucion" in data
    assert len(data["detalle"]) == 5

