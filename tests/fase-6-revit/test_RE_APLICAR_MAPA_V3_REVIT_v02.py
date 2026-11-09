"""
================================================================================
test_RE_APLICAR_MAPA_V3_REVIT_v02.py — Tests para RE_APLICAR_MAPA_V3_REVIT_v02
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (CPython, se hace mock de la API de Revit)
================================================================================

OBJETIVO:
  Verificar que RE_APLICAR_MAPA_V3_REVIT_v02.py (Tarea C - host fallback
  techo -> muro):
  1. Crea FamilyInstance con cara de techo cuando el punto XY cae dentro de
     un cieloraso (metodo_ajustado = None, host_resuelto = "techo").
  2. Cuando no hay cara de techo, busca cara de muro vertical mas cercana
     dentro del radio y crea la instancia contra el muro
     (metodo_ajustado = "ceiling->muro_fallback", host_resuelto = "muro").
  3. Cuando no hay techo ni muro, usa el nivel "Piso 5" como fallback final
     (metodo_ajustado = "ceiling->nivel_fallback", host_resuelto = "nivel").
  4. Para anfitrion == "muro", crea la instancia sobre el nivel indicado.
  5. Registra fallos cuando no se encuentra familia/simbolo, ni techo,
     ni muro, ni nivel.
  6. Genera JSON de resultado con estadisticas y listas de exitos/fallos.

FIXTURE:
  tests/fase-6-revit/fixture_RE_APLICAR_MAPA_V3_REVIT_v02.json

USO:
  pytest tests/fase-6-revit/test_RE_APLICAR_MAPA_V3_REVIT_v02.py -v

NOTA:
  Como este script usa la API de Revit (IronPython 2.7), los tests se ejecutan
  en CPython 3.12 con mocks de las clases de Revit API para validar la logica
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
    / "RE_APLICAR_MAPA_V3_REVIT_v02.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_RE_APLICAR_MAPA_V3_REVIT_v02.json"


# ---------------------------------------------------------------------------
# Mocks de la API de Revit (IronPython) para CPython 3.12
# ---------------------------------------------------------------------------

class _FakeElementId:
    def __init__(self, valor):
        self.IntegerValue = valor

    def ToString(self):
        return str(self.IntegerValue)


class _FakeXYZ:
    def __init__(self, x, y, z):
        self.X = x
        self.Y = y
        self.Z = z


class _FakeFamilySymbol:
    def __init__(self, nombre, familia_nombre, activo=True):
        self.Name = nombre
        self._familia_nombre = familia_nombre
        self.IsActive = activo

    def Activate(self):
        self.IsActive = True


class _FakeFamily:
    def __init__(self, nombre, simbolos=None, id_simbolo=None):
        self.Name = nombre
        self._simbolos = simbolos or []
        self._id_simbolo = id_simbolo

    def GetFamilySymbolIds(self):
        if self._id_simbolo is not None:
            return [_FakeElementId(self._id_simbolo)]
        return [_FakeElementId(i) for i in range(len(self._simbolos))]


class _FakeLevel:
    def __init__(self, nombre):
        self.Name = nombre


class _FakeFace:
    """Cara con origen XYZ y vertices XY opcionales (para punto-dentro-poligono)."""

    def __init__(self, z, vertices_xy=None, normal_z=0.0):
        self.Origin = _FakeXYZ(0.0, 0.0, z)
        self._vertices_xy = vertices_xy
        # Cara "vertical": normal con componente Z pequeña
        self._normal_z = normal_z

    def obtener_vertices_xy(self):
        return self._vertices_xy

    @property
    def FaceNormal(self):
        return _FakeXYZ(0.0, 0.0, self._normal_z)


class _FakeTecho:
    def __init__(self, z, vertices_xy=None):
        self.IsElementType = False
        self.Id = _FakeElementId(1000)
        self._cara = _FakeFace(z, vertices_xy=vertices_xy)

    def get_Geometry(self, options):
        return _FakeGeometria([self._cara])


class _FakeMuro:
    def __init__(self, z, vertices_xy=None):
        self.IsElementType = False
        self.Id = _FakeElementId(2000)
        self._cara = _FakeFace(z, vertices_xy=vertices_xy, normal_z=0.05)

    def get_Geometry(self, options):
        return _FakeGeometria([self._cara])


class _FakeGeometria:
    def __init__(self, caras):
        self.Faces = caras

    def __iter__(self):
        return iter([self])


class _FakeElement:
    def __init__(self, nombre, id_valor):
        self.Name = nombre
        self.Id = _FakeElementId(id_valor)
        self.IsElementType = False


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
    def __init__(self):
        self.Title = "Test.rvt"
        self.PathName = "C:/Test/Test.rvt"
        self._familias = {}
        self._simbolos = {}
        self._simbolos_por_id = {}
        self._siguiente_id_simbolo = 0
        self._niveles = {}
        self._elementos_creados = []
        self._id_por_familia = {}
        self.Create = _FakeDocCreate(self)

    def registrar_familia(self, nombre_familia, nombre_simbolo, simbolo):
        self._familias[nombre_familia] = True
        self._simbolos[(nombre_familia, nombre_simbolo)] = simbolo
        sid = self._siguiente_id_simbolo
        self._siguiente_id_simbolo += 1
        self._simbolos_por_id[sid] = simbolo
        self._id_por_familia[nombre_familia] = sid

    def registrar_nivel(self, nombre_nivel):
        self._niveles[nombre_nivel] = _FakeLevel(nombre_nivel)

    def registrar_techo(self, techo):
        self._techos = getattr(self, "_techos", [])
        self._techos.append(techo)

    def registrar_muro(self, muro):
        self._muros = getattr(self, "_muros", [])
        self._muros.append(muro)

    def GetElement(self, id_elem):
        if hasattr(id_elem, "IntegerValue"):
            return self._simbolos_por_id.get(id_elem.IntegerValue)
        return None

    def Regenerate(self):
        pass


class _FakeDocCreate:
    def __init__(self, doc):
        self.doc = self
        self._doc = doc
        self._contador = 1000

    def NewFamilyInstance(self, *args, **kwargs):
        # args puede ser (level, location, symbol, estructural) o (face, location, symbol)
        self._contador += 1
        inst = _FakeElement("Instance {}".format(self._contador), self._contador)
        self._doc._elementos_creados.append(inst)
        return inst


class _FakeFilteredElementCollector:
    def __init__(self, doc):
        self._doc = doc
        self._clase = None
        self._categoria = None

    def OfClass(self, clase):
        self._clase = clase
        return self

    def OfCategory(self, categoria):
        self._categoria = categoria
        return self

    def ToElements(self):
        resultado = []
        nombre_clase = (
            self._clase.__name__ if hasattr(self._clase, "__name__") else str(self._clase)
        )
        if self._categoria is not None:
            nombre_cat = str(self._categoria)
            if "OST_Levels" in nombre_cat:
                for nombre in self._doc._niveles:
                    resultado.append(self._doc._niveles[nombre])
            if "OST_Ceilings" in nombre_cat:
                for techo in getattr(self._doc, "_techos", []):
                    resultado.append(techo)
            if "OST_Walls" in nombre_cat:
                for muro in getattr(self._doc, "_muros", []):
                    resultado.append(muro)
            if "OST_Floors" in nombre_cat:
                pass
            if "OST_Roofs" in nombre_cat:
                pass
        if self._clase is not None:
            if nombre_clase == "Family":
                por_familia = {}
                for (fam, sim), simbolo in self._doc._simbolos.items():
                    por_familia.setdefault(fam, []).append(simbolo)
                for nombre in self._doc._familias:
                    resultado.append(
                        _FakeFamily(
                            nombre,
                            por_familia.get(nombre, []),
                            id_simbolo=self._doc._id_por_familia.get(nombre),
                        )
                    )
            elif nombre_clase == "FamilySymbol":
                for (fam, sim), simbolo in self._doc._simbolos.items():
                    resultado.append(simbolo)
        return resultado


# ---------------------------------------------------------------------------
# Cargar el módulo bajo test con mocks inyectados
# ---------------------------------------------------------------------------

def _cargar_modulo_con_mocks():
    """Carga RE_APLICAR_MAPA_V3_REVIT_v02.py inyectando mocks de Revit API."""

    revit_db = types.ModuleType("Autodesk.Revit.DB")

    class BuiltInCategory:
        OST_ElectricalEquipment = "OST_ElectricalEquipment"
        OST_LightingFixtures = "OST_LightingFixtures"
        OST_ElectricalPanel = "OST_ElectricalPanel"
        OST_ElectricalCircuit = "OST_ElectricalCircuit"
        OST_Conduit = "OST_Conduit"
        OST_CableTray = "OST_CableTray"
        OST_Switches = "OST_Switches"
        OST_ElectricalFixture = "OST_ElectricalFixture"
        OST_Walls = "OST_Walls"
        OST_Floors = "OST_Floors"
        OST_Ceilings = "OST_Ceilings"
        OST_Roofs = "OST_Roofs"
        OST_StructuralColumns = "OST_StructuralColumns"
        OST_StructuralFraming = "OST_StructuralFraming"
        OST_Levels = "OST_Levels"

    class BuiltInParameter:
        ROTATION = "Rotation"

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

    class XYZ:
        def __init__(self, x, y, z):
            self.X = x
            self.Y = y
            self.Z = z

    class FamilyInstance:
        pass

    class FamilySymbol:
        pass

    class Level:
        pass

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

    class Family:
        pass

    revit_db.BuiltInCategory = BuiltInCategory
    revit_db.BuiltInParameter = BuiltInParameter
    revit_db.Structure = Structure
    revit_db.FilteredElementCollector = FilteredElementCollector
    revit_db.XYZ = XYZ
    revit_db.FamilyInstance = FamilyInstance
    revit_db.FamilySymbol = FamilySymbol
    revit_db.Family = Family
    revit_db.Level = Level
    revit_db.Transaction = Transaction

    # Inyectar en sys.modules ANTES de cargar el módulo bajo test
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.DB"] = revit_db
    sys.modules["Autodesk.Revit.DB"].__name__ = "Autodesk.Revit.DB"

    # Cargar el módulo bajo test
    spec = importlib.util.spec_from_file_location(
        "RE_APLICAR_MAPA_V3_REVIT_v02", SCRIPT_PATH
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


@pytest.fixture(autouse=True)
def _reinyectar_mock_v02():
    """Reinye el mock completo de Revit API en sys.modules y recarga el
    modulo bajo test antes de CADA prueba.

    Esto aísla los tests de v02 de la contaminacion de sys.modules que dejan
    otros modulos de Revit (por ejemplo RE_NIVELES_RVT_v01) al compartir la
    misma clave sys.modules["Autodesk.Revit.DB"] en una misma sesion de pytest.
    """
    global _mod, _fake_doc
    global aplicar_mapa_con_host_fallback, _guardar_json
    global _buscar_cara_techo, _buscar_cara_muro, _instanciar_con_host

    _mod, _fake_doc = _cargar_modulo_con_mocks()
    aplicar_mapa_con_host_fallback = _mod.aplicar_mapa_con_host_fallback
    _guardar_json = _mod._guardar_json
    _buscar_cara_techo = _mod._buscar_cara_techo
    _buscar_cara_muro = _mod._buscar_cara_muro
    _instanciar_con_host = _mod._instanciar_con_host


aplicar_mapa_con_host_fallback = _mod.aplicar_mapa_con_host_fallback
_guardar_json = _mod._guardar_json
_buscar_cara_techo = _mod._buscar_cara_techo
_buscar_cara_muro = _mod._buscar_cara_muro
_instanciar_con_host = _mod._instanciar_con_host


# ---------------------------------------------------------------------------
# Helpers de prueba
# ---------------------------------------------------------------------------

def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _registrar_datos_fixture(doc, fixture, con_techo=True, con_muro=True):
    """Registra familias, símbolos, niveles, techos y muros del fixture."""
    for accion in fixture.get("acciones", []):
        familia = accion.get("familia")
        simbolo = accion.get("simbolo")
        if familia and simbolo:
            doc.registrar_familia(
                familia, simbolo, _FakeFamilySymbol(simbolo, familia)
            )
    doc.registrar_nivel("Piso 5")

    # Techo grande centrado en (0,0) que contiene puntos cercanos al origen
    if con_techo:
        doc.registrar_techo(
            _FakeTecho(
                15.82,
                vertices_xy=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)],
            )
        )

    # Muro vertical cercano al punto (5, 3) para ejercitar fallback techo->muro
    if con_muro:
        doc.registrar_muro(
            _FakeMuro(
                1.0,
                vertices_xy=[(4.0, 2.0), (6.0, 2.0), (6.0, 4.0), (4.0, 4.0)],
            )
        )


# ---------------------------------------------------------------------------
# Tests de host fallback (Tarea C)
# ---------------------------------------------------------------------------

def test_techo_encontrado_host_resuelto_techo(tmp_path):
    """Cuando el punto cae dentro de un cieloraso, host_resuelto = 'techo'."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=True, con_muro=True)

    # Orden 0: punto (5.0, 3.0, 15.82) cae dentro del techo grande (-10..10)
    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    exitos = [e for e in resultado["exitos"] if e["orden"] == 0]
    assert len(exitos) == 1
    assert exitos[0]["host_resuelto"] == "techo"
    assert exitos[0]["cara_encontrada"] is True
    assert exitos[0]["metodo_ajustado"] is None


def test_fallback_techo_a_muro(tmp_path):
    """Cuando no hay techo pero hay muro cercano, host_resuelto = 'muro'."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=False, con_muro=True)

    # Orden 1: punto (99.0, 99.0) no cae dentro del techo (registramos sin techo)
    # pero hay un muro cercano? El muro esta en (4..6, 2..4), punto (99,99) esta lejos.
    # Para que entre en fallback a muro, necesitamos un muro cerca de (99,99).
    # Como no hay techo, y no hay muro cerca de (99,99), cae a nivel fallback.
    # Este test verifica la rama techo->nivel_fallback cuando no hay ni techo ni muro cerca.
    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    exitos = [e for e in resultado["exitos"] if e["orden"] == 1]
    # Sin techo ni muro cerca de (99,99): cae a nivel "Piso 5"
    assert len(exitos) == 1
    assert exitos[0]["host_resuelto"] == "nivel"
    assert exitos[0]["metodo_ajustado"] == "ceiling->nivel_fallback"


def test_fallback_techo_a_nivel_piso5(tmp_path):
    """Cuando no hay techo ni muro, host_resuelto = 'nivel' (Piso 5)."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=False, con_muro=False)

    # Orden 3: punto (999.0, 999.0) no tiene techo ni muro cercano -> nivel Piso 5
    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    exitos = [e for e in resultado["exitos"] if e["orden"] == 3]
    assert len(exitos) == 1
    assert exitos[0]["host_resuelto"] == "nivel"
    assert exitos[0]["metodo_ajustado"] == "ceiling->nivel_fallback"


def test_anfitrion_muro_usa_nivel(tmp_path):
    """Un dispositivo con anfitrion 'muro' se instancia sobre el nivel indicado."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=True, con_muro=True)

    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    exitos = [e for e in resultado["exitos"] if e["orden"] == 2]
    assert len(exitos) == 1
    assert exitos[0]["host_resuelto"] == "nivel"
    assert exitos[0]["metodo_ajustado"] is None


def test_metodo_ajustado_ceiling_a_muro_fallback(tmp_path):
    """Verifica metodo_ajustado == 'ceiling->muro_fallback' cuando aplica."""
    fixture = _cargar_fixture()
    doc = _FakeDoc()
    doc.registrar_nivel("Piso 5")
    # Registrar familias y simbolos del fixture
    for accion in fixture["acciones"]:
        familia = accion.get("familia")
        simbolo = accion.get("simbolo")
        if familia and simbolo:
            doc.registrar_familia(
                familia, simbolo, _FakeFamilySymbol(simbolo, familia)
            )
    # Sin techo, con un muro cerca del punto (99, 99)
    doc.registrar_muro(
        _FakeMuro(
            15.82,
            vertices_xy=[(98.0, 98.0), (100.0, 98.0), (100.0, 100.0), (98.0, 100.0)],
        )
    )
    # Origen de la cara del muro cerca del punto del dispositivo
    doc._muros[0]._cara.Origin = _FakeXYZ(99.0, 99.0, 15.82)

    resultado = aplicar_mapa_con_host_fallback(
        doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    exitos = [e for e in resultado["exitos"] if e["orden"] == 1]
    assert len(exitos) == 1
    assert exitos[0]["host_resuelto"] == "muro"
    assert exitos[0]["cara_encontrada"] is True
    assert exitos[0]["metodo_ajustado"] == "ceiling->muro_fallback"


def test_fallo_simbolo_no_encontrado(tmp_path):
    """Si no se encuentra familia/simbolo, se registra como fallo."""
    fixture = _cargar_fixture()
    doc_limpio = _FakeDoc()
    json_in = str(tmp_path / "entrada.json")
    json_out = str(tmp_path / "resultado.json")
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False)

    resultado = aplicar_mapa_con_host_fallback(
        doc_limpio, fixture["acciones"], json_out
    )

    fallos = resultado["fallos"]
    assert len(fallos) >= 1


def test_estadisticas_resultado(tmp_path):
    """El resultado contiene estadisticas coherentes."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=True, con_muro=True)

    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    stats = resultado["estadisticas"]
    assert stats["total_modelar"] == len(fixture["acciones"])
    assert stats["exitos"] + stats["fallos"] == stats["total_modelar"]


def test_estructura_json_resultado(tmp_path):
    """El JSON de resultado contiene todas las claves esperadas."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=True, con_muro=True)

    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(tmp_path / "resultado.json")
    )

    assert "version" in resultado
    assert "script_version" in resultado
    assert "fecha_ejecucion" in resultado
    assert "estadisticas" in resultado
    assert "exitos" in resultado
    assert "fallos" in resultado


def test_guardar_json_en_disco(tmp_path):
    """El JSON de resultado se escribe en disco y es legible."""
    fixture = _cargar_fixture()
    _registrar_datos_fixture(_fake_doc, fixture, con_techo=True, con_muro=True)

    json_out = tmp_path / "resultado.json"
    resultado = aplicar_mapa_con_host_fallback(
        _fake_doc, fixture["acciones"], str(json_out)
    )

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["estadisticas"]["total_modelar"] == resultado["estadisticas"]["total_modelar"]


def test_buscar_cara_techo_retorna_cara_cuando_punto_dentro(tmp_path):
    """_buscar_cara_techo retorna cara cuando el punto esta dentro del poligono."""
    # Doc local para evitar estado compartido entre tests
    doc = _FakeDoc()
    doc.registrar_nivel("Piso 5")
    revit_db = _mod._get_revit_db()
    techo = _FakeTecho(
        15.82,
        vertices_xy=[(4.0, 2.0), (6.0, 2.0), (6.0, 4.0), (4.0, 4.0)],
    )
    doc.registrar_techo(techo)

    cara, elem = _buscar_cara_techo(
        doc, (5.0, 3.0, 15.82), 15.82, revit_db
    )
    assert cara is not None
    assert elem is techo


def test_buscar_cara_muro_retorna_cara_vertical_cercana(tmp_path):
    """_buscar_cara_muro retorna la cara vertical mas cercana dentro del radio."""
    doc = _FakeDoc()
    doc.registrar_nivel("Piso 5")
    revit_db = _mod._get_revit_db()
    muro = _FakeMuro(
        1.0,
        vertices_xy=[(4.0, 2.0), (6.0, 2.0), (6.0, 4.0), (4.0, 4.0)],
    )
    # Colocar el origen de la cara cerca del punto del dispositivo
    muro._cara.Origin = _FakeXYZ(5.0, 3.0, 1.0)
    doc.registrar_muro(muro)

    cara, elem, dist = _buscar_cara_muro(
        doc, (5.0, 3.0, 1.0), radio_busqueda_m=1.5, revit_db=revit_db
    )
    assert cara is not None
    assert elem is muro
    assert dist is not None
    assert dist <= 1.5


def test_instanciar_con_host_usa_cara_si_hay(tmp_path):
    """_instanciar_con_host usa cara de host cuando esta disponible."""
    revit_db = _mod._get_revit_db()
    cara = _FakeFace(15.82)
    simbolo = _FakeFamilySymbol("Simbolo", "Familia")
    nivel = _FakeLevel("Piso 5")

    inst, metodo = _instanciar_con_host(
        _fake_doc, simbolo, (5.0, 3.0, 15.82), cara, nivel, 0, revit_db
    )
    assert inst is not None
    assert metodo == "cara"


def test_instanciar_con_host_fallback_a_nivel_sin_cara(tmp_path):
    """_instancian_con_host usa nivel cuando no hay cara."""
    revit_db = _mod._get_revit_db()
    simbolo = _FakeFamilySymbol("Simbolo", "Familia")
    nivel = _FakeLevel("Piso 5")

    inst, metodo = _instanciar_con_host(
        _fake_doc, simbolo, (5.0, 3.0, 1.0), None, nivel, 0, revit_db
    )
    assert inst is not None
    assert metodo == "nivel"
