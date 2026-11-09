# -*- coding: utf-8 -*-
"""
DIAGNOSTICAR_VISIBILIDAD_v01.py — Diagnostica FamilyInstance en Revit para
entender por qué los componentes no se ven en el Apartamento Tipo F 02.

Lista todas las FamilyInstance del documento con:
  - Id, Nombre de familia, Nombre de símbolo
  - Location.Point (XYZ) si disponible
  - LevelId y nombre del nivel
  - Categoría (BuiltInCategory)
  - Es face-based (host = cara) o level-based

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:/Work/PROJECTS/Actuales/T5-SantaMarta/src/fase-6-revit/DIAGNOSTICAR_VISIBILIDAD_v01.py").read())
  diagnosticar_visibilidad(doc, json_out="data/diagnostico_visibilidad_v01.json")


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import clr
try:
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
except Exception:
    pass
try:
    clr.AddReference("System")
except Exception:
    pass

try:
    from Autodesk.Revit.DB import FilteredElementCollector
except Exception:
    FilteredElementCollector = None
try:
    from Autodesk.Revit.DB import FamilyInstance
except Exception:
    FamilyInstance = None
try:
    from Autodesk.Revit.DB import BuiltInCategory
except Exception:
    BuiltInCategory = None
try:
    from Autodesk.Revit.DB import Level
except Exception:
    Level = None
try:
    from Autodesk.Revit.DB import BuiltInParameter
except Exception:
    BuiltInParameter = None
try:
    from Autodesk.Revit.DB import XYZ
except Exception:
    XYZ = None
try:
    from Autodesk.Revit.DB import LocationPoint
except Exception:
    LocationPoint = None
import json
import os


def _to_unicode(valor):
    """Convierte un valor a unicode seguro para JSON en IronPython 2.7 y CPython 3."""
    if valor is None:
        return None
    # En CPython 3, str ya es unicode. En IronPython 2.7, str es bytes.
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


def _element_id_int(element_id):
    """Obtiene el entero de un ElementId de forma compatible con IronPython 2.7 y CPython."""
    if element_id is None:
        return None
    try:
        return element_id.Value
    except Exception:
        pass
    try:
        return element_id.IntegerValue
    except Exception:
        pass
    try:
        return int(element_id)
    except Exception:
        return None


def _sanitize_para_json(valor):
    """Convierte recursivamente todos los str (bytes en IronPython) a unicode
    para que json.dumps(ensure_ascii=True) no falle con UnicodeDecodeError."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return _to_unicode(valor)
    if isinstance(valor, dict):
        return { _sanitize_para_json(k): _sanitize_para_json(v) for k, v in valor.items() }
    if isinstance(valor, list):
        return [ _sanitize_para_json(v) for v in valor ]
    if isinstance(valor, tuple):
        return tuple(_sanitize_para_json(v) for v in valor)
    return valor


def _nombre_elemento_seguro(elemento):
    try:
        if BuiltInParameter is not None:
            p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
            if p is not None:
                v = p.AsString()
                if v:
                    return _to_unicode(v)
    except Exception:
        pass
    try:
        n = getattr(elemento, "Name", None)
        if n:
            return _to_unicode(n)
    except Exception:
        pass
    return None



def _nombre_categoria(inst):
    try:
        cat = inst.Category
        if cat is not None:
            return _to_unicode(cat.Name)
    except Exception:
        pass
    return None


def _es_face_based(inst):
    """Una instancia es face-based si su Location no es LocationPoint."""
    try:
        loc = getattr(inst, "Location", None)
        if loc is None:
            return True
        if LocationPoint is not None:
            return not isinstance(loc, LocationPoint)
        return getattr(loc, "Point", None) is None
    except Exception:
        return True


def _nivel_nombre(doc, nivel_id):
    if nivel_id is None:
        return None
    try:
        niv = doc.GetElement(nivel_id)
        if niv is not None:
            return _nombre_elemento_seguro(niv)
    except Exception:
        pass
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
    # Dentro de Revit/IronPython, __file__ apunta al script.
    # src/fase-6-revit/DIAGNOSTICAR_VISIBILIDAD_v01.py -> subir 3 niveles para T5-SantaMarta
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
        if os.path.exists(os.path.join(root, "CLAUDE.md")):
            return root
    except NameError:
        pass
    # Buscar CLAUDE.md hacia arriba desde cwd (marcador del proyecto)
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

    Si ruta_json ya es absoluta, se devuelve tal cual.
    """
    if not ruta_json:
        return ruta_json
    if os.path.isabs(ruta_json):
        return ruta_json
    root = _obtener_root_proyecto(root_proyecto)
    return os.path.join(root, ruta_json)


def diagnosticar_visibilidad(doc, json_out=None, solo_sin_nivel=False,
                             root_proyecto=None):
    """
    Lista FamilyInstance del documento para diagnosticar visibilidad.

    Parametros:
      doc: Documento de Revit activo.
      json_out: Ruta opcional para guardar JSON de resultado. Si es relativa,
                se resuelve contra la raiz del proyecto.
      solo_sin_nivel: Si True, solo lista instancias sin LevelId valido.
      root_proyecto: Ruta opcional a la raiz del proyecto para resolver
                     rutas relativas (default: REVITELECTRICO_ROOT o cwd).
    """
    if json_out:
        json_out = _resolver_ruta_relativa(json_out, root_proyecto)
    resultados = []
    niveles = {}

    # Indexar niveles por id para lookup rapido.
    # Nota: Level no pertenece a BuiltInCategory.OST_Levels, asi que se usa
    # OfClass(Level) directamente. Como fallback, probar con OST_Levels.
    # Estrategias adicionales si fallan las anteriores:
    #   - OfCategory(OST_Levels) sin WhereElementIsNotElementType
    #   - OfCategory(OST_Levels).WhereElementIsElementType()
    try:
        colector_niveles = FilteredElementCollector(doc).OfClass(Level)
        nivel_elementos = colector_niveles.ToElements()
        print("  DEBUG: OfClass(Level) retorno {} niveles".format(len(nivel_elementos)))
        if len(nivel_elementos) == 0 and BuiltInCategory is not None:
            # Fallback 1: buscar por categoria OST_Levels (no element type)
            colector_niveles = FilteredElementCollector(doc) \
                .OfCategory(BuiltInCategory.OST_Levels) \
                .WhereElementIsNotElementType()
            nivel_elementos = colector_niveles.ToElements()
            print("  DEBUG: OST_Levels WhereElementIsNotElementType retorno {} niveles".format(len(nivel_elementos)))
        if len(nivel_elementos) == 0 and BuiltInCategory is not None:
            # Fallback 2: buscar por categoria OST_Levels (element type)
            colector_niveles = FilteredElementCollector(doc) \
                .OfCategory(BuiltInCategory.OST_Levels) \
                .WhereElementIsElementType()
            nivel_elementos = colector_niveles.ToElements()
            print("  DEBUG: OST_Levels WhereElementIsElementType retorno {} niveles".format(len(nivel_elementos)))
        if len(nivel_elementos) == 0 and BuiltInCategory is not None:
            # Fallback 3: buscar por categoria OST_Levels sin filtro de tipo
            colector_niveles = FilteredElementCollector(doc) \
                .OfCategory(BuiltInCategory.OST_Levels)
            nivel_elementos = colector_niveles.ToElements()
            print("  DEBUG: OST_Levels sin filtro retorno {} niveles".format(len(nivel_elementos)))
        for niv in nivel_elementos:
            eid = _element_id_int(niv.Id)
            niveles[eid] = {
                "nombre": _nombre_elemento_seguro(niv) or "?",
                "elev_m": niv.Elevation / 3.28084,
            }
    except Exception as exc:
        print("  ERROR buscando niveles: {}".format(_to_unicode(str(exc))))

    total = 0
    sin_nivel = 0
    face_based = 0

    colector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for inst in colector.ToElements():
        total += 1
        try:
            loc = getattr(inst, "Location", None)
            punto = None
            if loc is not None:
                pt = getattr(loc, "Point", None)
                if pt is not None:
                    punto = {"X": pt.X, "Y": pt.Y, "Z": pt.Z}

            nivel_id = None
            try:
                lid = inst.LevelId
                if lid is not None:
                    eid = _element_id_int(lid)
                    if eid is not None and eid != -1:
                        nivel_id = eid
            except Exception:
                pass

            fb = _es_face_based(inst)
            if fb:
                face_based += 1

            tiene_nivel_valido = nivel_id is not None
            if solo_sin_nivel and tiene_nivel_valido and not fb:
                continue

            if not tiene_nivel_valido:
                sin_nivel += 1

            cat_nombre = _nombre_categoria(inst)
            fam_nombre = _nombre_elemento_seguro(inst)

            nivel_info = niveles.get(nivel_id) if nivel_id is not None else None

            resultados.append({
                "id": _element_id_int(inst.Id),
                "familia": _to_unicode(fam_nombre),
                "categoria": _to_unicode(cat_nombre),
                "posicion": punto,
                "nivel_id": nivel_id,
                "nivel_nombre": _to_unicode(nivel_info["nombre"]) if nivel_info else None,
                "nivel_elev_m": nivel_info["elev_m"] if nivel_info else None,
                "face_based": fb,
            })
        except Exception as exc:
            resultados.append({
                "id": _element_id_int(inst.Id),
                "error": _to_unicode(str(exc)),
            })

    # Resumen
    resumen = {
        "total_instancias": total,
        "sin_nivel_valido": sin_nivel,
        "face_based": face_based,
        "con_nivel": total - sin_nivel - face_based + (face_based and 0 or 0),
        "niveles_en_documento": len(niveles),
    }

    print("=" * 60)
    print("DIAGNOSTICO DE VISIBILIDAD — FamilyInstance en Revit")
    print("Documento: {}".format(_to_unicode(doc.Title)))
    print("Total FamilyInstance: {}".format(total))
    print("  - sin nivel valido: {}".format(sin_nivel))
    print("  - face-based (cara de techo/muro): {}".format(face_based))
    print("  - niveles en documento: {}".format(len(niveles)))
    print("=" * 60)

    # Listar niveles disponibles
    print("\nNiveles disponibles:")
    for nid, info in sorted(niveles.items(), key=lambda kv: kv[1]["elev_m"]):
        print("  id={} | '{}' | elev={:.4f} m".format(nid, info["nombre"], info["elev_m"]))

    # Mostrar instancias sin nivel o face-based primero
    print("\nInstancias sin nivel o face-based:")
    cont = 0
    for r in resultados:
        if not r.get("tiene_nivel_valido", True) or r.get("face_based"):
            cont += 1
            print("  id={} | {} | cat={} | pos={} | nivel={} | face_based={}".format(
                r.get("id"),
                r.get("familia"),
                r.get("categoria"),
                r.get("posicion"),
                r.get("nivel_nombre"),
                r.get("face_based")))
            if cont >= 20:
                print("  ... (mostrando primeras 20)")
                break

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        datos_json = _sanitize_para_json({
            "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": _to_unicode(doc.Title),
            "resumen": resumen,
            "niveles": niveles,
            "instancias": resultados,
        })
        with open(json_out, "w") as f:
            f.write(json.dumps(datos_json, indent=2, ensure_ascii=True))
        print("\nJSON guardado en: {}".format(json_out))

    return {
        "resumen": resumen,
        "niveles": niveles,
        "instancias": resultados,
    }

