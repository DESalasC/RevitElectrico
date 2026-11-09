# -*- coding: utf-8 -*-
"""
RE_NIVELES_RVT_v01.py — Niveles en el RVT activo para RevitElectrico (T5-SantaMarta)
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
IronPython 2.7 (Dentro de Revit / pyRevit) — SIN type hints, SIN f-strings, SIN requests/bs4.

OBJETIVO:
  Listar los niveles del RVT activo, comparar con los niveles del RVT referenciado
  (prueba 01), y crear/mapear el nivel "Piso 5" si falta, para que el modelado
  de dispositivos electricos quede anclado al nivel correcto (Piso 5 a 13.22 m /
  43.37 pies) en lugar de al nivel por defecto de la plantilla MEP
  ("Flor plan 1 - Lighting").

USO (desde dentro de Revit con pyRevit):
  pyrevit run RE_NIVELES_RVT_v01.py --json-out <niveles.json>
  # o desde RevitPythonShell:
  exec(open(r"...\RE_NIVELES_RVT_v01.py").read())
  asegurar_nivel_piso5(doc)

NOTAS:
  - pyRevit provee __revit__ como UIApplication.
  - Usar .format() y concatenación de strings (no f-strings).
  - No usar type hints ni requests/bs4.
  - Los imports de Revit API se hacen dentro de las funciones para poder
    probar la lógica en CPython 3.12 sin Revit instalado (inyectando
    Autodesk.Revit.DB en sys.modules).


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import json
import os
from datetime import datetime


DEFAULT_NIVEL_PISO5 = "Piso 5"
ELEVACION_PISO5_M = 13.22  # metros
ELEVACION_PISO5_PIES = 43.37  # pies (13.22 m * 3.28084)


def _ascii_safe(valor):
    """Convierte un valor a string seguro para ASCII (IronPython 2.7)."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    try:
        return str(valor).encode("ascii", "replace").decode("ascii")
    except Exception:
        return "?"


def _sanitizar_dict(d):
    """Sanitiza recursivamente todos los strings de un diccionario o lista."""
    if isinstance(d, dict):
        return {_ascii_safe(k): _sanitizar_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_sanitizar_dict(v) for v in d]
    elif isinstance(d, tuple):
        return tuple(_sanitizar_dict(v) for v in d)
    else:
        return _ascii_safe(d)


def _cargar_json(ruta):
    with open(ruta, "r") as f:
        return json.load(f)


def _guardar_json(ruta, datos):
    dirpath = os.path.dirname(ruta)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(ruta, "w") as f:
        # IronPython 2.7 no soporta encoding="utf-8" en open().
        datos_limpios = _sanitizar_dict(datos)
        contenido = json.dumps(datos_limpios, indent=2, ensure_ascii=True)
        f.write(contenido)


# ---------------------------------------------------------------------------
# Helpers de la API de Revit (se importan perezosamente dentro de cada
# función para permitir pruebas en CPython 3.12 sin Revit).
# ---------------------------------------------------------------------------

def _import_revit_db():
    """
    Obtiene las clases de la API de Revit.

    En pruebas (CPython 3.12) se usa el módulo ya inyectado en
    sys.modules["Autodesk.Revit.DB"] por el harness de tests (mocks).
    En Revit / IronPython real se importa la API verdadera mediante clr.
    """
    import sys

    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": mock_db.FilteredElementCollector,
            "BuiltInCategory": mock_db.BuiltInCategory,
            "Level": mock_db.Level,
            "Transaction": mock_db.Transaction,
            "XYZ": mock_db.XYZ,
            "UnitUtils": mock_db.UnitUtils,
            "UnitTypeId": mock_db.UnitTypeId,
        }

    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        BuiltInCategory,
        Level,
        Transaction,
        XYZ,
        UnitUtils,
        UnitTypeId,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "Level": Level,
        "Transaction": Transaction,
        "XYZ": XYZ,
        "UnitUtils": UnitUtils,
        "UnitTypeId": UnitTypeId,
    }


def _get_revit_db():
    """Obtiene el diccionario de la API de Revit, importando si es necesario."""
    return _import_revit_db()


def _obtener_nombre_elemento(elemento, revit_db):
    """
    Obtiene el nombre legible de un elemento de Revit.
    Probamos: propiedad Name directa, luego parametro ALL_MODEL_TYPE_NAME.
    """
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass

    try:
        BuiltInParameter = revit_db.get("BuiltInParameter")
        if BuiltInParameter is None:
            import Autodesk.Revit.DB as _db
            BuiltInParameter = _db.BuiltInParameter
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass

    return None


def _nivel_coincide(nombre_obtenido, nombre_esperado):
    """Compara dos nombres de nivel de forma case-insensitive."""
    if not nombre_obtenido or not nombre_esperado:
        return False
    return nombre_obtenido.strip().lower() == nombre_esperado.strip().lower()


def _mm_a_pies(mm, revit_db):
    """Convierte milimetros a pies internos de Revit usando UnitUtils."""
    UnitUtils = None
    UnitTypeId = None
    if isinstance(revit_db, dict):
        UnitUtils = revit_db.get("UnitUtils")
        UnitTypeId = revit_db.get("UnitTypeId")
    else:
        UnitUtils = getattr(revit_db, "UnitUtils", None)
        UnitTypeId = getattr(revit_db, "UnitTypeId", None)
    if UnitUtils is not None and UnitTypeId is not None:
        try:
            return UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters)
        except Exception:
            pass
    # Fallback: 1 pie = 304.8 mm
    return mm / 304.8


# ---------------------------------------------------------------------------
# Funciones principales de niveles
# ---------------------------------------------------------------------------

def _listar_niveles(doc, revit_db=None):
    """
    Devuelve una lista de dicts {id, nombre, elevacion_m, elevacion_pies}
    para todos los niveles del documento usando
    FilteredElementCollector(doc).OfClass(Level).
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Level = revit_db.get("Level")

    niveles = []
    colector = FilteredElementCollector(doc).OfClass(Level)
    for nivel in colector.ToElements():
        try:
            if getattr(nivel, "IsElementType", False):
                continue
        except Exception:
            pass

        nombre = _obtener_nombre_elemento(nivel, revit_db)
        id_str = nivel.Id.ToString() if hasattr(nivel, "Id") else "?"

        # Elevación: Revit almacena en pies internos; intentar convertir a metros
        elevacion_pies = None
        elevacion_m = None
        try:
            elevacion_pies = nivel.Elevation
        except Exception:
            elevacion_pies = None

        if elevacion_pies is not None:
            # Convertir pies a metros: 1 pie = 0.3048 m
            elevacion_m = elevacion_pies * 0.3048

        niveles.append({
            "id": id_str,
            "nombre": nombre,
            "elevacion_pies": elevacion_pies,
            "elevacion_m": elevacion_m,
        })

    return niveles


def _nivel_existe(doc, nombre_nivel, revit_db=None):
    """Devuelve True si existe un nivel con el nombre dado (case-insensitive)."""
    if revit_db is None:
        revit_db = _get_revit_db()

    for n in _listar_niveles(doc, revit_db):
        if _nivel_coincide(n["nombre"], nombre_nivel):
            return True
    return False


def _obtener_nivel_por_nombre(doc, nombre_nivel, revit_db=None):
    """
    Devuelve el elemento Level cuyo nombre coincida (case-insensitive),
    o None si no existe.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Level = revit_db.get("Level")

    colector = FilteredElementCollector(doc).OfClass(Level)
    for nivel in colector.ToElements():
        try:
            if getattr(nivel, "IsElementType", False):
                continue
        except Exception:
            pass

        nombre = _obtener_nombre_elemento(nivel, revit_db)
        if _nivel_coincide(nombre, nombre_nivel):
            return nivel
    return None


def _crear_nivel(doc, nombre_nivel, elevacion_pies, revit_db=None):
    """
    Crea un nuevo nivel en el documento con Level.Create(doc, elevacion_pies)
    dentro de una Transaction. Retorna el elemento Level creado o None.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    Level = revit_db["Level"]
    Transaction = revit_db["Transaction"]

    trans = Transaction(doc, "Crear nivel {}".format(nombre_nivel))
    trans.Start()
    try:
        nuevo_nivel = Level.Create(doc, elevacion_pies)
        # Intentar establecer el nombre del nivel (en Revit real, Level.Create
        # asigna un nombre automatico; se puede renombrar despues).
        try:
            nuevo_nivel.Name = nombre_nivel
        except Exception:
            pass
        trans.Commit()
        return nuevo_nivel
    except Exception:
        trans.RollBack()
        return None


def asegurar_nivel_piso5(doc, elevacion_m=ELEVACION_PISO5_M, revit_db=None):
    """
    Si no existe el nivel "Piso 5" en el documento, lo crea con la elevación
    indicada (default 13.22 m = 43.37 pies). Retorna el ElementId del nivel
    "Piso 5" (existente o recién creado) o None si no se pudo crear.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    if _nivel_existe(doc, DEFAULT_NIVEL_PISO5, revit_db):
        nivel = _obtener_nivel_por_nombre(doc, DEFAULT_NIVEL_PISO5, revit_db)
        if nivel is not None:
            return nivel.Id
        return None

    elevacion_pies = _mm_a_pies(elevacion_m * 1000.0, revit_db)
    nuevo_nivel = _crear_nivel(doc, DEFAULT_NIVEL_PISO5, elevacion_pies, revit_db)
    if nuevo_nivel is not None:
        return nuevo_nivel.Id
    return None


def mapear_nivel_referenciado(doc_activo, doc_referenciado, nombre_nivel, revit_db=None):
    """
    Busca el nivel con el nombre dado en el RVT referenciado y retorna su
    elevación en metros para replicar en el documento activo.
    Retorna (elevacion_m, encontrado) donde encontrado es un booleano.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    niveles_ref = _listar_niveles(doc_referenciado, revit_db)
    for n in niveles_ref:
        if _nivel_coincide(n["nombre"], nombre_nivel):
            return n["elevacion_m"], True
    return None, False


# ---------------------------------------------------------------------------
# Resultado consolidado (JSON)
# ---------------------------------------------------------------------------

def listar_niveles_resultado(doc, revit_db=None):
    """
    Devuelve un diccionario con la lista de niveles del documento y el
    estado del nivel "Piso 5". Listo para serializar a JSON.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    niveles = _listar_niveles(doc, revit_db)
    piso5_existe = _nivel_existe(doc, DEFAULT_NIVEL_PISO5, revit_db)
    piso5_id = None
    if piso5_existe:
        nivel = _obtener_nivel_por_nombre(doc, DEFAULT_NIVEL_PISO5, revit_db)
        if nivel is not None:
            piso5_id = nivel.Id.ToString() if hasattr(nivel, "Id") else None

    return {
        "niveles": niveles,
        "total_niveles": len(niveles),
        "nivel_piso5": DEFAULT_NIVEL_PISO5,
        "piso5_existe": piso5_existe,
        "piso5_id": piso5_id,
        "elevacion_piso5_m": ELEVACION_PISO5_M,
        "elevacion_piso5_pies": ELEVACION_PISO5_PIES,
    }


# ---------------------------------------------------------------------------
# main (CLI para ejecutar dentro de Revit / pyRevit)
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("RE_NIVELES_RVT_v01 — Niveles en RVT activo (Revit 2026)")
    print("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)

    revit_db = _get_revit_db()

    # pyRevit provee __revit__ como UIApplication.
    app = __revit__.Application
    uidoc = __revit__.ActiveUIDocument

    doc = None
    if uidoc is not None:
        doc = uidoc.Document
    else:
        try:
            docs = app.Documents
            if docs is not None and docs.Size > 0:
                doc = docs.get_Item(0)
        except Exception:
            doc = None

    if doc is None:
        print("ERROR: No hay un documento de Revit activo abierto.")
        return {
            "conectado": False,
            "documento_activo": False,
        }

    print("Documento: {}".format(doc.Title))

    import argparse

    parser = argparse.ArgumentParser(
        description="Lista y asegura niveles en el RVT activo (RevitElectrico)."
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de salida con la lista de niveles",
    )
    parser.add_argument(
        "--crear-piso5",
        action="store_true",
        default=False,
        help="Crear el nivel 'Piso 5' si no existe (13.22 m / 43.37 pies)",
    )
    parser.add_argument(
        "--elevacion-piso5",
        type=float,
        default=ELEVACION_PISO5_M,
        help="Elevación del nivel Piso 5 en metros (default: 13.22)",
    )

    args = parser.parse_args()

    # Listar niveles actuales
    resultado = listar_niveles_resultado(doc, revit_db)
    print("Niveles encontrados: {}".format(resultado["total_niveles"]))
    for n in resultado["niveles"]:
        print("  - {} | id={} | elevacion={} m".format(
            n["nombre"], n["id"], n["elevacion_m"]))

    print("Nivel 'Piso 5' existe: {}".format(resultado["piso5_existe"]))

    # Crear Piso 5 si se solicita y no existe
    if args.crear_piso5 and not resultado["piso5_existe"]:
        print("Creando nivel 'Piso 5' a {} m...".format(args.elevacion_piso5))
        piso5_id = asegurar_nivel_piso5(doc, args.elevacion_piso5, revit_db)
        if piso5_id is not None:
            print("Nivel 'Piso 5' creado con id={}".format(piso5_id))
            resultado["piso5_existe"] = True
            resultado["piso5_id"] = str(piso5_id)
        else:
            print("FALLO: no se pudo crear el nivel 'Piso 5'")

    # Guardar JSON de salida si se solicita
    if args.json_out:
        _guardar_json(args.json_out, resultado)
        print("JSON guardado en: {}".format(args.json_out))

    print("=" * 60)
    return resultado


if __name__ == "__main__":
    main()
