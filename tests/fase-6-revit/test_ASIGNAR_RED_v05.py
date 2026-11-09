"""
================================================================================
test_ASIGNAR_RED_v05.py — Tests para ASIGNAR_RED_v05.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que ASIGNAR_RED_v05.py:
  1. Carga el JSON de reporte de modelado (acciones_modelar).
  2. Filtra dispositivos de capa ELEC-APPL-NETWORD (RED=SI).
  3. Busca en Revit por coincidencia de posicion XYZ (tolerancia 0.02 m).
  4. Marca Comments = 'RED=SI' (agrega si ya hay comentario previo).
  5. No depende de ElementIds fijos del DXF.
  6. Genera JSON de salida con exitos, fallos y detalle.

FIXTURE:
  tests/fase-6-revit/fixture_ASIGNAR_RED_v05.json

USO:
  pytest tests/fase-6-revit/test_ASIGNAR_RED_v05.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API para validar la logica
  de negocio sin necesidad de tener Revit instalado.
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-6-revit"
    / "ASIGNAR_RED_v05.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_ASIGNAR_RED_v05.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeXYZ:
    def __init__(self, x, y, z):
        self.X = x
        self.Y = y
        self.Z = z

    def DistanceTo(self, otro):
        return math.sqrt(
            (self.X - otro.X) ** 2 + (self.Y - otro.Y) ** 2 + (self.Z - otro.Z) ** 2
        )


class _FakeLocation:
    def __init__(self, punto):
        self.Point = punto


class _FakeParameter:
    def __init__(self, nombre, valor=None, readonly=False):
        self.Definition = types.SimpleNamespace(Name=nombre)
        self._valor = valor
        self._readonly = readonly
        self.seteado = None

    @property
    def IsReadOnly(self):
        return self._readonly

    def AsString(self):
        return self._valor

    def Set(self, valor):
        self.seteado = valor
        self._valor = valor


class _FakeFamilyInstance:
    def __init__(self, id_val, x, y, z, familia="M_Toma simple", simbolo="Estandar"):
        self.Id = _FakeElementId(id_val)
        self.Location = _FakeLocation(_FakeXYZ(x, y, z))
        self._familia = familia
        self._simbolo = simbolo
        self._parametros = {}

    def get_Parameter(self, built_in_param):
        return self._parametros.get(str(built_in_param))

    @property
    def Symbol(self):
        return _FakeElementSymbol(self._simbolo, self._familia)

    @property
    def Parameters(self):
        return list(self._parametros.values())


class _FakeElementSymbol:
    def __init__(self, nombre, familia_nombre):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self._nombre_familia = familia_nombre


class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


class _FakeDoc:
    def __init__(self, nombre_doc="Test.rvt"):
        self.Title = nombre_doc
        self.PathName = "C:/Test/{}".format(nombre_doc)
        self._instancias = []
        self._transacciones = []
        self._commitido = False

    def Transaction(self, nombre):
        t = _FakeTransaction(self, nombre)
        self._transacciones.append(t)
        return t


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


class _FakeFilteredElementCollector:
    def __init__(self, doc):
        self._doc = doc
        self._clase = None

    def OfClass(self, clase):
        self._clase = clase
        return self

    def ToElements(self):
        return list(self._doc._instancias)


# ---------------------------------------------------------------------------
# Cargar el modulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _cargar_modulo_con_mocks():
    # Mock de 'clr' (solo existe en IronPython) para que import clr no falle en CPython
    clr_mock = types.ModuleType("clr")

    def _add_reference(nombre):
        pass

    clr_mock.AddReference = _add_reference

    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class FamilyInstance:
        pass

    class BuiltInParameter:
        ALL_MODEL_INSTANCE_COMMENTS = "ALL_MODEL_INSTANCE_COMMENTS"
        ALL_MODEL_TYPE_NAME = "ALL_MODEL_TYPE_NAME"

    class Transaction:
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

    class XYZ:
        def __init__(self, x, y, z):
            self.X = x
            self.Y = y
            self.Z = z

    class FilteredElementCollector:
        def __init__(self, doc):
            self._doc = doc
        def OfClass(self, clase):
            return _FakeFilteredElementCollector(self._doc).OfClass(clase)

    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.BuiltInParameter = BuiltInParameter
    revit_db.FamilyInstance = FamilyInstance
    revit_db.Transaction = Transaction
    revit_db.XYZ = XYZ

    sys.modules["clr"] = clr_mock
    # Mock de 'System' (solo existe en IronPython/.NET) para que from System import Int64 no falle
    system_mock = types.ModuleType("System")
    class _FakeInt64:
        pass
    system_mock.Int64 = _FakeInt64
    sys.modules["System"] = system_mock
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    spec = importlib.util.spec_from_file_location(
        "ASIGNAR_RED_v05", SCRIPT_PATH
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
asignar_red = _mod.asignar_red
_filtrar_dispositivos_red = _mod._filtrar_dispositivos_red
_cargar_reporte = _mod._cargar_reporte
_buscar_instancia_por_posicion = _mod._buscar_instancia_por_posicion


@pytest.fixture(autouse=True)
def _reiniciar_modulo():
    global _mod, _fake_doc, asignar_red, _filtrar_dispositivos_red, _cargar_reporte, _buscar_instancia_por_posicion
    _cargar_modulo_con_mocks()
    _mod, _fake_doc = _cargar_modulo_con_mocks()
    asignar_red = _mod.asignar_red
    _filtrar_dispositivos_red = _mod._filtrar_dispositivos_red
    _cargar_reporte = _mod._cargar_reporte
    _buscar_instancia_por_posicion = _mod._buscar_instancia_por_posicion
    yield


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Instalacion de instancias falsas en el doc para pruebas de busqueda
# ---------------------------------------------------------------------------

def _instalar_instancias(doc, instancias):
    doc._instancias = []
    for inst in instancias:
        doc._instancias.append(inst)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cargar_reporte_acciones_modelar(tmp_path):
    """_cargar_reporte lee la clave acciones_modelar del JSON de reporte."""
    datos = {"acciones_modelar": [{"orden": 1, "nombre_bloque": "ELEC-TEL"}]}
    ruta = tmp_path / "reporte.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    acciones = _cargar_reporte(str(ruta))
    assert len(acciones) == 1
    assert acciones[0]["nombre_bloque"] == "ELEC-TEL"


def test_cargar_reporte_exitos(tmp_path):
    """_cargar_reporte soporta la clave 'exitos' (reporte _resultado.json)."""
    datos = {"exitos": [{"orden": 1, "nombre_bloque": "ELEC-NET-PAU"}]}
    ruta = tmp_path / "reporte_resultado.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    acciones = _cargar_reporte(str(ruta))
    assert len(acciones) == 1
    assert acciones[0]["nombre_bloque"] == "ELEC-NET-PAU"


def test_filtrar_dispositivos_red_solo_capa_netword():
    """_filtrar_dispositivos_red solo retorna dispositivos de capa ELEC-APPL-NETWORD."""
    acciones = [
        {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 42,
         "x_revit": 6.1419, "y_revit": 7.2148, "z_revit": 0.3},
        {"capa": "ELEC-APPL-TOMAS", "nombre_bloque": "ELEC-T-GFCI-t-15A", "orden": 0,
         "x_revit": 2.822, "y_revit": 8.7015, "z_revit": 0.3},
        {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-NET-PAU", "orden": 45,
         "x_revit": 3.961, "y_revit": 5.0512, "z_revit": 0.3},
    ]
    red = _filtrar_dispositivos_red(acciones)
    assert len(red) == 2
    nombres = {d["nombre_bloque"] for d in red}
    assert nombres == {"ELEC-TEL", "ELEC-NET-PAU"}


def test_filtrar_dispositivos_red_campos_coordenadas():
    """Los dispositivos filtrados incluyen x, y, z como floats."""
    acciones = [
        {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 42,
         "x_revit": 6.1419, "y_revit": 7.2148, "z_revit": 0.3},
    ]
    red = _filtrar_dispositivos_red(acciones)
    assert red[0]["x"] == 6.1419
    assert red[0]["y"] == 7.2148
    assert red[0]["z"] == 0.3


def test_buscar_instancia_por_posicion_encuentra():
    """_buscar_instancia_por_posicion encuentra la instancia mas cercana."""
    inst = _FakeFamilyInstance(867009, 6.1419, 7.2148, 0.3)
    _instalar_instancias(_fake_doc, [inst])
    found = _buscar_instancia_por_posicion(_fake_doc, 6.1419, 7.2148, 0.3)
    assert found is inst


def test_buscar_instancia_por_posicion_tolerancia():
    """_buscar_instancia_por_posicion respeta la tolerancia de 0.02 m."""
    inst = _FakeFamilyInstance(867009, 6.1419, 7.2148, 0.3)
    _instalar_instancias(_fake_doc, [inst])
    # Dentro de la tolerancia
    found = _buscar_instancia_por_posicion(_fake_doc, 6.1420, 7.2149, 0.3001)
    assert found is inst
    # Fuera de la tolerancia (0.5 m de distancia)
    found_lejos = _buscar_instancia_por_posicion(_fake_doc, 6.6419, 7.2148, 0.3)
    assert found_lejos is None


def test_asignar_red_marca_comentarios():
    """asignar_red marca Comments='RED=SI' en las instancias encontradas."""
    inst1 = _FakeFamilyInstance(867009, 6.1419, 7.2148, 0.3)
    inst2 = _FakeFamilyInstance(867010, 6.1419, 7.0649, 0.3)
    inst1._parametros["ALL_MODEL_INSTANCE_COMMENTS"] = _FakeParameter("Comments", None)
    inst2._parametros["ALL_MODEL_INSTANCE_COMMENTS"] = _FakeParameter("Comments", None)
    _instalar_instancias(_fake_doc, [inst1, inst2])

    reporte = {
        "acciones_modelar": [
            {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 42,
             "x_revit": 6.1419, "y_revit": 7.2148, "z_revit": 0.3},
            {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 43,
             "x_revit": 6.1419, "y_revit": 7.0649, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_red_test.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_red(_fake_doc, reporte_json=ruta_reporte)
    assert resultado["exitos"] == 2
    assert resultado["fallos"] == 0
    assert inst1._parametros["ALL_MODEL_INSTANCE_COMMENTS"].seteado == "RED=SI"
    assert inst2._parametros["ALL_MODEL_INSTANCE_COMMENTS"].seteado == "RED=SI"


def test_asignar_red_agrega_a_comentario_existente():
    """Si ya hay comentario, agrega ' | RED=SI' en vez de reemplazar."""
    inst = _FakeFamilyInstance(867009, 6.1419, 7.2148, 0.3)
    inst._parametros["ALL_MODEL_INSTANCE_COMMENTS"] = _FakeParameter("Comments", "Circuitos: A")
    _instalar_instancias(_fake_doc, [inst])

    reporte = {
        "acciones_modelar": [
            {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 42,
             "x_revit": 6.1419, "y_revit": 7.2148, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_red_test2.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_red(_fake_doc, reporte_json=ruta_reporte)
    assert resultado["exitos"] == 1
    assert inst._parametros["ALL_MODEL_INSTANCE_COMMENTS"].seteado == "Circuitos: A | RED=SI"


def test_asignar_red_no_encontrado():
    """Si no hay instancia en la posicion, cuenta como fallo no_encontrado."""
    _instalar_instancias(_fake_doc, [])

    reporte = {
        "acciones_modelar": [
            {"capa": "ELEC-APPL-NETWORD", "nombre_bloque": "ELEC-TEL", "orden": 42,
             "x_revit": 99.999, "y_revit": 99.999, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_red_test3.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_red(_fake_doc, reporte_json=ruta_reporte)
    assert resultado["exitos"] == 0
    assert resultado["no_encontrados"] == 1
    assert resultado["fallos"] == 1


def test_asignar_red_ignora_dispositivos_no_red():
    """Los dispositivos de otras capas no se marcan."""
    inst = _FakeFamilyInstance(867001, 2.822, 8.7015, 0.3)
    inst._parametros["ALL_MODEL_INSTANCE_COMMENTS"] = _FakeParameter("Comments", None)
    _instalar_instancias(_fake_doc, [inst])

    reporte = {
        "acciones_modelar": [
            {"capa": "ELEC-APPL-TOMAS", "nombre_bloque": "ELEC-T-GFCI-t-15A", "orden": 0,
             "x_revit": 2.822, "y_revit": 8.7015, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_red_test4.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_red(_fake_doc, reporte_json=ruta_reporte)
    assert resultado["exitos"] == 0
    assert resultado["total_reporte"] == 0
    assert inst._parametros["ALL_MODEL_INSTANCE_COMMENTS"].seteado is None


def test_estructura_json_salida_contiene_claves_esperadas():
    """main() genera claves esperadas para JSON (verificado por inspeccion de fuente)."""
    import inspect
    fuente = inspect.getsource(_mod.asignar_red)
    assert "exitos" in fuente
    assert "fallos" in fuente
    assert "detalle" in fuente
    assert "no_encontrados" in fuente
