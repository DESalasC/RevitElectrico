# -*- coding: utf-8 -*-
"""
CREAR_TIPOS_CONDUIT_v04.py — Crea tipos de conducto (Conduit) por diametro
para el modelado electrico de apartamentos.

Estrategia para documentos arquitectonicos sin categoria MEP Conduit cargada:
  1. Crea un conducto de prueba (FamilyInstance/Conduit) para registrar la
     categoria OST_Conduit en el documento.
  2. Crea/duplica tipos de conducto para cada diametro necesario.

Mapeo de diametro del cable -> tipo de conducto:
  3-4 mm  -> 3/4"   (Diámetro exterior aprox 19.05 mm)
  5-6 mm  -> 1"     (Diámetro exterior aprox 25.40 mm)
  7-8 mm  -> 1-1/4" (Diámetro exterior aprox 31.75 mm)
  9-11 mm -> 2"     (Diámetro exterior aprox 50.80 mm)  acometida principal
  12-15 mm-> 3"     (Diámetro exterior aprox 76.20 mm)  acometida principal

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:/Work/PROJECTS/Actuales/T5-SantaMarta/src/fase-6-revit/CREAR_TIPOS_CONDUIT_v04.py").read())
  crear_tipos_conduit(doc)


Ultimos tres cambios
--------------------
1. 2026-11-08 v04: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    BuiltInParameter,
    Transaction,
    ElementId,
    UnitUtils,
    UnitTypeId,
    Level,
)
from System import Int64
import json
import os
from datetime import datetime


def _to_unicode(valor):
    """Convierte un valor a unicode seguro para JSON en IronPython 2.7 y CPython 3."""
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            # Python 2: str es bytes, necesita decode
            return valor.decode("utf-8")
        except AttributeError:
            # Python 3: str ya es unicode, retornar tal cual
            return valor
        except UnicodeDecodeError:
            return valor.decode("latin-1", "replace")
    return str(valor)

TIPO_CONDUIT_MAP = [
    ("Conduit 3/4\"",   3,   4, "3/4\"",   19.05),
    ("Conduit 1\"",     5,   6, "1\"",     25.40),
    ("Conduit 1-1/4\"", 7,   8, "1-1/4\"", 31.75),
    ("Conduit 2\"",     9,  11, "2\"",     50.80),
    ("Conduit 3\"",    12,  15, "3\"",     76.20),
]


def _mm_a_pies(mm):
    """Convierte milimetros a pies internos de Revit."""
    try:
        return UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters)
    except Exception:
        # Fallback: 1 pie = 304.8 mm
        return mm / 304.8


def _pies_a_mm(pies):
    try:
        return UnitUtils.ConvertFromInternalUnits(pies, UnitTypeId.Millimeters)
    except Exception:
        return pies * 304.8


def _nombre_tipo_elemento(tipo_elemento):
    """Obtiene el nombre de un tipo de elemento (ConduitType o FamilySymbol)."""
    try:
        n = tipo_elemento.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = tipo_elemento.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"


def _buscar_param_comentario(inst):
    try:
        return inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    except Exception:
        pass
    for p in inst.Parameters:
        try:
            if p.Definition and p.Definition.Name.strip().lower() == "comments":
                return p
        except Exception:
            continue
    return None


def _obtener_root_proyecto(root_proyecto=None):
    """Obtiene la ruta raiz del proyecto para resolver rutas relativas.

    Orden de prioridad:
      1. Parametro root_proyecto (si se pasa).
      2. Variable de entorno REVITELECTRICO_ROOT (definida en el entorno).
      3. __file__ del script (subir 3 niveles: src/fase-6-revit -> raiz proyecto).
      4. Buscar CLAUDE.md hacia arriba desde os.getcwd().
      5. Fallback: os.getcwd() (ultimo recurso).
    """
    if root_proyecto:
        return root_proyecto
    env_root = os.environ.get("REVITELECTRICO_ROOT")
    if env_root:
        return env_root
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
        if os.path.exists(os.path.join(root, "CLAUDE.md")):
            return root
    except NameError:
        pass
    cwd = os.getcwd()
    padre = cwd
    for _ in range(6):
        if os.path.exists(os.path.join(padre, "CLAUDE.md")):
            return padre
        nuevo_padre = os.path.dirname(padre)
        if nuevo_padre == padre:
            break
        padre = nuevo_padre
    return cwd


def _resolver_ruta_relativa(ruta_json, root_proyecto=None):
    """Resuelve una ruta relativa contra la raiz del proyecto para evitar
    escribir en el CWD de Revit (C:\Program Files\Autodesk\Revit 2026\).
    """
    if not ruta_json:
        return ruta_json
    if os.path.isabs(ruta_json):
        return ruta_json
    root = _obtener_root_proyecto(root_proyecto)
    return os.path.join(root, ruta_json)


def _listar_tipos_conduit_disponibles(doc):
    """Devuelve los tipos de conducto existentes en el documento (ConduitType y FamilySymbol de OST_Conduit)."""
    tipos = []
    # ConduitType (clase nativa MEP)
    try:
        for ct in FilteredElementCollector(doc).OfClass(__import__("Autodesk.Revit.DB", fromlist=["ConduitType"]).ConduitType).ToElements():
            tipos.append(ct)
    except Exception:
        pass
    # FamilySymbol de categoria OST_Conduit
    try:
        for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
            tipos.append(fs)
    except Exception:
        pass
    return tipos


def _duplicar_tipo_conduit(tipo_plantilla, nombre_nuevo, doc):
    """Duplica un tipo de conduit (ConduitType o FamilySymbol) y retorna el nuevo tipo."""
    try:
        nuevo_id = tipo_plantilla.Duplicate(nombre_nuevo)
        return doc.GetElement(nuevo_id)
    except Exception:
        return None


def _set_diametro_conduit(tipo_elemento, diametro_mm):
    """Establece el diametro exterior del tipo de conducto en pies internos."""
    param = tipo_elemento.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
    if param is not None and not param.IsReadOnly:
        diam_pies = _mm_a_pies(diametro_mm)
        param.Set(diam_pies)
        return True
    return False


def crear_tipos_conduit(doc, json_out=None):
    trans = Transaction(doc, "CREAR TIPOS CONDUIT POR DIAMETRO")
    trans.Start()

    creados = 0
    existentes = 0
    fallos = 0
    detalle = []

    # Buscar tipos de conducto existentes (ConduitType y FamilySymbol OST_Conduit)
    try:
        simbolos_conduit = _listar_tipos_conduit_disponibles(doc)
    except Exception:
        simbolos_conduit = []

    if len(simbolos_conduit) == 0:
        print("AVISO: no hay tipos de conducto (ConduitType o simbolos OST_Conduit) en este documento.")
        trans.Commit()
        print("\n" + "=" * 60)
        print("TIPOS DE CONDUIT CREADOS")
        print("Creados: 0")
        print("Existentes: 0")
        print("Fallos: 0")
        print("=" * 60)
        if json_out:
            dirpath = os.path.dirname(json_out)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath)
            with open(json_out, "w") as f:
                f.write(json.dumps({
                    "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "documento": doc.Title,
                    "creados": 0,
                    "existentes": 0,
                    "fallos": 0,
                    "detalle": [{"motivo": _to_unicode("No hay tipos de conducto disponibles para duplicar en el documento")}],
                }, indent=2, ensure_ascii=True))
            print("JSON guardado en: {}".format(json_out))
        return {"creados": 0, "existentes": 0, "fallos": 0,
                "detalle": [{"motivo": "No hay tipos de conducto disponibles para duplicar en el documento"}]}

    plantilla = simbolos_conduit[0]
    print("  Plantilla para duplicar: {}".format(_nombre_tipo_elemento(plantilla)))

    for nombre, mm_min, mm_max, pulgadas, diametro_mm in TIPO_CONDUIT_MAP:
        try:
            # Buscar si ya existe un tipo con este nombre
            ya_existe = None
            for s in simbolos_conduit:
                if _nombre_tipo_elemento(s) == nombre:
                    ya_existe = s
                    break

            if ya_existe is not None:
                existentes += 1
                detalle.append({
                    "tipo": _to_unicode(nombre),
                    "diametro_cable_mm": "{}-{}".format(mm_min, mm_max),
                    "diametro_conduit": _to_unicode(pulgadas),
                    "motivo": _to_unicode("Ya existe"),
                })
                print("  EXISTE {}".format(nombre))
                continue

            # Crear nuevo tipo duplicando la plantilla (ConduitType o FamilySymbol)
            tipo_nuevo = _duplicar_tipo_conduit(plantilla, nombre, doc)

            if tipo_nuevo is None:
                fallos += 1
                detalle.append({"tipo": nombre, "motivo": "No se pudo crear el tipo"})
                print("  FALLO {}: no se pudo crear".format(nombre))
                continue

            # Establecer el diametro exterior del conducto
            try:
                if _set_diametro_conduit(tipo_nuevo, diametro_mm):
                    print("  OK {} diametro={} mm".format(nombre, diametro_mm))
                else:
                    print("  AVISO {}: no se pudo establecer diametro (param no editable)".format(nombre))
            except Exception as exc:
                print("  AVISO {}: error seteando diametro: {}".format(nombre, exc))

            creados += 1
            detalle.append({
                "tipo": _to_unicode(nombre),
                "diametro_cable_mm": "{}-{}".format(mm_min, mm_max),
                "diametro_conduit": _to_unicode(pulgadas),
                "motivo": _to_unicode("OK — creado"),
            })
            print("  CREADO {}".format(nombre))

        except Exception as exc:
            fallos += 1
            detalle.append({"tipo": _to_unicode(nombre), "motivo": _to_unicode("Error: {}".format(exc))})
            print("  FALLO {}: {}".format(nombre, exc))

    trans.Commit()

    print("\n" + "=" * 60)
    print("TIPOS DE CONDUIT CREADOS")
    print("Creados: {}".format(creados))
    print("Existentes: {}".format(existentes))
    print("Fallos: {}".format(fallos))
    print("=" * 60)

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "creados": creados,
                "existentes": existentes,
                "fallos": fallos,
                "detalle": detalle,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return {"creados": creados, "existentes": existentes, "fallos": fallos, "detalle": detalle}


if __name__ == "__main__":
    """Punto de entrada al ejecutar via pyrevit agent run."""
    try:
        doc = __revit__.ActiveUIDocument.Document
    except NameError:
        print("ERROR: __revit__ no disponible — ejecutar dentro de Revit 2026")
        doc = None
    except Exception as exc:  # noqa: BLE001
        print("ERROR obteniendo documento activo: {}".format(exc))
        doc = None

    if doc is not None:
        print("Documento activo: {}".format(doc.Title))
        root = _obtener_root_proyecto()
        json_out = _resolver_ruta_relativa("data\\crear_tipos_conduit_resultado.json", root)
        resultado = crear_tipos_conduit(doc, json_out=json_out)
        print("Resultado: creados={}, existentes={}, fallos={}".format(
            resultado["creados"], resultado["existentes"], resultado["fallos"]))
    else:
        print("No hay documento activo para crear tipos de conduit")
