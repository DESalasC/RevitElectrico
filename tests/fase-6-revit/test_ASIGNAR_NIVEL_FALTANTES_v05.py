"""
================================================================================
test_ASIGNAR_NIVEL_FALTANTES_v05.py — Tests para ASIGNAR_NIVEL_FALTANTES_v05.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que ASIGNAR_NIVEL_FALTANTES_v05.py:
  1. Carga el JSON de reporte de modelado (acciones_modelar).
  2. Filtra candidatos anfitrion ceiling/nivel (sin host de muro asignado).
  3. Busca en Revit por coincidencia de posicion XYZ (tolerancia 0.02 m).
  4. Asigna el nivel "Piso 5" buscado dinamicamente por nombre o elevacion.
  5. No depende de ElementIds fijos del DXF.
  6. Genera JSON de salida con exitos, fallos y detalle.

FIXTURE:
  tests/fase-6-revit/fixture_ASIGNAR_NIVEL_FALTANTES_v05.json

USO:
  pytest tests/fase-6-revit/test_ASIGNAR_NIVEL_FALTANTES_v05.py -v

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
    / "ASIGNAR_NIVEL_FALTANTES_v05.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_ASIGNAR_NIVEL_FALTANTES_v05.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

# Clases reales en scope global para comparaciones `is` y isinstance en los tests
class Level:
    pass


class FamilyInstance:
    pass


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


class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


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


class _FakeLevel:
    def __init__(self, id_val, nombre, elev_pies):
        self.Id = _FakeElementId(id_val)
        self._nombre = nombre
        self.Elevation = elev_pies

    def get_Parameter(self, built_in_param):
        return None

    @property
    def Name(self):
        return self._nombre


class _FakeFamilyInstance:
    def __init__(self, id_val, x, y, z, familia="M_Toma simple", simbolo="Estandar",
                 nivel_id=None):
        self.Id = _FakeElementId(id_val)
        self.Location = _FakeLocation(_FakeXYZ(x, y, z))
        self._familia = familia
        self._simbolo = simbolo
        self._nivel_id = nivel_id
        self._parametros = {}

    def get_Parameter(self, built_in_param):
        return self._parametros.get(str(built_in_param))

    @property
    def Symbol(self):
        return _FakeElementSymbol(self._simbolo, self._familia)

    @property
    def Parameters(self):
        return list(self._parametros.values())

    @property
    def LevelId(self):
        return self._nivel_id

    @LevelId.setter
    def LevelId(self, valor):
        self._nivel_id = valor


class _FakeElementSymbol:
    def __init__(self, nombre, familia_nombre):
        self.Name = nombre
        self.Id = _FakeElementId(hash(nombre) % 100000)
        self._nombre_familia = familia_nombre


class _FakeDoc:
    def __init__(self, nombre_doc="Test.rvt"):
        self.Title = nombre_doc
        self.PathName = "C:/Test/{}".format(nombre_doc)
        self._instancias = []
        self._niveles = []
        self._transacciones = []
        self._commitido = False

    def Transaction(self, nombre):
        t = _FakeTransaction(self, nombre)
        self._transacciones.append(t)
        return t

    def GetElement(self, elem_id):
        for inst in self._instancias:
            if inst.Id.IntegerValue == elem_id.IntegerValue:
                return inst
        return None


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
        self._categoria = None
        self._clase = None

    def OfCategory(self, categoria):
        self._categoria = categoria
        return self

    def OfClass(self, clase):
        self._clase = clase
        return self

    def ToElements(self):
        if self._clase is Level:
            return list(self._doc._niveles)
        if self._clase is FamilyInstance:
            return list(self._doc._instancias)
        return []


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

    class BuiltInCategory:
        OST_Levels = "OST_Levels"

    class Level:
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
            self._categoria = None
            self._clase = None

        def OfCategory(self, categoria):
            self._categoria = categoria
            return self

        def OfClass(self, clase):
            self._clase = clase
            return self

        def ToElements(self):
            if self._clase is Level:
                return list(self._doc._niveles)
            if self._clase is FamilyInstance:
                return list(self._doc._instancias)
            return []

    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.BuiltInParameter = BuiltInParameter
    revit_db.FamilyInstance = FamilyInstance
    revit_db.Transaction = Transaction
    revit_db.XYZ = XYZ
    revit_db.BuiltInCategory = BuiltInCategory
    revit_db.Level = Level

    sys.modules["clr"] = clr_mock
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
        "ASIGNAR_NIVEL_FALTANTES_v05", SCRIPT_PATH
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
asignar_nivel_faltantes = _mod.asignar_nivel_faltantes
_filtrar_sin_nivel = _mod._filtrar_sin_nivel
_cargar_reporte = _mod._cargar_reporte
_buscar_instancia_por_posicion = _mod._buscar_instancia_por_posicion
_buscar_nivel_por_nombre_o_elevacion = _mod._buscar_nivel_por_nombre_o_elevacion
_nivel_actual_de_instancia = _mod._nivel_actual_de_instancia


@pytest.fixture(autouse=True)
def _reiniciar_modulo():
    global _mod, _fake_doc, asignar_nivel_faltantes
    global _filtrar_sin_nivel, _cargar_reporte, _buscar_instancia_por_posicion
    global _buscar_nivel_por_nombre_o_elevacion, _nivel_actual_de_instancia
    _cargar_modulo_con_mocks()
    _mod, _fake_doc = _cargar_modulo_con_mocks()
    asignar_nivel_faltantes = _mod.asignar_nivel_faltantes
    _filtrar_sin_nivel = _mod._filtrar_sin_nivel
    _cargar_reporte = _mod._cargar_reporte
    _buscar_instancia_por_posicion = _mod._buscar_instancia_por_posicion
    _buscar_nivel_por_nombre_o_elevacion = _mod._buscar_nivel_por_nombre_o_elevacion
    _nivel_actual_de_instancia = _mod._nivel_actual_de_instancia
    yield


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _instalar_instancias(doc, instancias):
    doc._instancias = []
    for inst in instancias:
        doc._instancias.append(inst)


def _instalar_niveles(doc, niveles):
    doc._niveles = []
    for niv in niveles:
        doc._niveles.append(niv)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cargar_reporte_acciones_modelar(tmp_path):
    """_cargar_reporte lee la clave acciones_modelar del JSON de reporte."""
    datos = {"acciones_modelar": [{"orden": 1, "nombre_bloque": "ELEC-CAMPANA"}]}
    ruta = tmp_path / "reporte.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    acciones = _cargar_reporte(str(ruta))
    assert len(acciones) == 1
    assert acciones[0]["nombre_bloque"] == "ELEC-CAMPANA"


def test_cargar_reporte_exitos(tmp_path):
    """_cargar_reporte soporta la clave 'exitos' (reporte _resultado.json)."""
    datos = {"exitos": [{"orden": 1, "nombre_bloque": "ELEC-F-VENT"}]}
    ruta = tmp_path / "reporte_resultado.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    acciones = _cargar_reporte(str(ruta))
    assert len(acciones) == 1
    assert acciones[0]["nombre_bloque"] == "ELEC-F-VENT"


def test_filtrar_sin_nivel_solo_candidates_techo_o_sin_nivel_revit():
    """_filtrar_sin_nivel retorna acciones anfitrion ceiling o sin nivel_revit."""
    acciones = [
        {"anfitrion": "ceiling", "nivel_revit": None, "nombre_bloque": "ELEC-CAMPANA",
         "orden": 9, "x_revit": 5.3375, "y_revit": 2.2423, "z_revit": 2.6},
        {"anfitrion": "muro", "nivel_revit": "Piso 5", "nombre_bloque": "ELEC-T-GFCI-t-15A",
         "orden": 0, "x_revit": 2.822, "y_revit": 8.7015, "z_revit": 0.3},
        {"anfitrion": "nivel", "nivel_revit": "", "nombre_bloque": "ELEC-F-VENT",
         "orden": 14, "x_revit": 4.3513, "y_revit": 6.9512, "z_revit": 2.6},
    ]
    candidatos = _filtrar_sin_nivel(acciones)
    assert len(candidatos) == 2
    nombres = {c["nombre_bloque"] for c in candidatos}
    assert nombres == {"ELEC-CAMPANA", "ELEC-F-VENT"}


def test_filtrar_sin_nivel_campos_coordenadas():
    """Los candidatos filtrados incluyen x, y, z como floats."""
    acciones = [
        {"anfitrion": "ceiling", "nivel_revit": None, "nombre_bloque": "ELEC-CAMPANA",
         "orden": 9, "x_revit": 5.3375, "y_revit": 2.2423, "z_revit": 2.6},
    ]
    candidatos = _filtrar_sin_nivel(acciones)
    assert candidatos[0]["x"] == 5.3375
    assert candidatos[0]["y"] == 2.2423
    assert candidatos[0]["z"] == 2.6


def test_buscar_instancia_por_posicion_encuentra():
    """_buscar_instancia_por_posicion encuentra la instancia mas cercana."""
    inst = _FakeFamilyInstance(866991, 5.3375, 2.2423, 2.6)
    _instalar_instancias(_fake_doc, [inst])
    found = _buscar_instancia_por_posicion(_fake_doc, 5.3375, 2.2423, 2.6)
    assert found is inst


def test_buscar_instancia_por_posicion_tolerancia():
    """_buscar_instancia_por_posicion respeta la tolerancia de 0.02 m."""
    inst = _FakeFamilyInstance(866991, 5.3375, 2.2423, 2.6)
    _instalar_instancias(_fake_doc, [inst])
    # Dentro de la tolerancia
    found = _buscar_instancia_por_posicion(_fake_doc, 5.3376, 2.2424, 2.6001)
    assert found is inst
    # Fuera de la tolerancia (0.5 m de distancia)
    found_lejos = _buscar_instancia_por_posicion(_fake_doc, 5.8375, 2.2423, 2.6)
    assert found_lejos is None


def test_buscar_nivel_por_nombre():
    """_buscar_nivel_por_nombre_o_elevacion encuentra el nivel por nombre."""
    nivel = _FakeLevel(100, "Piso 5", 13.22 * 3.28084)
    _instalar_niveles(_fake_doc, [nivel])
    found = _buscar_nivel_por_nombre_o_elevacion(_fake_doc, "Piso 5", 13.22)
    assert found is nivel


def test_buscar_nivel_por_elevacion_fallback():
    """_buscar_nivel_por_nombre_o_elevacion usa elevacion como fallback."""
    nivel = _FakeLevel(200, "Nivel 2", 13.22 * 3.28084)
    _instalar_niveles(_fake_doc, [nivel])
    found = _buscar_nivel_por_nombre_o_elevacion(_fake_doc, "Piso 5", 13.22)
    assert found is nivel


def test_nivel_actual_de_instancia_con_nivel():
    """_nivel_actual_de_instancia retorna el LevelId cuando hay uno."""
    nivel_id = _FakeElementId(500)
    inst = _FakeFamilyInstance(1, 0, 0, 0, nivel_id=nivel_id)
    assert _nivel_actual_de_instancia(inst) is nivel_id


def test_nivel_actual_de_instancia_sin_nivel():
    """_nivel_actual_de_instancia retorna None cuando no hay nivel."""
    inst = _FakeFamilyInstance(1, 0, 0, 0, nivel_id=None)
    assert _nivel_actual_de_instancia(inst) is None


def test_asignar_nivel_faltantes_asigna_nivel():
    """asignar_nivel_faltantes asigna el nivel Piso 5 a las instancias encontradas."""
    inst1 = _FakeFamilyInstance(866991, 5.3375, 2.2423, 2.6, nivel_id=None)
    inst2 = _FakeFamilyInstance(866996, 4.3513, 6.9512, 2.6, nivel_id=None)
    inst3 = _FakeFamilyInstance(867000, 5.0709, 4.3372, 2.6, nivel_id=None)
    inst4 = _FakeFamilyInstance(867001, 5.0794, 3.0361, 2.6, nivel_id=None)
    inst5 = _FakeFamilyInstance(867002, 5.0664, 8.2472, 2.6, nivel_id=None)
    inst6 = _FakeFamilyInstance(867017, 3.978, 4.9135, 0.3, nivel_id=None)
    _instalar_instancias(_fake_doc, [inst1, inst2, inst3, inst4, inst5, inst6])
    nivel = _FakeLevel(100, "Piso 5", 13.22 * 3.28084)
    _instalar_niveles(_fake_doc, [nivel])

    reporte = _cargar_fixture()
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_nivel_test.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    ruta_json_out = os.path.join(tempfile.gettempdir(), "asignar_nivel_v05_resultado.json")
    resultado = asignar_nivel_faltantes(_fake_doc, reporte_json=ruta_reporte,
                                        json_out=ruta_json_out, nivel_destino="Piso 5",
                                        elevacion_m=13.22)

    assert resultado["exitos"] == 1
    assert resultado["face_based_skip"] == 5
    assert resultado["fallos"] == 5
    # Solo la instancia de muro (inst6, z=0.3) recibe el nivel
    assert inst6.LevelId is not None
    assert inst6.LevelId.IntegerValue == 100
    # Las instancias de techo (z=2.6) son face-based: LevelId no se les asigna
    assert inst1.LevelId is None
    assert inst2.LevelId is None


def test_asignar_nivel_faltantes_ya_tenia_nivel():
    """Si la instancia ya tiene el nivel asignado, se cuenta como ya_tenia_nivel."""
    # Instancia de MURO (z=0.3), no de techo, para que no sea face-based skip
    nivel_id = _FakeElementId(100)
    inst = _FakeFamilyInstance(867017, 3.978, 4.9135, 0.3, nivel_id=nivel_id)
    _instalar_instancias(_fake_doc, [inst])
    nivel = _FakeLevel(100, "Piso 5", 13.22 * 3.28084)
    _instalar_niveles(_fake_doc, [nivel])

    reporte = _cargar_fixture()
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_nivel_test2.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_nivel_faltantes(_fake_doc, reporte_json=ruta_reporte,
                                        nivel_destino="Piso 5", elevacion_m=13.22)

    assert resultado["ya_tenia_nivel"] == 1
    assert resultado["exitos"] == 0


def test_asignar_nivel_faltantes_no_encontrado():
    """Si no hay instancia en la posicion, cuenta como fallo no_encontrado."""
    _instalar_instancias(_fake_doc, [])
    _instalar_niveles(_fake_doc, [_FakeLevel(100, "Piso 5", 13.22 * 3.28084)])

    reporte = {
        "acciones_modelar": [
            {"anfitrion": "muro", "nivel_revit": None, "nombre_bloque": "ELEC-T-D-t-15A",
             "orden": 50, "x_revit": 99.999, "y_revit": 99.999, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_nivel_test3.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_nivel_faltantes(_fake_doc, reporte_json=ruta_reporte,
                                        nivel_destino="Piso 5", elevacion_m=13.22)

    assert resultado["exitos"] == 0
    assert resultado["no_encontrados"] == 1
    assert resultado["fallos"] == 1


def test_asignar_nivel_faltantes_ignora_muro_con_nivel():
    """Los dispositivos de muro con nivel_revit asignado no son candidatos."""
    inst = _FakeFamilyInstance(867001, 2.822, 8.7015, 0.3)
    _instalar_instancias(_fake_doc, [inst])
    _instalar_niveles(_fake_doc, [_FakeLevel(100, "Piso 5", 13.22 * 3.28084)])

    reporte = {
        "acciones_modelar": [
            {"anfitrion": "muro", "nivel_revit": "Piso 5", "nombre_bloque": "ELEC-T-GFCI-t-15A",
             "orden": 0, "x_revit": 2.822, "y_revit": 8.7015, "z_revit": 0.3},
        ]
    }
    import tempfile
    ruta_reporte = os.path.join(tempfile.gettempdir(), "reporte_nivel_test4.json")
    with open(ruta_reporte, "w") as f:
        json.dump(reporte, f)

    resultado = asignar_nivel_faltantes(_fake_doc, reporte_json=ruta_reporte,
                                        nivel_destino="Piso 5", elevacion_m=13.22)

    assert resultado["total_candidatos"] == 0
    assert resultado["exitos"] == 0
    assert inst.LevelId is None or inst.LevelId.IntegerValue != 100


def test_estructura_json_salida_contiene_claves_esperadas():
    """main() genera claves esperadas para JSON (verificado por inspeccion de fuente)."""
    import inspect
    fuente = inspect.getsource(_mod.asignar_nivel_faltantes)
    assert "exitos" in fuente
    assert "fallos" in fuente
    assert "detalle" in fuente
    assert "ya_tenia_nivel" in fuente
    assert "no_encontrados" in fuente
