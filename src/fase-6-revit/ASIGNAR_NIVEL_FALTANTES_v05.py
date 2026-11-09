# -*- coding: utf-8 -*-
"""
ASIGNAR_NIVEL_FALTANTES_v05.py — Asigna el nivel "Piso 5" a FamilyInstance
que se crearon sin nivel (host basado en techo/nivel, o instances sin LevelId).

Estrategia escalable (repetible para cualquier piso/bloque):
  1. Lee el JSON de reporte de modelado (tiene x_revit, y_revit, z_revit, anfitrion, nivel_revit).
  2. Filtra acciones con anfitrion == "ceiling" o "nivel" (creadas sin host de muro).
  3. Busca en Revit una FamilyInstance cuya Location.Point coincida (tolerancia 0.02 m).
  4. Si la instancia no tiene LevelId valido (o es distinto al nivel destino),
     le asigna el nivel "Piso 5" buscado dinamicamente por elevacion o nombre.
  5. No depende de ElementIds fijos del DXF.

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r".../src/fase-6-revit/ASIGNAR_NIVEL_FALTANTES_v05.py").read()))
  asignar_nivel_faltantes(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json",
                          json_out="data\\asignar_nivel_faltantes_v05_resultado.json",
                          nivel_destino="Piso 5")


Ultimos tres cambios
--------------------
1. 2026-11-08 v05: version vigente conservada tras la limpieza de duplicados;
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
    from System import Int64
except Exception:
    Int64 = None

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
    from Autodesk.Revit.DB import Transaction
except Exception:
    Transaction = None
try:
    from Autodesk.Revit.DB import XYZ
except Exception:
    XYZ = None
try:
    from Autodesk.Revit.DB import ElementId
except Exception:
    ElementId = None
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

TOLERANCIA_M = 0.02  # metros, tolerancia de coincidencia XYZ
NIVEL_DESTINO_DEFAULT = "Piso 5"
ELEVACION_DEFAULT_M = 13.22  # metros, elevacion aproximada de Piso 5


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
    # src/fase-6-revit/ASIGNAR_NIVEL_FALTANTES_v05.py -> subir 3 niveles para T5-SantaMarta
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


def _nombre_elemento_seguro(elemento):
    try:
        if BuiltInParameter is not None:
            p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
            if p is not None:
                valor = p.AsString()
                if valor:
                    return valor
    except Exception:
        pass
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    return None


def _buscar_param_comments(inst):
    """Devuelve el parametro Comments (COMENTARIOS) de la instancia."""
    try:
        return inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    except Exception:
        pass
    # Fallback: buscar por nombre entre los parametros de instancia
    for p in inst.Parameters:
        try:
            if p.Definition and p.Definition.Name.strip().lower() == "comments":
                return p
        except Exception:
            continue
    return None


def _cargar_reporte(ruta_json):
    """Carga el JSON de reporte de modelado y retorna la lista de acciones."""
    with open(ruta_json, "r") as f:
        datos = json.load(f)
    acciones = datos.get("acciones_modelar", [])
    if not acciones:
        # Soporte para el reporte _resultado.json (clave 'exitos')
        acciones = datos.get("exitos", [])
    return acciones


def _filtrar_sin_nivel(acciones, nivel_destino=NIVEL_DESTINO_DEFAULT):
    """Retorna acciones anfitrion ceiling/nivel (candidatas a nivel faltante)."""
    candidatos = []
    for accion in acciones:
        anfitrion = accion.get("anfitrion", "")
        nivel_revit = accion.get("nivel_revit", "")
        # anfitrion ceiling o nivel_revit vacio = sin host de muro asignado
        if anfitrion == "ceiling" or anfitrion == "nivel" or not nivel_revit:
            try:
                x = float(accion.get("x_revit", 0))
                y = float(accion.get("y_revit", 0))
                z = float(accion.get("z_revit", 0))
            except (TypeError, ValueError):
                continue
            candidatos.append({
                "nombre_bloque": _to_unicode(accion.get("nombre_bloque", "")),
                "orden": accion.get("orden", None),
                "capa": _to_unicode(accion.get("capa", "")),
                "anfitrion": _to_unicode(anfitrion),
                "nivel": _to_unicode(accion.get("nivel", nivel_destino)),
                "nivel_revit": _to_unicode(nivel_revit),
                "x": x,
                "y": y,
                "z": z,
            })
    return candidatos


def _buscar_nivel_por_nombre_o_elevacion(doc, nivel_destino=NIVEL_DESTINO_DEFAULT,
                                         elevacion_m=ELEVACION_DEFAULT_M):
    """Busca el nivel destino por nombre o elevacion (fallback)."""
    # Nota: Level no pertenece a BuiltInCategory.OST_Levels, asi que se usa
    # OfClass(Level) directamente. Como fallback, probar con OST_Levels.
    colector = FilteredElementCollector(doc).OfClass(Level)
    nivel_elementos = colector.ToElements()
    if len(nivel_elementos) == 0 and BuiltInCategory is not None:
        # Fallback: buscar por categoria OST_Levels
        colector = FilteredElementCollector(doc) \
            .OfCategory(BuiltInCategory.OST_Levels) \
            .WhereElementIsNotElementType()
        nivel_elementos = colector.ToElements()
    elev_pies = elevacion_m * 3.28084

    # Primero por nombre exacto
    for niv in nivel_elementos:
        try:
            nombre = _nombre_elemento_seguro(niv)
            if nombre and nivel_destino.lower() in nombre.lower():
                return niv
        except Exception:
            continue

    # Fallback por elevacion aproximada
    for niv in nivel_elementos:
        try:
            elev = niv.Elevation
            if abs(elev - elev_pies) < 0.05:
                return niv
        except Exception:
            continue

    return None


def _buscar_instancia_por_posicion(doc, x, y, z, tolerancia=TOLERANCIA_M):
    """Busca una FamilyInstance cuya Location.Point este cerca de (x,y,z)."""
    colector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for inst in colector.ToElements():
        try:
            loc = getattr(inst, "Location", None)
            if loc is None:
                continue
            punto = getattr(loc, "Point", None)
            if punto is None:
                continue
            ref = XYZ(x, y, z)
            d = punto.DistanceTo(ref)
            if d <= tolerancia:
                return inst
        except Exception:
            continue
    return None


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


def _es_face_based(inst):
    """Una instancia es face-based si su Location no es LocationPoint."""
    try:
        loc = getattr(inst, "Location", None)
        if loc is None:
            return True
        if LocationPoint is not None:
            return not isinstance(loc, LocationPoint)
        # Fallback sin LocationPoint: considerar face-based si no tiene atributo Point
        return getattr(loc, "Point", None) is None
    except Exception:
        return True


def _nivel_actual_de_instancia(inst):
    """Retorna el LevelId actual de la instancia o None."""
    try:
        lid = inst.LevelId
        if lid is not None:
            eid = _element_id_int(lid)
            if eid is not None and eid != -1:
                return lid
    except Exception:
        pass
    return None


def _buscar_instancia_por_elemento_id(doc, elemento_id):
    """Busca una FamilyInstance por su ElementId entero (desde reporte de modelado)."""
    try:
        eid = ElementId(Int64(int(elemento_id)))
    except Exception:
        return None
    inst = doc.GetElement(eid)
    if inst is not None and isinstance(inst, FamilyInstance):
        return inst
    return None


def asignar_nivel_faltantes(doc, reporte_json=None, json_out=None,
                            nivel_destino=NIVEL_DESTINO_DEFAULT,
                            elevacion_m=ELEVACION_DEFAULT_M,
                            root_proyecto=None):
    """
    Asigna el nivel destino a FamilyInstance sin nivel (host techo/nivel).

    Parametros:
      doc: Documento de Revit activo.
      reporte_json: Ruta al JSON de reporte de modelado (acciones_modelar).
                    Si es relativa, se resuelve contra la raiz del proyecto.
      json_out: Ruta opcional para guardar el JSON de resultado.
                Si es relativa, se resuelve contra la raiz del proyecto.
      nivel_destino: Nombre del nivel a asignar (default "Piso 5").
      elevacion_m: Elevacion aproximada en metros para buscar el nivel (fallback).
      root_proyecto: Ruta opcional a la raiz del proyecto para resolver
                     rutas relativas (default: REVITELECTRICO_ROOT o cwd).
    """
    if reporte_json is None:
        raise ValueError("se requiere reporte_json (ruta al JSON de reporte de modelado)")

    reporte_json = _resolver_ruta_relativa(reporte_json, root_proyecto)
    if json_out:
        json_out = _resolver_ruta_relativa(json_out, root_proyecto)

    acciones = _cargar_reporte(reporte_json)
    candidatos = _filtrar_sin_nivel(acciones, nivel_destino)

    nivel_piso5 = _buscar_nivel_por_nombre_o_elevacion(doc, nivel_destino, elevacion_m)

    if nivel_piso5 is None:
        print("ERROR: No se encontro el nivel '{}' (elev~{} m).".format(
            nivel_destino, elevacion_m))
        print("Niveles disponibles:")
        try:
            colector = FilteredElementCollector(doc).OfClass(Level)
            nivel_elementos = colector.ToElements()
            if len(nivel_elementos) == 0 and BuiltInCategory is not None:
                colector = FilteredElementCollector(doc) \
                    .OfCategory(BuiltInCategory.OST_Levels) \
                    .WhereElementIsNotElementType()
                nivel_elementos = colector.ToElements()
            for niv in nivel_elementos:
                try:
                    elev_m = niv.Elevation / 3.28084
                    nombre = _nombre_elemento_seguro(niv) or "?"
                    print("  - '{}' | elev={:.4f} m | id={}".format(
                        nombre, elev_m, niv.Id.ToString()))
                except Exception:
                    pass
        except Exception:
            pass
        return {"exitos": 0, "fallos": len(candidatos),
                "detalle": [{"nombre_bloque": c["nombre_bloque"],
                             "motivo": "Nivel {} no encontrado".format(nivel_destino)}
                            for c in candidatos]}

    print("Nivel encontrado: '{}' | elev={:.4f} m | id={}".format(
        _nombre_elemento_seguro(nivel_piso5),
        nivel_piso5.Elevation / 3.28084,
        nivel_piso5.Id.ToString()))

    trans = Transaction(doc, "ASIGNAR_NIVEL_FALTANTES — {}".format(nivel_destino))
    trans.Start()

    exitos = 0
    fallos = 0
    ya_tenia_nivel = 0
    no_encontrados = 0
    face_based_skip = 0
    detalle = []

    for cand in candidatos:
        try:
            # Dispositivos de techo (anfitrion == "ceiling") son face-based:
            # su host es la cara de un techo, LevelId es read-only y no se les
            # asigna nivel. No se pueden buscar por Location.Point porque no
            # tienen punto de ubicacion en el modelo (están anclados a una cara).
            # Se marcan directamente como face_based_skip.
            if cand.get("anfitrion") == "ceiling":
                face_based_skip += 1
                fallos += 1
                detalle.append({
                    "nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                    "orden": cand["orden"],
                    "x": cand["x"],
                    "y": cand["y"],
                    "z": cand["z"],
                    "anfitrion": _to_unicode(cand["anfitrion"]),
                    "motivo": _to_unicode("Face-based (host = cara de techo): LevelId no aplica"),
                    "nivel_anterior": None,
                    "nivel_nuevo": nivel_piso5.Id.ToString() if nivel_piso5 else None,
                })
                print("  FACE-BASED (techo) {} (z={} m): LevelId no aplica".format(
                    cand["nombre_bloque"], cand["z"]))
                continue

            # Estrategia 1: buscar por ElementId si el reporte lo tiene (mas directo)
            inst = None
            elemento_id = cand.get("elemento_id")
            if elemento_id is not None:
                inst = _buscar_instancia_por_elemento_id(doc, elemento_id)
                motivo_busqueda = "por ElementId {}".format(elemento_id)
            else:
                motivo_busqueda = "por posicion ({},{},{})".format(cand["x"], cand["y"], cand["z"])

            # Estrategia 2: buscar por posicion si no hay elemento_id o no se encontro
            if inst is None:
                inst = _buscar_instancia_por_posicion(doc, cand["x"], cand["y"], cand["z"])

            if inst is None:
                no_encontrados += 1
                fallos += 1
                detalle.append({
                    "nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                    "orden": cand["orden"],
                    "x": cand["x"],
                    "y": cand["y"],
                    "z": cand["z"],
                    "motivo": _to_unicode("Instancia no encontrada en Revit ({})".format(motivo_busqueda)),
                })
                print("  NO ENCONTRADO {} {}".format(cand["nombre_bloque"], motivo_busqueda))
                continue

            # Si es face-based (host = cara de techo/muro), LevelId es read-only: no asignar
            if _es_face_based(inst):
                face_based_skip += 1
                fallos += 1
                detalle.append({
                    "nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                    "orden": cand["orden"],
                    "id": inst.Id.ToString(),
                    "anfitrion": _to_unicode(cand["anfitrion"]),
                    "motivo": _to_unicode("Face-based (host = cara de techo/muro): LevelId no aplica"),
                    "nivel_anterior": None,
                    "nivel_nuevo": nivel_piso5.Id.ToString(),
                })
                print("  FACE-BASED id={} {} (LevelId no aplica)".format(
                    inst.Id.ToString(), cand["nombre_bloque"]))
                continue

            nivel_actual = _nivel_actual_de_instancia(inst)
            if nivel_actual is not None:
                try:
                    eid_actual = _element_id_int(nivel_actual)
                    eid_destino = _element_id_int(nivel_piso5.Id)
                    if eid_actual is not None and eid_destino is not None and eid_actual == eid_destino:
                        ya_tenia_nivel += 1
                        detalle.append({
                            "nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                            "orden": cand["orden"],
                            "id": inst.Id.ToString(),
                            "motivo": _to_unicode("Ya tiene el nivel asignado (Piso 5)"),
                            "nivel_anterior": nivel_actual.ToString(),
                            "nivel_nuevo": nivel_piso5.Id.ToString(),
                        })
                        print("  YA TIENE NIVEL id={} {}".format(inst.Id.ToString(), cand["nombre_bloque"]))
                        continue
                except Exception:
                    pass

            try:
                inst.LevelId = nivel_piso5.Id
                exitos += 1
                detalle.append({
                    "id": inst.Id.ToString(),
                    "nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                    "orden": cand["orden"],
                    "anfitrion": _to_unicode(cand["anfitrion"]),
                    "motivo": _to_unicode("OK"),
                    "nivel_anterior": nivel_actual.ToString() if nivel_actual is not None else None,
                    "nivel_nuevo": nivel_piso5.Id.ToString(),
                })
                print("  OK id={} {} nivel={}".format(
                    inst.Id.ToString(), cand["nombre_bloque"], nivel_destino))
            except Exception as exc:
                fallos += 1
                detalle.append({"nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                                "orden": cand["orden"],
                                "motivo": _to_unicode("Error asignando nivel: {}".format(exc))})
                print("  FALLO {}: {}".format(cand["nombre_bloque"], exc))

        except Exception as exc:
            fallos += 1
            detalle.append({"nombre_bloque": _to_unicode(cand["nombre_bloque"]),
                            "orden": cand["orden"],
                            "motivo": _to_unicode("Error: {}".format(exc))})
            print("  FALLO {}: {}".format(cand["nombre_bloque"], exc))

    trans.Commit()

    print("\n" + "=" * 60)
    print("ASIGNACIÓN DE NIVEL COMPLETADA (v05 — por posicion XY)")
    print("Documento: {}".format(doc.Title))
    print("Reporte: {}".format(reporte_json))
    print("Nivel destino: {}".format(nivel_destino))
    print("Candidatos en reporte: {}".format(len(candidatos)))
    print("Exitos: {}".format(exitos))
    print("  - ya tenian nivel: {}".format(ya_tenia_nivel))
    print("Fallos: {}".format(fallos))
    print("  - no encontrados en Revit: {}".format(no_encontrados))
    print("  - face-based (LevelId no aplica): {}".format(face_based_skip))
    print("=" * 60)

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "reporte_origen": reporte_json,
                "nivel_destino": nivel_destino,
                "nivel_id": nivel_piso5.Id.ToString(),
                "elevacion_m": nivel_piso5.Elevation / 3.28084,
                "estrategia": "posicion_XY_tolerancia_{}m".format(TOLERANCIA_M),
                "candidatos_reporte": len(candidatos),
                "exitos": exitos,
                "fallos": fallos,
                "ya_tenia_nivel": ya_tenia_nivel,
                "no_encontrados": no_encontrados,
                "face_based_skip": face_based_skip,
                "detalle": detalle,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return {
        "exitos": exitos,
        "fallos": fallos,
        "ya_tenia_nivel": ya_tenia_nivel,
        "no_encontrados": no_encontrados,
        "face_based_skip": face_based_skip,
        "total_candidatos": len(candidatos),
        "detalle": detalle,
    }

