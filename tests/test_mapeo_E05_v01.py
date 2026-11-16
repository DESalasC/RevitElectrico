# -*- coding: utf-8 -*-
"""Tests offline de F6_APLICAR_E05_v03 (sin Revit).

Verifican:

  1. `_clave()` normaliza acentos, guiones, guiones bajos y simbolos.
  2. `_resolver()` **NO** cae al primer simbolo de la familia cuando el simbolo
     pedido no existe. Ese fallback silencioso era la causa de que todos los
     interruptores salieran como `M_Interruptor` -> `Ventilador`.
  3. `_resolver()` acepta coincidencia exacta y rechaza ambiguedades.
  4. El mapeo `config/mapeo_E05_v01.json` cubre TODOS los bloques del JSON de
     transferencia, sea con una regla o con una exclusion explicita.

Ejecutar:
    pytest tests/test_mapeo_E05_v01.py -v
"""
import json
import os
import sys
import types

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_MOD = os.path.join(RAIZ, "src", "fase-6-revit", "F6_APLICAR_E05_v19.py")
CONFIG = os.path.join(RAIZ, "config", "mapeo_E05_v01.json")
TRANSFER = os.path.join(RAIZ, "data", "E05_transferencia_panel_ancla_v03.json")


# ---------------------------------------------------------------------------
# Stub de Autodesk.Revit.DB
# ---------------------------------------------------------------------------

class _Placeholder(object):
    def __init__(self, *a, **k):
        pass


def _instalar_stub():
    if "Autodesk.Revit.DB" in sys.modules and getattr(
            sys.modules["Autodesk.Revit.DB"], "_es_stub", False):
        return

    autodesk = types.ModuleType("Autodesk")
    revit = types.ModuleType("Autodesk.Revit")
    db = types.ModuleType("Autodesk.Revit.DB")
    structure = types.ModuleType("Autodesk.Revit.DB.Structure")

    db._es_stub = True
    db.BuiltInCategory = type("BuiltInCategory", (), {
        "OST_ElectricalFixtures": 1,
        "OST_ElectricalEquipment": 2,
        "OST_LightingFixtures": 3,
        "OST_LightingDevices": 4,
        "OST_DataDevices": 5,
        "OST_CommunicationDevices": 6,
        "OST_TelephoneDevices": 7,
        "OST_Walls": 8,
        "OST_Ceilings": 9,
    })
    db.BuiltInParameter = type("BuiltInParameter", (), {
        "ALL_MODEL_INSTANCE_COMMENTS": 0,
        # Ojo: a proposito NO se define ELEM_REFERENCE_LEVEL_PARAM,
        # para comprobar que la resolucion perezosa lo soporta.
    })
    for nombre in ("Family", "FamilySymbol", "FilteredElementCollector",
                   "GeometryInstance", "HostObjectUtils", "Level", "Options",
                   "Solid", "Transaction", "XYZ"):
        setattr(db, nombre, _Placeholder)

    db.ShellLayerType = type("ShellLayerType", (), {"Exterior": 0, "Interior": 1})

    structure.StructuralType = type("StructuralType", (), {"NonStructural": 0})
    db.Structure = structure

    autodesk.Revit = revit
    revit.DB = db
    sys.modules["Autodesk"] = autodesk
    sys.modules["Autodesk.Revit"] = revit
    sys.modules["Autodesk.Revit.DB"] = db
    sys.modules["Autodesk.Revit.DB.Structure"] = structure


def _cargar_modulo():
    _instalar_stub()
    src = open(SRC_MOD, "r", encoding="utf-8").read()
    mod = types.ModuleType("f6_aplicar_e05_v03")
    mod.__file__ = SRC_MOD
    exec(compile(src, SRC_MOD, "exec"), mod.__dict__)
    return mod


MOD = _cargar_modulo()


# ---------------------------------------------------------------------------
# Dobles de prueba para familias / simbolos / documento
# ---------------------------------------------------------------------------

class _Symbol(object):
    _seq = 500

    def __init__(self, name):
        self.Name = name
        _Symbol._seq += 1
        self.Id = str(_Symbol._seq)
        self.IsActive = True

    def Activate(self):
        self.IsActive = True


class _Family(object):
    def __init__(self, name, ids):
        self.Name = name
        self.Id = None
        self.FamilyCategory = None
        self._ids = list(ids)

    def GetFamilySymbolIds(self):
        return list(self._ids)


class _Doc(object):
    def __init__(self, simbolos):
        self._simbolos = simbolos  # {id: _Symbol}

    def GetElement(self, sid):
        return self._simbolos.get(sid)


def _escenario(familias_simbolos):
    """familias_simbolos: [(nombre_familia, [nombres_simbolo])]

    Devuelve (familias, tipos) con la MISMA estructura que usa v05:
      familias = {clave: {"family", "id", "name"}}
      tipos    = {clave_familia: {clave_simbolo: symbol}}
    """
    familias = {}
    tipos = {}
    fid = 900
    for nombre_fam, nombres_sym in familias_simbolos:
        kf = MOD._clave(nombre_fam)
        fam = _Family(nombre_fam, [])
        fam.Id = str(fid)
        fid += 1
        familias[kf] = {"family": fam, "id": str(fam.Id), "name": nombre_fam}
        d = {}
        for ns in nombres_sym:
            d[MOD._clave(ns)] = _Symbol(ns)
        tipos[kf] = d
    return familias, tipos


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clave_normaliza():
    assert MOD._clave("Estándar") == "estandar"
    assert MOD._clave("Estandar") == "estandar"
    # El volcado del inventario sustituye el caracter acentuado por "_",
    # por lo que la letra se pierde: 'Est_ndar' -> 'estndar'.
    assert MOD._clave("Est_ndar") == "estndar"
    assert MOD._clave("ESTANDAR") == "estandar"
    assert MOD._clave("_SONO FLEX 200 trim") == "sonoflex200trim"
    assert MOD._clave("SONO FLEX 200 trim") == "sonoflex200trim"
    assert MOD._clave("M_Toma de teléfono - Datos") == "mtomadetelefonodatos"
    assert MOD._clave(None) == ""


def test_resolver_no_cae_al_primer_simbolo():
    """El bug original: M_Interruptor solo tiene 'Ventilador' y devolvia eso."""
    familias, tipos = _escenario([("M_Interruptor", ["Ventilador"])])
    sym, err = MOD._resolver(familias, tipos, "M_Interruptor", "Estandar")
    assert sym is None, "no debe devolver un simbolo por fallback"
    assert "simbolo" in err.lower()
    assert "ventilador" in err.lower(), "el error debe listar los simbolos disponibles"


def test_resolver_coincidencia_exacta():
    familias, tipos = _escenario([
        ("M_Interruptor", ["Ventilador"]),
        ("M_Pulsador - Interruptor", ["Estándar"]),
    ])
    sym, err = MOD._resolver(familias, tipos, "M_Pulsador - Interruptor", "Estándar")
    assert sym is not None, err
    assert sym.Name == "Estándar"


def test_resolver_simbolo_con_guion_bajo_inicial():
    """En el .rfa real los tipos 150/200 aparecen como '_SONO FLEX ...'."""
    familias, tipos = _escenario([
        ("SONO FLEX trim", ["SONO FLEX 100 trim", "_SONO FLEX 150 trim",
                            "_SONO FLEX 200 trim"]),
    ])
    for pedido in ("SONO FLEX 100 trim", "SONO FLEX 150 trim", "SONO FLEX 200 trim"):
        sym, err = MOD._resolver(familias, tipos, "SONO FLEX trim", pedido)
        assert sym is not None, pedido + " -> " + err
        assert MOD._clave(sym.Name) == MOD._clave(pedido)


def test_resolver_familia_inexistente():
    familias, tipos = _escenario([("M_Toma doble", ["Estándar", "GFCI"])])
    sym, err = MOD._resolver(familias, tipos, "M_Familia que no existe", "Estándar")
    assert sym is None
    assert "familia no encontrada" in err.lower()


def test_resolver_familia_ambigua_no_adivina():
    """'M_Interruptor' es prefijo de 'M_Interruptor-Doble': no debe adivinar."""
    familias, tipos = _escenario([
        ("M_Interruptor-Doble", ["Doble"]),
        ("M_Interruptor-Triple", ["Triple"]),
    ])
    sym, err = MOD._resolver(familias, tipos, "M_Interruptor", "Doble")
    assert sym is None, "con dos candidatos parciales debe rechazar, no elegir uno"
    assert "no encontrada" in err.lower()


@pytest.mark.parametrize("bloque,familia,simbolo", [
    ("ELEC-I-S-1-5A", "M_Interruptor-simple", "Sencillo"),
    ("ELEC-I-S-C1-5A", "Keypad-Lutron-Homeworks_Sunnata", "Conmutable"),
    ("S3", "M_Interruptor-Doble", "Doble"),
    ("ELEC-F-CONTROL", "M_Interruptor", "Ventilador"),
    ("ELEC-T-GFCI-t-15A", "M_Toma doble", "GFCI"),
    ("Bala Stil Led 13W", "SONO FLEX trim", "SONO FLEX 150 trim"),
])
def test_mapeo_resuelve_contra_inventario_real(bloque, familia, simbolo):
    """Resuelve el mapeo contra el inventario real volcado de Revit."""
    inv_path = os.path.join(RAIZ, "data", "familias_electricas_reales_v01.json")
    inv = json.load(open(inv_path, "r", encoding="utf-8"))

    nombres_fam = []
    for cat in inv.values():
        for fam, info in (cat or {}).items():
            nombres_fam.append((fam, info.get("simbolos") or []))

    familias, tipos = _escenario(nombres_fam)

    cfg = json.load(open(CONFIG, "r", encoding="utf-8"))
    regla = cfg["dispositivos"][bloque]
    assert regla["familia"] == familia
    assert regla["simbolo"] == simbolo

    # El inventario fue volcado con caracteres no-ASCII sustituidos por "_",
    # asi que se acepta coincidencia exacta o por subsecuencia.
    sym, err = MOD._resolver(familias, tipos, familia, simbolo)
    if sym is None:
        kf = MOD._clave(familia)
        kk = MOD._clave(simbolo)
        if kf not in familias:
            pytest.skip("la familia '{}' no esta en el inventario del 2026-11-08 "
                        "(ese volcado solo lista familias con instancias)".format(familia))
        syms = list((tipos.get(kf) or {}).keys())
        assert any(_parecido(kk, s) for s in syms), \
            "simbolo {} no aparece en {}: {}".format(simbolo, familia, sorted(syms))


def _parecido(a, b):
    """Tolerante a la perdida de vocales acentuadas en el volcado."""
    if a == b:
        return True
    if a and b and (a in b or b in a):
        return True
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def test_todos_los_bloques_del_transfer_estan_cubiertos():
    cfg = json.load(open(CONFIG, "r", encoding="utf-8"))
    disp = cfg["dispositivos"]
    excl = cfg["excluir"]
    data = json.load(open(TRANSFER, "r", encoding="utf-8"))

    faltantes = set()
    for d in data["dispositivos"]:
        b = d["nombre_bloque_hijo"]
        if b in disp or b in excl:
            continue
        faltantes.add(b)
    assert not faltantes, "bloques sin regla ni exclusion: {}".format(sorted(faltantes))


def test_ninguna_regla_usa_simbolo_generico_inexistente():
    """'Estandar' generico fue el origen del fallo: el mapeo no debe usarlo
    para familias que no lo tengan."""
    cfg = json.load(open(CONFIG, "r", encoding="utf-8"))
    canonicos = cfg["simbolos_canonicos"]
    for bloque, regla in cfg["dispositivos"].items():
        fam = regla["familia"]
        sym = regla["simbolo"]
        assert fam in canonicos, "familia {} sin lista de simbolos canonicos".format(fam)
        assert MOD._clave(sym) in [MOD._clave(s) for s in canonicos[fam]], \
            "{}: simbolo '{}' no esta en la lista canonica de {}".format(bloque, sym, fam)


def test_leer_json_respeta_utf8(tmp_path):
    """Regresion del 2026-11-09: IronPython 2.7 leia los .json como bytes y
    'Estándar' llegaba como 'EstÃ¡ndar', de modo que ninguna familia ni simbolo
    con acento resolvia."""
    p = tmp_path / "prueba.json"
    p.write_text(u'{"s": "Est\u00e1ndar", "f": "M_Toma de tel\u00e9fono - Datos"}',
                 encoding="utf-8")
    datos = MOD._leer_json(str(p))
    assert datos["s"] == u"Est\u00e1ndar", "se perdio el acento al leer"
    assert MOD._clave(datos["s"]) == "estandar"
    assert MOD._clave(datos["f"]) == "mtomadetelefonodatos"


def test_config_real_lee_acentos_correctamente():
    cfg = MOD._leer_json(CONFIG)
    assert cfg["dispositivos"]["ELEC-T-D-t-15A"]["simbolo"] == u"Est\u00e1ndar"
    assert cfg["dispositivos"]["ELEC-TEL"]["familia"] == u"M_Toma de tel\u00e9fono - Datos"


# ---------------------------------------------------------------------------
# Guarda de unidades (hallazgo del 2026-11-09)
#
# Revit guarda las elevaciones en PIES. El JSON de transferencia tenia
# 'elevacion_nivel_m': 43.3727, que en realidad eran pies (= 13.219999 m).
# ---------------------------------------------------------------------------

class _Nivel(object):
    def __init__(self, elev_ft):
        self.Elevation = elev_ft


def test_pies_dentro_de_clave_metros_se_detectan():
    nivel = _Nivel(43.3727)  # Piso 5, pies internos de Revit
    m, aviso = MOD._revisar_unidades_elevacion({"elevacion_nivel_m": 43.3727}, nivel)
    assert abs(m - 13.22) < 0.001, "la elevacion viva debe ser 13.22 m"
    assert "PIES" in aviso, "debe avisar del error de unidades"


def test_elevacion_ya_en_metros_no_avisa():
    nivel = _Nivel(43.3727)
    m, aviso = MOD._revisar_unidades_elevacion({"elevacion_nivel_m": 13.22}, nivel)
    assert abs(m - 13.22) < 0.001
    assert aviso == ""


def test_elevacion_ausente_no_rompe():
    nivel = _Nivel(43.3727)
    m, aviso = MOD._revisar_unidades_elevacion({}, nivel)
    assert abs(m - 13.22) < 0.001
    assert aviso == ""


def test_z_local_implausible_se_detecta():
    assert MOD._revisar_unidades_z_local([{"nombre_bloque_hijo": "X", "z_local_m": 13.52}])
    assert MOD._revisar_unidades_z_local([{"nombre_bloque_hijo": "X", "z_local_m": 2.6}]) == []


def test_transfer_ya_quedo_en_metros():
    """Tras la correccion, el JSON debe declarar 13.22 m y no avisar."""
    d = MOD._leer_json(TRANSFER)
    m, aviso = MOD._revisar_unidades_elevacion(d, _Nivel(43.3727))
    assert aviso == "", "el JSON de transferencia sigue con unidades inconsistentes: " + aviso
    assert abs(d["elevacion_nivel_m"] - 13.22) < 0.001
    for x in d["dispositivos"]:
        assert float(x["z_local_m"]) < 6.0
        assert abs(float(x["z_abs_m"]) - (13.22 + float(x["z_local_m"]))) < 0.001


# ---------------------------------------------------------------------------
# Documento opcional (NameError: name 'doc' is not defined)
#
# En la pyRevit Python Shell las variables se pierden al reiniciar la sesion.
# Llamar diagnosticar(doc) sin haber definido doc fallaba antes de entrar.
# ---------------------------------------------------------------------------

def test_resolver_doc_sin_revit_devuelve_none():
    assert MOD._resolver_doc(None) is None


def test_resolver_doc_respeta_el_documento_pasado():
    centinela = object()
    assert MOD._resolver_doc(centinela) is centinela


def test_aplicar_sin_documento_no_lanza():
    r = MOD.aplicar(confirmar=False)
    assert r.get("ok") is False


def test_guardar_escribe_ascii_sin_fallo_de_codec(tmp_path):
    """Regresion 2026-11-09: json.dump sobre io.open('w', encoding='utf-8')
    fallaba con "'unknown' codec can't decode byte 0xe9" al haber acentos.
    """
    p = str(tmp_path / "x.json")
    assert MOD._guardar(p, {"s": u"Estándar", "f": u"M_Toma de teléfono - Datos"})
    raw = open(p, "rb").read()
    assert b"\\u00e1" in raw, "debe escapar los acentos a ASCII"
    datos = json.loads(raw.decode("ascii"))
    assert datos["s"] == u"Estándar"


# ---------------------------------------------------------------------------
# Altura de montaje cuando el mapeo fuerza techo
#
# Regresion 14:36: las 4 'Bala Stil Led 13W' traian z_local_m = 0.30 pero el
# mapeo las fuerza a techo; se buscaba un cielorraso a 13.52 m y no existe
# (el falso techo esta a 15.82 m), asi que fallaban con "sin cara de anfitrion".
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("z_json,es_techo,esperado_z,esperado_ajuste", [
    (0.30, True, 2.60, True),    # lampara de muro forzada a techo
    (2.60, True, 2.60, False),   # lampara ya correcta
    (0.30, False, 0.30, False),  # toma en muro
    (1.10, False, 1.10, False),  # interruptor en muro
    (2.60, False, 2.60, False),  # interruptor de techo
])
def test_z_objetivo_corrige_lampara_forzada_a_techo(z_json, es_techo,
                                                    esperado_z, esperado_ajuste):
    z, ajustada = MOD._z_objetivo_m({"z_local_m": z_json}, es_techo)
    assert abs(z - esperado_z) < 1e-9
    assert ajustada is esperado_ajuste


def test_z_objetivo_respeta_el_mapeo():
    """Los interruptores vienen del JSON a 2.60 m en techo; el mapeo los baja a 1.10."""
    z, ajustada = MOD._z_objetivo_m({"z_local_m": 2.6}, False, 1.10)
    assert abs(z - 1.10) < 1e-9
    assert ajustada is True, "debe marcar que se cambio respecto al JSON"


def test_interruptores_van_a_muro_a_1_10():
    cfg = MOD._leer_json(CONFIG)
    for bloque in ("ELEC-I-S-1-5A", "ELEC-I-S-C1-5A", "S3"):
        regla = cfg["dispositivos"][bloque]
        assert regla["anfitrion"] == "muro", bloque + " debe ir en muro"
        assert abs(float(regla["z_local_m"]) - 1.10) < 1e-9, bloque + " debe ir a 1.10 m"


def test_conmutado_usa_la_familia_lutron():
    cfg = MOD._leer_json(CONFIG)
    regla = cfg["dispositivos"]["ELEC-I-S-C1-5A"]
    assert regla["familia"] == "Keypad-Lutron-Homeworks_Sunnata"
    assert regla["simbolo"] == "Conmutable"
    assert "Keypad-Lutron-Homeworks_Sunnata" in cfg["simbolos_canonicos"]


# ---------------------------------------------------------------------------
# Nombre del metodo de geometria
#
# Regresion 2026-11-09: el metodo correcto es 'get_Geometry' (g minuscula).
# v09 uso 'get_geometry' y v10/v11 'GetGeometry': ambos daban
# "'Wall' object has no attribute 'GetGeometry'" y se perdian las caras.
# ---------------------------------------------------------------------------

def test_metodo_geometria_correcto_primero():
    assert MOD._METODOS_GEOMETRIA[0] == "get_Geometry"
    assert "get_Geometry" in MOD._METODOS_GEOMETRIA


def test_exclusion_por_bloque_y_capa_en_el_mapeo():
    """El bloque Bala Stil Led 13W insertado en la capa de tuberia no se modela."""
    cfg = MOD._leer_json(CONFIG)
    reglas = cfg.get("excluir_por_bloque_y_capa") or {}
    assert "Bala Stil Led 13W" in reglas
    assert "ELEC-POWER- PIPE" in reglas["Bala Stil Led 13W"]


def test_el_espurio_queda_fuera_del_conteo():
    """49 en transferencia - 2 marcadores - 1 espurio = 46 a modelar."""
    cfg = MOD._leer_json(CONFIG)
    excl = cfg.get("excluir") or {}
    excl_capa = cfg.get("excluir_por_bloque_y_capa") or {}
    data = MOD._leer_json(TRANSFER)

    modelables = 0
    for d in data["dispositivos"]:
        b = d["nombre_bloque_hijo"]
        if b in excl:
            continue
        if (d.get("capa") or "") in (excl_capa.get(b) or []):
            continue
        modelables += 1
    assert modelables == 46, "se esperaban 46 dispositivos modelables, hay {}".format(modelables)


def test_geometria_tolera_objeto_sin_metodos():
    class _SinNada(object):
        Name = "host de prueba"

    MOD._ERRORES_CARAS[:] = []
    assert MOD._geometria(_SinNada()) is None
    assert MOD._ERRORES_CARAS, "debe registrar el fallo, no callarlo"


def test_geometria_usa_el_primer_nombre_disponible():
    class _ConMetodo(object):
        Name = "host con get_Geometry"

        def get_Geometry(self, opts):
            return ["geo"]

    MOD._GEOMETRIA_OK[:] = []
    assert MOD._geometria(_ConMetodo()) == ["geo"]
    assert MOD._GEOMETRIA_OK[0] == "get_Geometry"
