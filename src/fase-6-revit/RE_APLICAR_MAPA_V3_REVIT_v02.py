# -*- coding: utf-8 -*-
"""
RE_APLICAR_MAPA_V3_REVIT_v02.py — Crea FamilyInstance reales en Revit 2026
consumiendo el reporte de RE_APLICAR_MAPA_V3_v01.py.
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
IronPython 2.7 (Dentro de Revit / pyRevit) — SIN type hints, SIN requests/bs4.

OBJETIVO:
  Leer el JSON de reporte generado por RE_APLICAR_MAPA_V3_v01.py y crear
  las FamilyInstance en Revit 2026 usando:
    - NewFamilyInstance(face, location, symbol) para anfitrion == "ceiling"
      (cara inferior del cieloraso, Z ≈ 15.82 m).
    - NewFamilyInstance(level, location, symbol, estructural) para anfitrion == "muro".
  Saltar marcadores de conductores (mapear: false) y dispositivos sin mapeo.
  Registrar resultados en un JSON de salida (éxitos / fallos).

Tarea C — Host fallback techo → muro:
  - _buscar_cara_techo(doc, punto, altura_cieloraso_m, ...) busca cara horizontal
    que contenga el punto XY del dispositivo.
  - _buscar_cara_muro(doc, punto, radio_busqueda_m, ...) busca caras verticales de
    muros (OST_Walls) dentro de un radio y retorna la mas cercana.
  - _instanciar_con_host(doc, simbolo, punto, host_cara, nivel, rotacion, ...)
    intenta NewFamilyInstance(face, ...) con la cara; si no hay cara o falla,
    usa NewFamilyInstance(level, ...) sobre el nivel "Piso 5".
  - aplicar_mapa_con_host_fallback(doc, acciones, json_out, ...) recorre las
    acciones; para anfitrion == "ceiling" sin cara de cieloraso usa fallback a
    muro y registra metodo_ajustado: "ceiling->muro_fallback".

USO (desde dentro de Revit con pyRevit):
  pyrevit run RE_APLICAR_MAPA_V3_REVIT_v02.py --json-in <reporte.json> --json-out <resultado.json>

O desde RevitPythonShell dentro de Revit.

NOTAS:
  - pyRevit provee __revit__ como UIApplication.
  - Usar .format() y concatenación de strings (no f-strings).
  - No usar type hints ni requests/bs4.
  - Los imports de Revit API se hacen dentro de las funciones para poder
    probar la lógica en CPython 3.12 sin Revit instalado.


Ultimos tres cambios
--------------------
1. 2026-11-08 v02: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import json
import os
from datetime import datetime


def _ascii_safe(valor):
    """
    Convierte un valor a string seguro para ASCII (IronPython 2.7).
    Reemplaza caracteres no-ASCII por '?' para evitar UnicodeDecodeError
    en json.dumps. Devuelve el valor original si no es string.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    # unicode o str en IronPython 2.7
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
        # Sanitizamos todos los strings a ASCII antes de serializar.
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

    En pruebas (CPython 3.12) se lee el módulo ya inyectado en
    sys.modules["Autodesk.Revit.DB"] por el harness de tests (mocks), usando
    getattr para no fallar si el mock carece de algún atributo. No se sobreescribe
    sys.modules para no contaminar a otros módulos de Revit cargados en la misma
    sesión de pytest.

    En Revit / IronPython real se importa la API verdadera mediante clr.
    """
    import sys

    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": getattr(mock_db, "FilteredElementCollector", None),
            "BuiltInCategory": getattr(mock_db, "BuiltInCategory", None),
            "XYZ": getattr(mock_db, "XYZ", None),
            "FamilyInstance": getattr(mock_db, "FamilyInstance", None),
            "FamilySymbol": getattr(mock_db, "FamilySymbol", None),
            "Family": getattr(mock_db, "Family", None),
            "Level": getattr(mock_db, "Level", None),
            "Structure": getattr(mock_db, "Structure", None),
            "Transaction": getattr(mock_db, "Transaction", None),
            "Options": getattr(mock_db, "Options", None),
        }

    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        BuiltInCategory,
        XYZ,
        FamilyInstance,
        FamilySymbol,
        Family,
        Level,
        Structure,
        Transaction,
        Options,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "XYZ": XYZ,
        "FamilyInstance": FamilyInstance,
        "FamilySymbol": FamilySymbol,
        "Family": Family,
        "Level": Level,
        "Structure": Structure,
        "Transaction": Transaction,
        "Options": Options,
    }


def _obtener_nombre_elemento(elemento, revit_db):
    """
    Obtiene el nombre legible de un elemento de Revit (Family, Level,
    FamilySymbol, etc.). En IronPython real, elemento.Name lanza
    AttributeError ("Name").

    Probamos en orden:
      1. getattr(elemento, "Name", None)
      2. Parametro BuiltInParameter.ALL_MODEL_TYPE_NAME
    """
    # Intento 1: propiedad Name directa
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass

    # Intento 2: parametro ALL_MODEL_TYPE_NAME
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


def _obtener_nombre_simbolo(simbolo, revit_db):
    """
    Obtiene el nombre legible de un FamilySymbol.

    En IronPython real, simbolo.Name lanza AttributeError ("Name").
    Probamos en orden:
      1. simbolo.Name (getattr directo).
      2. Parametro BuiltInParameter.ALL_MODEL_TYPE_NAME.
      3. Cualquier parametro de tipo string cuyo valor coincida con el nombre
         de la familia o del tipo.
    Devuelve el string del nombre o None.
    """
    # Intento 1: propiedad Name directa
    try:
        nombre = getattr(simbolo, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass

    # Intento 2: parametro ALL_MODEL_TYPE_NAME
    try:
        BuiltInParameter = revit_db.get("BuiltInParameter")
        if BuiltInParameter is None:
            import Autodesk.Revit.DB as _db
            BuiltInParameter = _db.BuiltInParameter
        p = simbolo.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass

    # Intento 3: recorrer todos los parametros buscando un string con el nombre
    try:
        for parametro in simbolo.Parameters:
            try:
                valor = parametro.AsString()
                if valor and valor.strip():
                    return valor
            except Exception:
                continue
    except Exception:
        pass

    return None


def _nombre_coincide(nombre_obtenido, nombre_esperado):
    """Compara dos nombres de forma case-insensitive y tolerante a espacios."""
    if not nombre_obtenido or not nombre_esperado:
        return False
    return nombre_obtenido.strip().lower() == nombre_esperado.strip().lower()


def _buscar_familia_por_nombre(doc, nombre_familia, revit_db):
    """Busca una familia cargada en el documento por su nombre."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Family = revit_db.get("Family")
    if Family is None:
        # En CPython de prueba con mocks, Family ya viene en el diccionario.
        # En IronPython real no se puede importar Autodesk.Revit.DB dentro
        # de la funcion si clr no esta cargado; confiamos en revit_db.
        return None
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            nombre_fam = _obtener_nombre_elemento(fam, revit_db)
            if _nombre_coincide(nombre_fam, nombre_familia):
                return fam
        except Exception:
            continue
    return None


def _buscar_symbol_por_nombre(doc, nombre_familia, nombre_simbolo, revit_db):
    """
    Busca un FamilySymbol dentro de una familia por nombre de familia y
    nombre de simbolo (tipo). Devuelve el FamilySymbol o None.

    Usa _obtener_nombre_simbolo para resolver el nombre real del simbolo
    en IronPython, donde simbolo.Name no es fiable.

    Estrategia de matching:
      1. Match exacto: nombre de familia + nombre de simbolo.
      2. Match por simbolo llamado "Estandar" (tipico en familias electricas de Revit).
      3. Primer simbolo disponible de la familia (fallback de ultimo recurso).

    Devuelve una tupla (simbolo, simbolo_usado) donde simbolo_usado es el
    nombre real del simbolo seleccionado (para reportar advertencias si no
    coincide con el solicitado).
    """
    familia = _buscar_familia_por_nombre(doc, nombre_familia, revit_db)
    if familia is None:
        return None, None

    simbolos = []
    for id_elem in familia.GetFamilySymbolIds():
        simbolo = doc.GetElement(id_elem)
        if simbolo is None:
            continue
        nombre_sim = _obtener_nombre_simbolo(simbolo, revit_db)
        simbolos.append((simbolo, nombre_sim))

    # 1. Match exacto de simbolo
    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, nombre_simbolo):
            if not simbolo.IsActive:
                try:
                    simbolo.Activate()
                    doc.Regenerate()
                except Exception:
                    pass
            return simbolo, nombre_sim

    # 2. Match por simbolo llamado "Estandar" (tipico en familias electricas de Revit)
    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, "Estandar"):
            if not simbolo.IsActive:
                try:
                    simbolo.Activate()
                    doc.Regenerate()
                except Exception:
                    pass
            return simbolo, nombre_sim

    # 3. Fallback: primer simbolo disponible de la familia
    if simbolos:
        simbolo, nombre_sim = simbolos[0]
        if not simbolo.IsActive:
            try:
                simbolo.Activate()
                doc.Regenerate()
            except Exception:
                pass
        return simbolo, nombre_sim

    return None, None


def _buscar_nivel_por_nombre(doc, nombre_nivel, revit_db):
    """Busca un Level por nombre."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    colector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Levels
    )
    for nivel in colector.ToElements():
        try:
            nombre_niv = _obtener_nombre_elemento(nivel, revit_db)
            if _nombre_coincide(nombre_niv, nombre_nivel):
                return nivel
        except Exception:
            continue
    return None


def _diagnosticar_techos(doc, revit_db):
    """Imprime cuántos elementos de categoría techo/cieloraso hay en el documento."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    conteo = {}
    for cat_name, cat_id in [
        ("OST_Ceilings", BuiltInCategory.OST_Ceilings),
        ("OST_Roofs", BuiltInCategory.OST_Roofs),
        ("OST_Floors", BuiltInCategory.OST_Floors),
    ]:
        try:
            colector = FilteredElementCollector(doc).OfCategory(cat_id)
            elementos = [
                e for e in colector.ToElements() if not getattr(e, "IsElementType", False)
            ]
            conteo[cat_name] = len(elementos)
            for e in elementos[:3]:
                try:
                    nombre = _obtener_nombre_elemento(e, revit_db) or "?"
                    print("  {} | nombre={} | id={}".format(cat_name, nombre, e.Id.ToString()))
                except Exception:
                    pass
        except Exception:
            conteo[cat_name] = "error"
    print("Diagnostico de techos/cielorasos:")
    for cat_name, cantidad in conteo.items():
        print("  {}: {} elementos".format(cat_name, cantidad))
    return conteo


def _punto_dentro_poligono_xy(px, py, vertices):
    """
    Test de punto dentro de polígono (ray casting) en el plano XY.
    vertices: lista de tuplas (x, y). Devuelve True si (px, py) está dentro.
    """
    dentro = False
    n = len(vertices)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)):
            cruz = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < cruz:
                dentro = not dentro
        j = i
    return dentro


def _vertices_cara_xy(face):
    """
    Obtiene los vértices XY de una cara de Revit para el test de
    punto-dentro-polígono.

    En Revit real usa face.EdgeLoops y edge.AsCurve().Tessellate().
    En el mock de pruebas, face puede exponer obtener_vertices_xy().
    Devuelve lista de (x, y) o None si no se pueden obtener.
    """
    # Mock: cara que expone sus vertices directamente
    try:
        verts = face.obtener_vertices_xy()
        if verts is not None:
            return [(float(v[0]), float(v[1])) for v in verts]
    except Exception:
        pass

    # Revit real: recorrer EdgeLoops y tessellar curvas
    try:
        loops = face.EdgeLoops
        for loop in loops:
            pts = []
            for edge in loop:
                curva = edge.AsCurve()
                if curva is None:
                    continue
                for p in curva.Tessellate():
                    pts.append((float(p.X), float(p.Y)))
            if len(pts) >= 3:
                return pts
    except Exception:
        pass

    return None


def _buscar_cara_techo(doc, punto, altura_cieloraso_m, revit_db, umbral_z=0.10, umbral_xy_cerca=2.0):
    """
    Tarea C: busca la cara inferior de un cieloraso/techo cuya geometría
    en el plano XY contenga el punto (x, y) del dispositivo, y cuya altura
    Z esté cercana a altura_cieloraso_m.

    Si ninguna cara contiene exactamente el punto, se elige la cara más
    cercana en XY (dentro de umbral_xy_cerca) a esa Z.

    Busca en categorías OST_Ceilings, OST_Roofs y OST_Floors.

    punto: tupla (x, y, z) del dispositivo.
    altura_cieloraso_m: altura esperada del cieloraso en metros.

    Devuelve (reference_face, techo_elemento) o (None, None) si no se encuentra
    ninguna cara cercana.
    """
    punto_x, punto_y, punto_z = punto[0], punto[1], punto[2]

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    Options = revit_db.get("Options")
    if Options is None:
        try:
            import Autodesk.Revit.DB as _db
            Options = _db.Options
        except Exception:
            Options = None

    mejor_cara = None
    mejor_techo = None
    mejor_dist_xy = float("inf")

    categorias = [
        BuiltInCategory.OST_Ceilings,
        BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Floors,
    ]
    for cat in categorias:
        colector = FilteredElementCollector(doc).OfCategory(cat)
        for techo in colector.ToElements():
            try:
                if techo.IsElementType:
                    continue
            except Exception:
                continue
            geo_opt = techo.get_Geometry(Options() if Options is not None else None)
            if geo_opt is None:
                continue
            for obj in geo_opt:
                try:
                    faces = obj.Faces
                except Exception:
                    continue
                for face in faces:
                    try:
                        origen = face.Origin
                    except Exception:
                        continue
                    if abs(origen.Z - punto_z) >= umbral_z:
                        continue
                    vertices = _vertices_cara_xy(face)
                    if vertices is None:
                        continue
                    if _punto_dentro_poligono_xy(punto_x, punto_y, vertices):
                        # Interseccion exacta: es la mejor candidata posible.
                        return face, techo
                    # Candidato por proximidad XY (umbral 2.0 m por defecto)
                    cx = sum(v[0] for v in vertices) / len(vertices)
                    cy = sum(v[1] for v in vertices) / len(vertices)
                    dist_xy = ((cx - punto_x) ** 2 + (cy - punto_y) ** 2) ** 0.5
                    if dist_xy <= umbral_xy_cerca and dist_xy < mejor_dist_xy:
                        mejor_dist_xy = dist_xy
                        mejor_cara = face
                        mejor_techo = techo
    if mejor_cara is not None:
        return mejor_cara, mejor_techo
    return None, None


def _buscar_cara_muro(doc, punto, radio_busqueda_m=1.5, revit_db=None):
    """
    Tarea C: busca caras verticales de muros (OST_Walls) dentro de un radio
    alrededor del punto (x, y) del dispositivo, y retorna la cara mas cercana.

    Se considera una cara "vertical" si su normal tiene componente Z menor a
    un umbral (es decir, la cara es mayormente vertical).

    Devuelve (reference_face, muro_elemento, distancia_m) o (None, None, None)
    si no se encuentra ninguna cara de muro dentro del radio.
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    punto_x, punto_y, punto_z = punto[0], punto[1], punto[2]

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    Options = revit_db.get("Options")
    if Options is None:
        try:
            import Autodesk.Revit.DB as _db
            Options = _db.Options
        except Exception:
            Options = None

    mejor_cara = None
    mejor_muro = None
    mejor_dist = float("inf")

    colector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls)
    for muro in colector.ToElements():
        try:
            if getattr(muro, "IsElementType", False):
                continue
        except Exception:
            continue
        geo_opt = muro.get_Geometry(Options() if Options is not None else None)
        if geo_opt is None:
            continue
        for obj in geo_opt:
            try:
                faces = obj.Faces
            except Exception:
                continue
            for face in faces:
                try:
                    origen = face.Origin
                    normal = face.FaceNormal
                except Exception:
                    continue
                # Solo caras verticales: componente Z de la normal pequeña
                try:
                    comp_z = abs(normal.Z)
                except Exception:
                    comp_z = 0.0
                if comp_z > 0.3:
                    # Cara no es suficientemente vertical (es horizontal o inclinada)
                    continue
                # Distancia del punto al origen de la cara (proyección XY)
                dist_xy = ((origen.X - punto_x) ** 2 + (origen.Y - punto_y) ** 2) ** 0.5
                if dist_xy <= radio_busqueda_m and dist_xy < mejor_dist:
                    mejor_dist = dist_xy
                    mejor_cara = face
                    mejor_muro = muro
    if mejor_cara is not None:
        return mejor_cara, mejor_muro, mejor_dist
    return None, None, None


def _instanciar_con_host(doc, simbolo, punto, host_cara, nivel, rotacion_grados, revit_db):
    """
    Tarea C: crea una FamilyInstance intentando usar una cara de host primero,
    y si no hay cara o falla, usa un nivel como host.

    Orden de preferencia:
      1. Si host_cara no es None: NewFamilyInstance(face, location, symbol)
      2. Si hay nivel: NewFamilyInstance(level, location, symbol, estructural)

    Retorna (instancia, metodo_usado) donde metodo_usado es "cara" o "nivel".
    """
    XYZ = revit_db["XYZ"]
    location = XYZ(punto[0], punto[1], punto[2])

    # Intento 1: cara de host (techo o muro)
    if host_cara is not None:
        try:
            inst = doc.Create.NewFamilyInstance(host_cara, location, simbolo)
            return inst, "cara"
        except Exception:
            pass

    # Intento 2: fallback a nivel (Piso 5 o el nivel dado)
    if nivel is not None:
        Structure = revit_db["Structure"]
        try:
            inst = doc.Create.NewFamilyInstance(
                location, simbolo, nivel, Structure.StructuralType.NonStructural
            )
            return inst, "nivel"
        except Exception:
            pass

    return None, None


def _aplicar_rotacion(inst, rotacion_grados, revit_db):
    """Intenta aplicar rotación sobre el eje Z si el parámetro lo permite.

    Nunca lanza: si algo falla, devuelve False y la instancia ya está creada.
    """
    if rotacion_grados == 0:
        return True
    try:
        BuiltInParameter = revit_db.get("BuiltInParameter")
        if BuiltInParameter is None:
            import Autodesk.Revit.DB as _db
            BuiltInParameter = _db.BuiltInParameter
        param = inst.get_Parameter(BuiltInParameter.ROTATION)
        if param is not None and not param.IsReadOnly:
            import math
            rad = rotacion_grados * 3.141592653589793 / 180.0
            param.Set(rad)
            return True
    except Exception:
        pass
    return False


def _crear_instancia_techo(doc, simbolo, punto, cara_techo, rotacion_grados, revit_db):
    """
    Crea FamilyInstance sobre una cara de techo usando
    NewFamilyInstance(face, location, symbol).
    """
    XYZ = revit_db["XYZ"]
    location = XYZ(punto[0], punto[1], punto[2])
    inst = doc.Create.NewFamilyInstance(cara_techo, location, simbolo)
    return inst


def _crear_instancia_muro(doc, simbolo, punto, nivel, rotacion_grados, revit_db):
    """
    Crea FamilyInstance sobre un nivel usando
    NewFamilyInstance(level, location, symbol, estructural).
    """
    XYZ = revit_db["XYZ"]
    Structure = revit_db["Structure"]
    location = XYZ(punto[0], punto[1], punto[2])
    inst = doc.Create.NewFamilyInstance(
        location, simbolo, nivel, Structure.StructuralType.NonStructural
    )
    return inst


def _get_revit_db():
    """Obtiene el diccionario de la API de Revit, importando si es necesario."""
    return _import_revit_db()


def _nombres_accion(accion):
    """Resuelve los nombres de familia y simbolo de una accion.

    Si el JSON de entrada ya fue enriquecido por RE_MAPEAR_FAMILIAS_RVT_v01.py,
    usa familia_real / simbolo_real (los nombres REALES del RVT). Si no,
    cae a familia / simbolo (los nombres originales del DXF/mapa).
    """
    familia_nombre = accion.get("familia_real") or accion.get("familia")
    simbolo_nombre = accion.get("simbolo_real") or accion.get("simbolo")
    return familia_nombre, simbolo_nombre


def aplicar_mapa_revit(doc, json_in, json_out, revit_db=None, acciones=None):
    """
    Lee el reporte de RE_APLICAR_MAPA_V3_v01.py y crea las FamilyInstance
    en Revit. Devuelve el diccionario de resultado (también escrito en disco).

    Parametros:
      doc: Documento de Revit activo.
      json_in: Ruta al JSON de reporte de RE_APLICAR_MAPA_V3_v01.py.
      json_out: Ruta del JSON de resultado de salida.
      revit_db: Diccionario con clases de la API de Revit (para pruebas).
                Si es None, se importa Revit API (solo IronPython).
      acciones: Lista opcional de acciones a procesar (sobrescribe json_in).
                Se usa para consumir el JSON enriquecido de
                RE_MAPEAR_FAMILIAS_RVT_v01.py (acciones_enriquecidas).
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    if acciones is None:
        reporte = _cargar_json(json_in)
        acciones_modelar = reporte.get("acciones_modelar", [])
        acciones_saltar = reporte.get("acciones_saltar", [])
        acciones_sin_mapeo = reporte.get("acciones_sin_mapeo", [])
    else:
        reporte = {}
        acciones_modelar = acciones
        acciones_saltar = []
        acciones_sin_mapeo = []

    _diagnosticar_techos(doc, revit_db)

    exitos = []
    fallos = []
    saltados = []
    sin_mapeo = []

    Transaction = revit_db["Transaction"]

    trans = Transaction(doc, "RE_APLICAR_MAPA_V3 — Crear FamilyInstance")
    trans.Start()

    try:
        total_acciones = len(acciones_modelar)
        print("Procesando {} acciones de modelado...".format(total_acciones))
        for indice, accion in enumerate(acciones_modelar, start=1):
            nombre = accion.get("nombre_bloque", "")
            familia_nombre, simbolo_nombre = _nombres_accion(accion)
            anfitrion = accion.get("anfitrion")
            x = accion.get("x_revit")
            y = accion.get("y_revit")
            z = accion.get("z_revit")
            rot = accion.get("rotacion", 0)
            nivel_nombre = accion.get("nivel_revit")

            print("  [{}/{}] {} (anfitrion={}, familia={})".format(
                indice, total_acciones, nombre, anfitrion, familia_nombre))

            try:
                simbolo, simbolo_usado = _buscar_symbol_por_nombre(
                    doc, familia_nombre, simbolo_nombre, revit_db
                )
                if simbolo is None:
                    print("    FALLO: familia o simbolo no encontrado: {} / {}".format(
                        familia_nombre, simbolo_nombre))
                    fallos.append({
                        "orden": accion.get("orden"),
                        "nombre_bloque": nombre,
                        "capa": accion.get("capa"),
                        "motivo": "Familia o simbolo no encontrado: {} / {}".format(
                            familia_nombre, simbolo_nombre
                        ),
                        "accion": accion,
                    })
                    continue

                advertencia_simbolo = None
                if simbolo_usado and simbolo_usado.lower() != simbolo_nombre.lower():
                    advertencia_simbolo = "Simbolo solicitado '{}', se uso '{}'".format(
                        simbolo_nombre, simbolo_usado
                    )

                punto = [x, y, z]

                if anfitrion == "ceiling":
                    print("    Buscando cara de cieloraso para z={}, x={}, y={}".format(z, x, y))
                    altura_z = z
                    punto = [x, y, z]
                    cara_techo, techo_elem = _buscar_cara_techo(
                        doc, punto, altura_z, revit_db
                    )
                    if cara_techo is None:
                        # FALLBACK: no hay cara de cieloraso usable en este punto.
                        # Se crea instancia sobre el nivel "Piso 5" a la altura
                        # de colocacion del dispositivo (z), para que el aparato
                        # quede modelado en posicion aunque no haya cara de cielo
                        # que contenga exactamente su punto (x, y).
                        print("    AVISO: sin cara de cieloraso; usando nivel 'Piso 5' como fallback para {}".format(nombre))
                        nivel = _buscar_nivel_por_nombre(doc, "Piso 5", revit_db)
                        if nivel is None:
                            print("    FALLO: nivel 'Piso 5' no encontrado para fallback de techo")
                            fallos.append({
                                "orden": accion.get("orden"),
                                "nombre_bloque": nombre,
                                "capa": accion.get("capa"),
                                "motivo": "No se encontro cara de cieloraso ni nivel 'Piso 5' para fallback de techo",
                                "accion": accion,
                            })
                            continue
                        inst = _crear_instancia_muro(
                            doc, simbolo, punto, nivel, rot, revit_db
                        )
                    else:
                        print("    Cara de cieloraso encontrada en techo id={}".format(
                            getattr(techo_elem, "Id", None).ToString() if techo_elem is not None and getattr(techo_elem, "Id", None) is not None else "?"))
                        inst = _crear_instancia_techo(
                            doc, simbolo, punto, cara_techo, rot, revit_db
                        )
                elif anfitrion == "muro":
                    nivel = (
                        _buscar_nivel_por_nombre(doc, nivel_nombre, revit_db)
                        if nivel_nombre
                        else None
                    )
                    if nivel is None:
                        print("    FALLO: nivel no encontrado: {}".format(nivel_nombre))
                        fallos.append({
                            "orden": accion.get("orden"),
                            "nombre_bloque": nombre,
                            "capa": accion.get("capa"),
                            "motivo": "Nivel no encontrado: {}".format(nivel_nombre),
                            "accion": accion,
                        })
                        continue
                    inst = _crear_instancia_muro(
                        doc, simbolo, punto, nivel, rot, revit_db
                    )
                else:
                    print("    FALLO: anfitrion no soportado: {}".format(anfitrion))
                    fallos.append({
                        "orden": accion.get("orden"),
                        "nombre_bloque": nombre,
                        "capa": accion.get("capa"),
                        "motivo": "Anfitrion no soportado: {}".format(anfitrion),
                        "accion": accion,
                    })
                    continue

                _aplicar_rotacion(inst, rot, revit_db)

                exitos.append({
                    "orden": accion.get("orden"),
                    "nombre_bloque": nombre,
                    "capa": accion.get("capa"),
                    "familia": familia_nombre,
                    "simbolo": simbolo_nombre,
                    "simbolo_usado": simbolo_usado,
                    "advertencia_simbolo": advertencia_simbolo,
                    "anfitrion": anfitrion,
                    "elemento_id": (
                        inst.Id.ToString() if inst is not None else None
                    ),
                    "x_revit": x,
                    "y_revit": y,
                    "z_revit": z,
                    "rotacion": rot,
                })
                print("    OK: instancia creada id={}".format(
                    inst.Id.ToString() if inst is not None else "?"))
            except Exception as exc:
                import traceback
                print("    EXCEPCION: {}".format(exc))
                traceback.print_exc()
                fallos.append({
                    "orden": accion.get("orden"),
                    "nombre_bloque": nombre,
                    "capa": accion.get("capa"),
                    "motivo": "Excepcion: {} ({})".format(
                        type(exc).__name__, str(exc)
                    ),
                    "detalle": traceback.format_exc(),
                    "accion": accion,
                })

        # Procesar saltados y sin mapeo (siempre se registran aunque haya fallos arriba)
        for accion in acciones_saltar:
            saltados.append({
                "orden": accion.get("orden"),
                "nombre_bloque": accion.get("nombre_bloque"),
                "capa": accion.get("capa"),
                "motivo": accion.get(
                    "motivo", "Marcador no dispositivo; no crear FamilyInstance"
                ),
            })

        for accion in acciones_sin_mapeo:
            sin_mapeo.append({
                "orden": accion.get("orden"),
                "nombre_bloque": accion.get("nombre_bloque"),
                "capa": accion.get("capa"),
                "motivo": accion.get(
                    "motivo", "Sin entrada en MAPA_BLOQUES_REVIT_v3.json"
                ),
            })

        trans.Commit()
    except Exception:
        trans.RollBack()
        raise

    resultado = {
        "version": "v3",
        "script_version": SCRIPT_VERSION,
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "proyecto": reporte.get("proyecto", "RevitElectrico - T5-SantaMarta"),
        "bloque_padre": reporte.get("bloque_padre", ""),
        "nivel": reporte.get("nivel", ""),
        "chip": reporte.get("chip", ""),
        "reporte_origen": str(json_in),
        "estadisticas": {
            "total_modelar": len(acciones_modelar),
            "exitos": len(exitos),
            "fallos": len(fallos),
            "saltados_marcador": len(acciones_saltar),
            "sin_mapeo": len(acciones_sin_mapeo),
        },
        "exitos": exitos,
        "fallos": fallos,
        "saltados": saltados,
        "sin_mapeo": sin_mapeo,
    }

    _guardar_json(json_out, resultado)
    return resultado


# ---------------------------------------------------------------------------
# Tarea C: aplicar_mapa_con_host_fallback
# ---------------------------------------------------------------------------

def aplicar_mapa_con_host_fallback(doc, acciones, json_out, revit_db=None, altura_cieloraso_m=15.82):
    """
    Tarea C: recorre una lista de acciones de modelado y crea FamilyInstance
    usando host fallback techo -> muro.

    Para cada accion con anfitrion == "ceiling":
      1. Intenta buscar cara de cieloraso que contenga el punto (_buscar_cara_techo).
      2. Si no hay cara de cieloraso, busca cara de muro vertical mas cercana
         dentro de un radio (_buscar_cara_muro).
      3. Si hay cara de muro, crea la instancia sobre la cara (_instanciar_con_host
         con metodo "cara").
      4. Si no hay cara de muro ni de techo, usa el nivel "Piso 5" como fallback
         (_instanciar_con_host con metodo "nivel").

    Para cada accion con anfitrion == "muro":
      - Busca el nivel indicado y crea la instancia sobre nivel.

    Cada accion de salida se enriquece con:
      - host_resuelto: "techo" | "muro" | "nivel"
      - cara_encontrada: bool
      - metodo_ajustado: None | "ceiling->muro_fallback" | "ceiling->nivel_fallback"

    Parametros:
      doc: Documento de Revit activo.
      acciones: Lista de diccionarios de acciones (cada uno con nombre_bloque,
                familia, simbolo, anfitrion, x_revit, y_revit, z_revit,
                rotacion, nivel_revit, orden, capa).
      json_out: Ruta del JSON de resultado de salida.
      revit_db: Diccionario con clases de la API de Revit (para pruebas).
      altura_cieloraso_m: Altura esperada del cieloraso en metros (default 15.82).

    Devuelve el diccionario de resultado (también escrito en disco).
    """
    if revit_db is None:
        revit_db = _get_revit_db()

    Transaction = revit_db["Transaction"]

    exitos = []
    fallos = []
    saltados = []
    sin_mapeo = []

    trans = Transaction(doc, "RE_APLICAR_MAPA_V3 — Host Fallback Techo->Muro")
    trans.Start()

    try:
        total_acciones = len(acciones)
        print("Procesando {} acciones con host fallback...".format(total_acciones))
        for indice, accion in enumerate(acciones, start=1):
            nombre = accion.get("nombre_bloque", "")
            familia_nombre, simbolo_nombre = _nombres_accion(accion)
            anfitrion = accion.get("anfitrion")
            x = accion.get("x_revit")
            y = accion.get("y_revit")
            z = accion.get("z_revit")
            rot = accion.get("rotacion", 0)
            nivel_nombre = accion.get("nivel_revit")

            print("  [{}/{}] {} (anfitrion={}, familia={})".format(
                indice, total_acciones, nombre, anfitrion, familia_nombre))

            try:
                simbolo, simbolo_usado = _buscar_symbol_por_nombre(
                    doc, familia_nombre, simbolo_nombre, revit_db
                )
                if simbolo is None:
                    print("    FALLO: familia o simbolo no encontrado: {} / {}".format(
                        familia_nombre, simbolo_nombre))
                    fallos.append({
                        "orden": accion.get("orden"),
                        "nombre_bloque": nombre,
                        "capa": accion.get("capa"),
                        "motivo": "Familia o simbolo no encontrado: {} / {}".format(
                            familia_nombre, simbolo_nombre
                        ),
                        "accion": accion,
                    })
                    continue

                advertencia_simbolo = None
                if simbolo_usado and simbolo_usado.lower() != simbolo_nombre.lower():
                    advertencia_simbolo = "Simbolo solicitado '{}', se uso '{}'".format(
                        simbolo_nombre, simbolo_usado
                    )

                punto = [x, y, z]
                nivel = (
                    _buscar_nivel_por_nombre(doc, nivel_nombre, revit_db)
                    if nivel_nombre
                    else None
                )

                host_resuelto = None
                cara_encontrada = False
                metodo_ajustado = None
                inst = None

                if anfitrion == "ceiling":
                    # 1. Buscar cara de cieloraso
                    cara_techo, techo_elem = _buscar_cara_techo(
                        doc, punto, altura_cieloraso_m, revit_db
                    )
                    if cara_techo is not None:
                        cara_encontrada = True
                        host_resuelto = "techo"
                        inst, metodo_usado = _instanciar_con_host(
                            doc, simbolo, punto, cara_techo, nivel, rot, revit_db
                        )
                        print("    Cara de cieloraso encontrada (techo).")
                    else:
                        # 2. Fallback: buscar cara de muro vertical cercana
                        cara_muro, muro_elem, dist_muro = _buscar_cara_muro(
                            doc, punto, radio_busqueda_m=1.5, revit_db=revit_db
                        )
                        if cara_muro is not None:
                            cara_encontrada = True
                            host_resuelto = "muro"
                            metodo_ajustado = "ceiling->muro_fallback"
                            inst, metodo_usado = _instanciar_con_host(
                                doc, simbolo, punto, cara_muro, nivel, rot, revit_db
                            )
                            print("    AVISO: sin cara de cieloraso; fallback a muro (dist={:.2f} m) para {}".format(
                                dist_muro, nombre))
                        else:
                            # 3. Fallback final: nivel "Piso 5"
                            host_resuelto = "nivel"
                            metodo_ajustado = "ceiling->nivel_fallback"
                            nivel_piso5 = _buscar_nivel_por_nombre(doc, "Piso 5", revit_db)
                            if nivel_piso5 is None:
                                print("    FALLO: sin cara de cieloraso, sin muro y sin nivel 'Piso 5' para {}".format(nombre))
                                fallos.append({
                                    "orden": accion.get("orden"),
                                    "nombre_bloque": nombre,
                                    "capa": accion.get("capa"),
                                    "motivo": "No se encontro cara de cieloraso, muro ni nivel 'Piso 5' para host fallback",
                                    "accion": accion,
                                })
                                continue
                            inst, metodo_usado = _instanciar_con_host(
                                doc, simbolo, punto, None, nivel_piso5, rot, revit_db
                            )
                            print("    AVISO: sin cara de cieloraso ni muro; usando nivel 'Piso 5' para {}".format(nombre))
                elif anfitrion == "muro":
                    host_resuelto = "nivel"
                    if nivel is None:
                        print("    FALLO: nivel no encontrado: {}".format(nivel_nombre))
                        fallos.append({
                            "orden": accion.get("orden"),
                            "nombre_bloque": nombre,
                            "capa": accion.get("capa"),
                            "motivo": "Nivel no encontrado: {}".format(nivel_nombre),
                            "accion": accion,
                        })
                        continue
                    inst, metodo_usado = _instanciar_con_host(
                        doc, simbolo, punto, None, nivel, rot, revit_db
                    )
                else:
                    print("    FALLO: anfitrion no soportado: {}".format(anfitrion))
                    fallos.append({
                        "orden": accion.get("orden"),
                        "nombre_bloque": nombre,
                        "capa": accion.get("capa"),
                        "motivo": "Anfitrion no soportado: {}".format(anfitrion),
                        "accion": accion,
                    })
                    continue

                if inst is None:
                    print("    FALLO: no se pudo crear la instancia para {}".format(nombre))
                    fallos.append({
                        "orden": accion.get("orden"),
                        "nombre_bloque": nombre,
                        "capa": accion.get("capa"),
                        "motivo": "No se pudo crear la instancia (host_cara={}, nivel={})".format(
                            host_cara is not None if 'host_cara' in dir() else False,
                            nivel is not None,
                        ),
                        "accion": accion,
                    })
                    continue

                _aplicar_rotacion(inst, rot, revit_db)

                exitos.append({
                    "orden": accion.get("orden"),
                    "nombre_bloque": nombre,
                    "capa": accion.get("capa"),
                    "familia": familia_nombre,
                    "simbolo": simbolo_nombre,
                    "simbolo_usado": simbolo_usado,
                    "advertencia_simbolo": advertencia_simbolo,
                    "anfitrion": anfitrion,
                    "host_resuelto": host_resuelto,
                    "cara_encontrada": cara_encontrada,
                    "metodo_ajustado": metodo_ajustado,
                    "elemento_id": inst.Id.ToString() if inst is not None else None,
                    "x_revit": x,
                    "y_revit": y,
                    "z_revit": z,
                    "rotacion": rot,
                })
                print("    OK: instancia creada id={} host={}".format(
                    inst.Id.ToString() if inst is not None else "?", host_resuelto))
            except Exception as exc:
                import traceback
                print("    EXCEPCION: {}".format(exc))
                traceback.print_exc()
                fallos.append({
                    "orden": accion.get("orden"),
                    "nombre_bloque": nombre,
                    "capa": accion.get("capa"),
                    "motivo": "Excepcion: {} ({})".format(
                        type(exc).__name__, str(exc)
                    ),
                    "detalle": traceback.format_exc(),
                    "accion": accion,
                })

        trans.Commit()
    except Exception:
        trans.RollBack()
        raise

    resultado = {
        "version": "v3-host-fallback",
        "script_version": SCRIPT_VERSION,
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "proyecto": "RevitElectrico - T5-SantaMarta",
        "chip": "SANTAMARTA_T5",
        "estadisticas": {
            "total_modelar": len(acciones),
            "exitos": len(exitos),
            "fallos": len(fallos),
            "saltados": len(saltados),
            "sin_mapeo": len(sin_mapeo),
        },
        "exitos": exitos,
        "fallos": fallos,
        "saltados": saltados,
        "sin_mapeo": sin_mapeo,
    }

    _guardar_json(json_out, resultado)
    return resultado


SCRIPT_VERSION = "v02-20261023-host-fallback"


def main():
    print("=" * 60)
    print("RE_APLICAR_MAPA_V3_REVIT_v02 — Crear FamilyInstance en Revit 2026")
    print("Version del script: {} | {}".format(
        SCRIPT_VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)

    # Forzar recarga del módulo actual para evitar que pyRevit use una
    # versión cached (IronPython a veces mantiene el modulo anterior en memoria).
    import sys as _sys
    _mod_name = __name__
    if _mod_name in _sys.modules:
        try:
            import importlib as _importlib
            _importlib.reload(_sys.modules[_mod_name])
        except Exception:
            pass

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
        print("Abra un archivo .rvt en Revit y vuelva a ejecutar este script.")
        return {
            "conectado": False,
            "documento_activo": False,
        }

    print("Documento: {}".format(doc.Title))

    import argparse

    parser = argparse.ArgumentParser(
        description="Crea FamilyInstance en Revit 2026 desde el reporte de RE_APLICAR_MAPA_V3_v01.py"
    )
    parser.add_argument(
        "--json-in",
        type=str,
        default="",
        help="Ruta al JSON de reporte de RE_APLICAR_MAPA_V3_v01.py "
        "(si se omite se usa la ruta por defecto data/apto_F_02_aplicar_mapa_v3.json)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de resultado de salida",
    )
    parser.add_argument(
        "--host-fallback",
        action="store_true",
        default=False,
        help="Usar host fallback techo->muro (Tarea C)",
    )

    args = parser.parse_args()

    json_in = args.json_in
    if not json_in:
        root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
        json_in = os.path.join(
            root, "data", "apto_F_02_aplicar_mapa_v3.json"
        )
        print("  (--json-in no indicado; usando ruta por defecto: {})".format(json_in))
    if not os.path.exists(json_in):
        raise SystemExit(
            "El archivo JSON de entrada no existe: {}".format(json_in)
        )

    if args.json_out:
        json_out = args.json_out
    else:
        root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
        json_out = os.path.join(
            root, "data", "apto_F_02_aplicar_mapa_v3_resultado.json"
        )

    if args.host_fallback:
        # Leer reporte y extraer solo las acciones_modelar para pasar a la nueva función
        reporte = _cargar_json(json_in)
        acciones = reporte.get("acciones_modelar", [])
        # Si el JSON viene enriquecido (acciones_enriquecidas), usar esas acciones
        # que ya llevan familia_real / simbolo_real resueltos.
        if not acciones and reporte.get("acciones_enriquecidas"):
            acciones = reporte.get("acciones_enriquecidas")
        resultado = aplicar_mapa_con_host_fallback(doc, acciones, json_out, revit_db)
    else:
        reporte = _cargar_json(json_in)
        acciones = reporte.get("acciones_modelar", [])
        if not acciones and reporte.get("acciones_enriquecidas"):
            acciones = reporte.get("acciones_enriquecidas")
        resultado = aplicar_mapa_revit(doc, json_in, json_out, revit_db, acciones=acciones)

    print()
    print("Fecha ejecucion: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=== Resultado ===")
    print("Total a modelar: {}".format(resultado["estadisticas"]["total_modelar"]))
    print("Exitos: {}".format(resultado["estadisticas"]["exitos"]))
    print("Fallos: {}".format(resultado["estadisticas"]["fallos"]))
    if "saltados_marcador" in resultado["estadisticas"]:
        print(
            "Saltados (marcador): {}".format(
                resultado["estadisticas"]["saltados_marcador"]
            )
        )
        print("Sin mapeo: {}".format(resultado["estadisticas"]["sin_mapeo"]))
    else:
        print("Saltados: {}".format(resultado["estadisticas"]["saltados"]))
        print("Sin mapeo: {}".format(resultado["estadisticas"]["sin_mapeo"]))
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)

    return resultado


if __name__ == "__main__":
    main()
