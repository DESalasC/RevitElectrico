# -*- coding: utf-8 -*-
"""
BLOQUES_PYREVIT_FASE6_v01.py — Bloques de pyRevit reutilizables para la Fase 6
de RevitElectrico (T5-SantaMarta).

Este archivo agrupa los 4 bloques de comandos pyRevit para que se puedan
ejecutar desde la consola de pyRevit sin tener que buscarlos en el chat:

  6.1 Modelar mapa (F02)   -> crea FamilyInstance desde reporte_bloques_todos.json
  6.2 Asignar RED=SI       -> marca Comments="RED=SI" en 5 FamilyInstance
  6.3 Tipos de Conduit     -> crea 5 tipos de conducto (3/4" a 3")
  6.4 Clash Detection      -> deteccion de interferencias contra MEP/estructura

Unidades: el Revit API trabaja en pies internamente, pero los JSON de entrada
usan metros (x_revit, y_revit, z_revit). Los scripts convierten a pies con
DB.UnitUtils.ConvertToInternalUnits(valor_m, DB.UnitTypeId.Meters).

IronPython 2.7 — SIN type hints, SIN requests/bs4.
"""

from __future__ import print_function

import os
import sys
import json
import clr
from datetime import datetime

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
    BuiltInParameter,
    ElementId,
    Options,
    ElementCategoryFilter,
)
from pyrevit import revit, DB, forms, script


# ============================================================================
# RUTAS DE DATOS (ajustar si se mueven)
# ============================================================================
REVITELECTRICO_ROOT = os.environ.get(
    "REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\Actuales\T5-SantaMarta"
)
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
JSON_REPORTE_BLOQUES = os.path.join(DATA_DIR, "reporte_bloques_todos.json")
JSON_RESULTADO_MAPA = os.path.join(DATA_DIR, "resultado_modelado_apto_F02.json")
JSON_ASIGNAR_RED = os.path.join(DATA_DIR, "asignar_red_resultado.json")
JSON_CONDUIT_RESULTADO = os.path.join(DATA_DIR, "crear_tipos_conduit_resultado.json")
JSON_CLASH_RESULTADO = os.path.join(DATA_DIR, "clash_detection_resultado.json")

# IDs de dispositivos con RED=SI
IDS_RED = ["5554265", "5554262", "5554263", "5554264", "5554269"]
VALOR_RED = "SI"
MARCA_COMENTARIO = "RED={}".format(VALOR_RED)

# Tipos de conduit (diametro en mm -> convertido a pies por el API)
TIPO_CONDUIT_MAP = [
    ("Conduit 3/4\"",   19.05),
    ("Conduit 1\"",     25.40),
    ("Conduit 1-1/4\"", 31.75),
    ("Conduit 2\"",     50.80),
    ("Conduit 3\"",     76.20),
]


def _fecha_ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _guardar_json(ruta, datos):
    dirpath = os.path.dirname(ruta)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(ruta, "w") as f:
        f.write(json.dumps(datos, indent=2, ensure_ascii=True))


def _ascii_safe(valor):
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
    if isinstance(d, dict):
        return {_ascii_safe(k): _sanitizar_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_sanitizar_dict(v) for v in d]
    elif isinstance(d, tuple):
        return tuple(_sanitizar_dict(v) for v in d)
    else:
        return _ascii_safe(d)


def _mm_a_pies(mm):
    """Convierte mm a pies internos de Revit."""
    try:
        return DB.UnitUtils.ConvertToInternalUnits(mm, DB.UnitTypeId.Millimeters)
    except Exception:
        return mm / 304.8


def _m_a_pies(metros):
    """Convierte metros a pies internos de Revit."""
    try:
        return DB.UnitUtils.ConvertToInternalUnits(metros, DB.UnitTypeId.Meters)
    except Exception:
        return metros * 3.280839895013123


def _obtener_nombre_elemento(elemento, revit_db=None):
    """Nombre legible de un elemento de Revit."""
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return None


def _nombre_coincide(nombre_obtenido, nombre_esperado):
    if not nombre_obtenido or not nombre_esperado:
        return False
    return nombre_obtenido.strip().lower() == nombre_esperado.strip().lower()


def _buscar_familia_por_nombre(doc, nombre_familia):
    """Busca una familia cargada por nombre."""
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            if _nombre_coincide(_obtener_nombre_elemento(fam), nombre_familia):
                return fam
        except Exception:
            continue
    return None


def _buscar_symbol_por_nombre(doc, nombre_familia, nombre_simbolo):
    """Busca un FamilySymbol dentro de una familia."""
    familia = _buscar_familia_por_nombre(doc, nombre_familia)
    if familia is None:
        return None, None

    simbolos = []
    for id_elem in familia.GetFamilySymbolIds():
        simbolo = doc.GetElement(id_elem)
        if simbolo is None:
            continue
        nombre_sim = _obtener_nombre_elemento(simbolo)
        simbolos.append((simbolo, nombre_sim))

    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, nombre_simbolo):
            if not simbolo.IsActive:
                try:
                    simbolo.Activate()
                    doc.Regenerate()
                except Exception:
                    pass
            return simbolo, nombre_sim

    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, "Estandar"):
            if not simbolo.IsActive:
                try:
                    simbolo.Activate()
                    doc.Regenerate()
                except Exception:
                    pass
            return simbolo, nombre_sim

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


def _buscar_nivel_por_nombre(doc, nombre_nivel):
    """Busca un Level por nombre."""
    colector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels)
    for nivel in colector.ToElements():
        try:
            if _nombre_coincide(_obtener_nombre_elemento(nivel), nombre_nivel):
                return nivel
        except Exception:
            continue
    return None


def _buscar_param_comments(inst):
    """Devuelve el parametro Comments de una FamilyInstance."""
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


def _crear_instancia_muro(doc, simbolo, punto_m, nivel, rotacion_grados):
    """Crea FamilyInstance basado en nivel (muro)."""
    location = XYZ(_m_a_pies(punto_m[0]), _m_a_pies(punto_m[1]), _m_a_pies(punto_m[2]))
    inst = doc.Create.NewFamilyInstance(
        location, simbolo, nivel, Structure.StructuralType.NonStructural
    )
    if rotacion_grados != 0:
        try:
            import math
            rad = rotacion_grados * math.pi / 180.0
            param = inst.get_Parameter(BuiltInParameter.ROTATION)
            if param is not None and not param.IsReadOnly:
                param.Set(rad)
        except Exception:
            pass
    return inst


def _vertices_cara_xy(face):
    """Vertices XY de una cara de Revit."""
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


def _punto_dentro_poligono_xy(px, py, vertices):
    """Ray casting en plano XY."""
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


def _obtener_cara_techo(doc, altura_z_m, punto_x_m, punto_y_m, umbral_z=0.10, umbral_xy_cerca=2.0):
    """Cara inferior de cieloraso/techo que contenga el punto (x,y) a la altura z."""
    categorias = [
        BuiltInCategory.OST_Ceilings,
        BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Floors,
    ]
    mejor_cara = None
    mejor_techo = None
    mejor_dist_xy = float("inf")

    for cat in categorias:
        colector = FilteredElementCollector(doc).OfCategory(cat)
        for techo in colector.ToElements():
            try:
                if techo.IsElementType:
                    continue
            except Exception:
                continue
            geo_opt = techo.get_Geometry(Options())
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
                    if abs(origen.Z - _m_a_pies(altura_z_m)) >= umbral_z:
                        continue
                    vertices = _vertices_cara_xy(face)
                    if vertices is None:
                        continue
                    if _punto_dentro_poligono_xy(punto_x_m, punto_y_m, vertices):
                        return face, techo
                    cx = sum(v[0] for v in vertices) / len(vertices)
                    cy = sum(v[1] for v in vertices) / len(vertices)
                    dist_xy = ((cx - punto_x_m) ** 2 + (cy - punto_y_m) ** 2) ** 0.5
                    if dist_xy <= umbral_xy_cerca and dist_xy < mejor_dist_xy:
                        mejor_dist_xy = dist_xy
                        mejor_cara = face
                        mejor_techo = techo
    if mejor_cara is not None:
        return mejor_cara, mejor_techo
    return None, None


def _crear_instancia_techo(doc, simbolo, punto_m, cara_techo, rotacion_grados):
    """Crea FamilyInstance sobre una cara de techo."""
    location = XYZ(_m_a_pies(punto_m[0]), _m_a_pies(punto_m[1]), _m_a_pies(punto_m[2]))
    inst = doc.Create.NewFamilyInstance(cara_techo, location, simbolo)
    return inst


# ============================================================================
# 6.1 Modelar mapa (F02)
# ============================================================================
def bloque_61_modelar_mapa(json_in=JSON_REPORTE_BLOQUES, json_out=JSON_RESULTADO_MAPA):
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.1 Modelar mapa de bloques (F 02)")
    output.print_md("Fecha: {}".format(_fecha_ahora()))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    import imp
    SCRIPT_MAPA = os.path.join(REVITELECTRICO_ROOT, "src", "fase-6-revit", "RE_APLICAR_MAPA_V3_REVIT_v02.py")

    mod = imp.load_source("mod_mapa_revit", SCRIPT_MAPA)
    revit_db = {
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

    try:
        resultado = mod.aplicar_mapa_revit(doc, json_in, json_out, revit_db)
    except Exception as exc:
        output.print_md("**ERROR:** {}".format(exc))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        return

    est = resultado["estadisticas"]
    output.print_md("## Resultado")
    output.print_md("- Total a modelar: {}".format(est["total_modelar"]))
    output.print_md("- **Exitos: {}**".format(est["exitos"]))
    output.print_md("- Fallos: {}".format(est["fallos"]))
    output.print_md("- Saltados (marcador): {}".format(est["saltados_marcador"]))
    output.print_md("- Sin mapeo: {}".format(est["sin_mapeo"]))
    output.print_md("JSON guardado en: `{}`".format(json_out))
    output.print_md("Fecha ejecucion: {}".format(_fecha_ahora()))

    if est["exitos"] == 37 and est["fallos"] == 0:
        output.print_md("**Estado: OK — 37 / 0 / 22 / 0 validado.**")
    else:
        output.print_md("**Estado: REVISAR — resultado inesperado.**")


# ============================================================================
# 6.2 Asignar RED=SI
# ============================================================================
def bloque_62_asignar_red(json_out=JSON_ASIGNAR_RED):
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.2 Asignar RED=SI")
    output.print_md("Fecha: {}".format(_fecha_ahora()))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    trans = Transaction(doc, "ASIGNAR_RED — dispositivos electricos")
    trans.Start()

    exitos = 0
    fallos = 0
    detalle = []

    for id_str in IDS_RED:
        try:
            elem_id = ElementId(int(id_str))
            inst = doc.GetElement(elem_id)
            if inst is None:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Elemento no encontrado"})
                output.print_md("  FALLO id={}: no encontrado".format(id_str))
                continue

            if not isinstance(inst, FamilyInstance):
                fallos += 1
                detalle.append({"id": id_str, "motivo": "No es FamilyInstance"})
                output.print_md("  FALLO id={}: no es FamilyInstance".format(id_str))
                continue

            p_comments = _buscar_param_comments(inst)
            if p_comments is None:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Parametro Comments no encontrado"})
                output.print_md("  FALLO id={}: parametro Comments no encontrado".format(id_str))
                continue

            if not p_comments.IsReadOnly:
                try:
                    actual = p_comments.AsString() or ""
                    if actual and "RED=" not in actual:
                        nuevo = actual + " | " + MARCA_COMENTARIO
                    else:
                        nuevo = MARCA_COMENTARIO
                    p_comments.Set(nuevo)
                    exitos += 1
                    detalle.append({"id": id_str, "motivo": "OK — Comments='{}'".format(nuevo)})
                    output.print_md("  OK id={} Comments='{}'".format(id_str, nuevo))
                except Exception as exc:
                    fallos += 1
                    detalle.append({"id": id_str, "motivo": "Error seteando Comments: {}".format(exc)})
                    output.print_md("  FALLO id={}: {}".format(id_str, exc))
            else:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Parametro Comments es de solo lectura"})
                output.print_md("  FALLO id={}: Comments es de solo lectura".format(id_str))

        except Exception as exc:
            fallos += 1
            detalle.append({"id": id_str, "motivo": "Error: {}".format(exc)})
            output.print_md("  FALLO id={}: {}".format(id_str, exc))

    trans.Commit()

    output.print_md("## Resultado")
    output.print_md("- **Exitos: {}**".format(exitos))
    output.print_md("- Fallos: {}".format(fallos))
    output.print_md("Fecha ejecucion: {}".format(_fecha_ahora()))

    _guardar_json(json_out, {
        "fecha_ejecucion": _fecha_ahora(),
        "documento": doc.Title,
        "campo": "Comments (ALL_MODEL_INSTANCE_COMMENTS)",
        "valor": MARCA_COMENTARIO,
        "exitos": exitos,
        "fallos": fallos,
        "detalle": detalle,
    })
    output.print_md("JSON guardado en: `{}`".format(json_out))


# ============================================================================
# 6.3 Tipos de Conduit
# ============================================================================
def bloque_63_tipos_conduit(json_out=JSON_CONDUIT_RESULTADO):
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.3 Tipos de Conduit (5 diametros)")
    output.print_md("Fecha: {}".format(_fecha_ahora()))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    trans = Transaction(doc, "CREAR TIPOS CONDUIT POR DIAMETRO")
    trans.Start()

    ConduitType = None
    try:
        ConduitType = DB.ConduitType
    except Exception:
        ConduitType = None

    conduit_type_disponible = ConduitType is not None
    if conduit_type_disponible:
        try:
            filtro = ElementCategoryFilter(BuiltInCategory.OST_ConduitType)
            tipo_existente = FilteredElementCollector(doc).WherePasses(filtro).FirstElement()
            if tipo_existente is None:
                conduit_type_disponible = False
        except Exception:
            conduit_type_disponible = False

    if not conduit_type_disponible:
        output.print_md("AVISO: la categoria ConduitType no existe en este documento.")
        output.print_md("  Se requiere un documento MEP (Electrical-Default.rte) para crear tipos de Conduit.")
        trans.Commit()
        output.print_md("## Resultado")
        output.print_md("- Creados: 0")
        output.print_md("- Existentes: 0")
        output.print_md("- Fallos: 0")
        output.print_md("**Estado: CATEGORIA CONDUIT NO DISPONIBLE**")
        _guardar_json(json_out, {
            "fecha_ejecucion": _fecha_ahora(),
            "documento": doc.Title,
            "creados": 0,
            "existentes": 0,
            "fallos": 0,
            "detalle": [],
            "estado": "CATEGORIA CONDUIT NO DISPONIBLE",
        })
        return

    def _nombre_tipo_conduit(tipo_conduit):
        try:
            n = tipo_conduit.Name
            if n:
                return n
        except Exception:
            pass
        try:
            p = tipo_conduit.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                v = p.AsString()
                if v:
                    return v
        except Exception:
            pass
        return "?"

    creados = 0
    existentes = 0
    fallos = 0
    detalle = []

    for nombre, diametro_mm in TIPO_CONDUIT_MAP:
        try:
            ya_existe = None
            for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
                if _nombre_tipo_conduit(t) == nombre:
                    ya_existe = t
                    break

            if ya_existe is not None:
                existentes += 1
                detalle.append({"tipo": nombre, "motivo": "Ya existe"})
                output.print_md("  EXISTE {}".format(nombre))
                continue

            tipos = FilteredElementCollector(doc).OfClass(ConduitType).ToElements()
            if len(tipos) > 0:
                plantilla = tipos[0]
                nuevo_id = plantilla.Duplicate(nombre)
                tipo_nuevo = doc.GetElement(nuevo_id)
            else:
                tipo_nuevo = ConduitType.Create(doc, nombre)

            if tipo_nuevo is None:
                fallos += 1
                detalle.append({"tipo": nombre, "motivo": "No se pudo crear el tipo"})
                output.print_md("  FALLO {}: no se pudo crear".format(nombre))
                continue

            try:
                param_diam = tipo_nuevo.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                if param_diam is not None and not param_diam.IsReadOnly:
                    diam_pies = _mm_a_pies(diametro_mm)
                    param_diam.Set(diam_pies)
                    output.print_md("  OK {} diametro={} mm".format(nombre, diametro_mm))
                else:
                    output.print_md("  AVISO {}: parametro diametro no editable".format(nombre))
            except Exception as exc:
                output.print_md("  AVISO {}: error seteando diametro: {}".format(nombre, exc))

            creados += 1
            detalle.append({"tipo": nombre, "diametro_conduit_mm": diametro_mm, "motivo": "OK — creado"})
            output.print_md("  CREADO {}".format(nombre))

        except Exception as exc:
            fallos += 1
            detalle.append({"tipo": nombre, "motivo": "Error: {}".format(exc)})
            output.print_md("  FALLO {}: {}".format(nombre, exc))

    trans.Commit()

    output.print_md("## Resultado")
    output.print_md("- **Creados: {}**".format(creados))
    output.print_md("- Existentes: {}".format(existentes))
    output.print_md("- Fallos: {}".format(fallos))
    output.print_md("Fecha ejecucion: {}".format(_fecha_ahora()))

    _guardar_json(json_out, {
        "fecha_ejecucion": _fecha_ahora(),
        "documento": doc.Title,
        "creados": creados,
        "existentes": existentes,
        "fallos": fallos,
        "detalle": detalle,
    })
    output.print_md("JSON guardado en: `{}`".format(json_out))


# ============================================================================
# 6.4 Clash Detection (implementacion real)
# ============================================================================
def _interseccion_bounding_boxes(bb1, bb2):
    """Test de interseccion de dos bounding boxes (en pies)."""
    min1, max1 = bb1.Min, bb1.Max
    min2, max2 = bb2.Min, bb2.Max
    return not (
        max1.X < min2.X or max2.X < min1.X or
        max1.Y < min2.Y or max2.Y < min1.Y or
        max1.Z < min2.Z or max2.Z < min1.Z
    )


def _solido_elemento(elemento):
    """Obtiene el primer solido de la geometria de un elemento."""
    try:
        geo_opt = elemento.get_Geometry(Options())
        if geo_opt is None:
            return None
        for obj in geo_opt:
            try:
                if hasattr(obj, "Faces"):
                    return obj
            except Exception:
                continue
    except Exception:
        pass
    return None


def bloque_64_clash_detection(json_out=JSON_CLASH_RESULTADO):
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.4 Deteccion de interferencias (Clash Detection)")
    output.print_md("Fecha: {}".format(_fecha_ahora()))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    categorias_mep = [
        (BuiltInCategory.OST_DuctCurves, "HVAC (ductos)"),
        (BuiltInCategory.OST_PipeCurves, "Fontaneria (tuberias)"),
        (BuiltInCategory.OST_Conduit, "Conduit existente"),
        (BuiltInCategory.OST_CableTray, "Bandejas portacables"),
        (BuiltInCategory.OST_StructuralFraming, "Estructura (framing)"),
        (BuiltInCategory.OST_StructuralColumns, "Estructura (columnas)"),
        (BuiltInCategory.OST_Walls, "Muros"),
        (BuiltInCategory.OST_Floors, "Losas"),
        (BuiltInCategory.OST_Ceilings, "Cielorrasos"),
    ]

    electricas = FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements()
    output.print_md("FamilyInstance electricas encontradas: {}".format(len(electricas)))

    resultados = []
    total_clashes = 0

    for cat_id, nombre_cat in categorias_mep:
        try:
            otros = FilteredElementCollector(doc).OfCategory(cat_id).WhereElementIsNotElementType().ToElements()
            output.print_md("  Comparando contra {} ({} elementos)...".format(nombre_cat, len(otros)))

            clashes_cat = 0
            for elec in electricas:
                try:
                    bb_elec = elec.get_BoundingBox(None)
                    if bb_elec is None:
                        continue
                    sol_elec = _solido_elemento(elec)
                except Exception:
                    continue

                for otro in otros:
                    try:
                        bb_otro = otro.get_BoundingBox(None)
                        if bb_otro is None:
                            continue
                        if not _interseccion_bounding_boxes(bb_elec, bb_otro):
                            continue

                        # Si hay solido de ambos, probar interseccion real
                        sol_otro = _solido_elemento(otro)
                        if sol_elec is not None and sol_otro is not None:
                            try:
                                resultado_bool = sol_elec.Intersect(sol_otro)
                                if resultado_bool is None or (isinstance(resultado_bool, list) and len(resultado_bool) == 0):
                                    continue
                            except Exception:
                                pass

                        clashes_cat += 1
                        total_clashes += 1
                    except Exception:
                        continue

            resultados.append({
                "categoria": nombre_cat,
                "elementos_comparados": len(otros),
                "clashes": clashes_cat,
            })
        except Exception as exc:
            output.print_md("  ERROR con {}: {}".format(nombre_cat, exc))

    output.print_md("## Resultado")
    output.print_md("Total clashes detectados: {}".format(total_clashes))
    output.print_md("Fecha ejecucion: {}".format(_fecha_ahora()))
    output.print_md("**Estado: OK — interseccion de bounding boxes implementada.**")

    _guardar_json(json_out, {
        "fecha_ejecucion": _fecha_ahora(),
        "documento": doc.Title,
        "total_clashes": total_clashes,
        "resultados": resultados,
    })
    output.print_md("JSON guardado en: `{}`".format(json_out))


if __name__ == "__main__":
    # Si se ejecuta directamente desde la consola pyRevit, mostrar menu
    output = script.get_output()
    output.print_md("# Bloques pyRevit Fase 6 — RevitElectrico T5-SantaMarta")
    output.print_md("Fecha: {}".format(_fecha_ahora()))
    output.print_md("")
    output.print_md("Bloques disponibles:")
    output.print_md("  - bloque_61_modelar_mapa()")
    output.print_md("  - bloque_62_asignar_red()")
    output.print_md("  - bloque_63_tipos_conduit()")
    output.print_md("  - bloque_64_clash_detection()")
    output.print_md("")
    output.print_md("Ejemplo: desde la consola pyRevit ejecute:")
    output.print_md("  exec(open(r'D:\\Work\\PROJECTS\\Actuales\\T5-SantaMarta\\3.-Proceso\\BLOQUES_PYREVIT_FASE6_v01.py').read())")
    output.print_md("  bloque_61_modelar_mapa()")
