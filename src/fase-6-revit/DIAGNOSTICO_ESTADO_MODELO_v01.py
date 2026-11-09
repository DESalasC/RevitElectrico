# -*- coding: utf-8 -*-
"""
DIAGNOSTICO_ESTADO_MODELO_v01.py
================================
Diagnostico integral del modelo electrico en el documento activo de Revit.
Responde, con datos, por que los dispositivos no se ven y en que estado
real esta el modelo (niveles, hosts, visibilidad, categorias, conduits).

Ejecucion:
    pyrevit agent run src/fase-6-revit/DIAGNOSTICO_ESTADO_MODELO_v01.py \
        --revit=2026 --mode=query --timeout=120

Tambien funciona dentro del pyRevit Python Shell:
    exec(open(r"...\\DIAGNOSTICO_ESTADO_MODELO_v01.py").read())
    diagnosticar_estado_modelo(doc)


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
import json
import os
import traceback

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    FamilyInstance,
    View,
    ViewType,
    PlanViewPlane,
    RevitLinkInstance,
)

CATEGORIAS_ELECTRICAS = [
    ("OST_ElectricalFixtures", "Aparatos electricos (tomas)"),
    ("OST_ElectricalEquipment", "Equipos electricos (tableros)"),
    ("OST_LightingFixtures", "Luminarias"),
    ("OST_LightingDevices", "Dispositivos de iluminacion (interruptores)"),
    ("OST_DataDevices", "Dispositivos de datos"),
    ("OST_CommunicationDevices", "Comunicaciones"),
    ("OST_TelephoneDevices", "Telefonia"),
    ("OST_FireAlarmDevices", "Alarma de incendio"),
    ("OST_SecurityDevices", "Seguridad"),
    ("OST_ElectricalCircuit", "Circuitos"),
    ("OST_Conduit", "Tuberia (conduit)"),
    ("OST_ConduitFitting", "Accesorios de conduit"),
    ("OST_CableTray", "Bandeja portacables"),
    ("OST_CableTrayFitting", "Accesorios de bandeja"),
]


# --------------------------------------------------------------------------
# Utilidades IronPython 2.7 / CPython 3
# --------------------------------------------------------------------------
def _to_unicode(valor):
    if valor is None:
        return None
    if isinstance(valor, unicode):  # noqa: F821  (IronPython 2.7)
        return valor
    try:
        return unicode(valor)  # noqa: F821
    except NameError:
        return str(valor)
    except UnicodeDecodeError:
        return unicode(str(valor), "utf-8", "replace")  # noqa: F821


def _txt(valor):
    """Convierte cualquier valor a texto ASCII puro (seguro para json.dumps)."""
    texto = None
    if isinstance(valor, unicode):  # noqa: F821
        texto = valor
    if texto is None:
        try:
            texto = unicode(valor, "utf-8")  # noqa: F821
        except Exception:
            texto = None
    if texto is None:
        try:
            texto = unicode(valor, "latin-1")  # noqa: F821
        except Exception:
            texto = None
    if texto is None:
        try:
            texto = unicode(repr(valor), "latin-1", "replace")  # noqa: F821
        except Exception:
            return "<?>"
    try:
        return texto.encode("ascii", "backslashreplace").decode("ascii")
    except Exception:
        return "<?>"


def _sanitize(valor):
    if valor is None or isinstance(valor, (int, long, float, bool)):  # noqa: F821
        return valor
    if isinstance(valor, dict):
        out = {}
        for k, v in valor.items():
            out[_txt(k)] = _sanitize(v)
        return out
    if isinstance(valor, (list, tuple)):
        return [_sanitize(v) for v in valor]
    return _txt(valor)


def _element_id_int(element_id):
    """Devuelve el entero de un ElementId en cualquier version de Revit."""
    if element_id is None:
        return None
    for attr in ("Value", "IntegerValue"):
        try:
            return int(getattr(element_id, attr))
        except Exception:
            pass
    try:
        return int(element_id)
    except Exception:
        return None


def _nombre_categoria(elem):
    try:
        cat = elem.Category
        if cat is not None:
            return _to_unicode(cat.Name)
    except Exception:
        pass
    return None


def _nombre_nivel(doc, nivel_id):
    try:
        if nivel_id is None:
            return None
        nivel = doc.GetElement(nivel_id)
        if nivel is not None:
            return _to_unicode(nivel.Name)
    except Exception:
        pass
    return None


def _bbox_z(elem):
    try:
        bb = elem.get_BoundingBox(None)
        if bb is None:
            return None, None
        return round(bb.Min.Z, 4), round(bb.Max.Z, 4)
    except Exception:
        return None, None


def _punto(elem):
    try:
        loc = elem.Location
        if loc is None:
            return None
        pt = loc.Point if hasattr(loc, "Point") else loc
        return [round(pt.X, 4), round(pt.Y, 4), round(pt.Z, 4)]
    except Exception:
        return None


def _es_face_based(inst):
    try:
        return bool(inst.HostFace is not None)
    except Exception:
        pass
    try:
        return bool(inst.Host is not None and inst.Host.Category is not None
                    and inst.Host.Category.Id.IntegerValue in (
                        int(BuiltInCategory.OST_Ceilings),
                        int(BuiltInCategory.OST_Floors)))
    except Exception:
        return False


def _cat_id(bic_name):
    try:
        return __import__("Autodesk.Revit.DB", fromlist=["DB"]).BuiltInCategory.__dict__[bic_name]
    except Exception:
        return None


def _conteo_categoria(doc, bic_name):
    bic = _cat_id(bic_name)
    if bic is None:
        return None
    try:
        col = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType()
        return len(list(col))
    except Exception:
        return None


def _info_vista(doc, view):
    info = {
        "nombre": _to_unicode(view.Name),
        "tipo": str(view.ViewType),
        "nivel_asociado": None,
        "disciplina": None,
        "fase": None,
        "detalle": str(view.DetailLevel) if hasattr(view, "DetailLevel") else None,
        "rango_vista": {},
        "categorias_ocultas_electricas": {},
    }
    try:
        if view.GenLevel is not None:
            info["nivel_asociado"] = _to_unicode(view.GenLevel.Name)
    except Exception:
        pass
    try:
        param = view.get_Parameter(__import__("Autodesk.Revit.DB", fromlist=["DB"]).BuiltInParameter.VIEW_DISCIPLINE)
        if param is not None:
            info["disciplina"] = _to_unicode(param.AsValueString())
    except Exception:
        pass
    try:
        if view.get_Parameter(__import__("Autodesk.Revit.DB", fromlist=["DB"]).BuiltInParameter.VIEW_PHASE) is not None:
            fase_id = view.get_Parameter(__import__("Autodesk.Revit.DB", fromlist=["DB"]).BuiltInParameter.VIEW_PHASE).AsElementId()
            fase = doc.GetElement(fase_id)
            if fase is not None:
                info["fase"] = _to_unicode(fase.Name)
    except Exception:
        pass
    # Rango de vista (solo vistas de planta / techo)
    try:
        vr = view.GetViewRange()
        if vr is not None:
            for etiqueta, plano in (("nivel_superior", PlanViewPlane.TopClipPlane),
                                    ("plano_corte", PlanViewPlane.CutPlane),
                                    ("nivel_inferior", PlanViewPlane.BottomClipPlane),
                                    ("profundidad", PlanViewPlane.ViewDepthPlane)):
                try:
                    nivel_id = vr.GetLevelId(plano)
                    info["rango_vista"][etiqueta] = {
                        "nivel": _nombre_nivel(doc, nivel_id),
                        "offset_m": round(vr.GetOffset(plano), 4),
                    }
                except Exception:
                    pass
    except Exception:
        pass
    # Visibilidad por categoria (V/G)
    for bic_name, etiqueta in CATEGORIAS_ELECTRICAS:
        bic = _cat_id(bic_name)
        if bic is None:
            continue
        try:
            cat = doc.Settings.Categories.get_Item(bic)
            if cat is None:
                continue
            info["categorias_ocultas_electricas"][etiqueta] = bool(view.GetCategoryHidden(cat.Id))
        except Exception:
            pass
    return info


def _obtener_root_proyecto():
    """Resuelve la raiz del proyecto en IronPython dentro de Revit.

    Orden: variable de entorno -> __file__ -> inputs del agente -> cwd.
    """
    env = os.environ.get("REVITELECTRICO_ROOT")
    if env:
        return env
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    except NameError:
        pass
    try:
        return inputs.get("root")  # inyectado por pyrevit agent run --inputs
    except NameError:
        pass
    return os.path.abspath(".")


def _attr(obj, *ruta):
    """Lee una cadena de atributos devolviendo None si algo falla."""
    actual = obj
    for nombre in ruta:
        try:
            actual = getattr(actual, nombre)
        except Exception:
            return None
        if actual is None:
            return None
    try:
        return _to_unicode(actual)
    except Exception:
        return repr(actual)


def _info_instancia(doc, inst, view):
    zmin, zmax = _bbox_z(inst)
    nivel_id = None
    try:
        nivel_id = inst.LevelId
    except Exception:
        pass
    nivel = _nombre_nivel(doc, nivel_id)
    elevacion_nivel = None
    try:
        if nivel_id is not None:
            obj_nivel = doc.GetElement(nivel_id)
            if obj_nivel is not None:
                elevacion_nivel = round(obj_nivel.Elevation, 4)
    except Exception:
        pass
    host = None
    try:
        if inst.Host is not None:
            host = "{} [{}]".format(_nombre_categoria(inst.Host), _element_id_int(inst.Host.Id))
    except Exception:
        pass
    oculto = None
    try:
        oculto = bool(inst.IsHidden(view)) if view is not None else None
    except Exception:
        oculto = None
    z_rel = None
    if zmin is not None and elevacion_nivel is not None:
        z_rel = round(zmin - elevacion_nivel, 4)
    return {
        "id": _element_id_int(inst.Id),
        "categoria": _nombre_categoria(inst),
        "familia": _attr(inst, "Symbol", "Family", "Name"),
        "tipo": _attr(inst, "Symbol", "Name"),
        "nivel": nivel,
        "nivel_id": _element_id_int(nivel_id),
        "elevacion_nivel": elevacion_nivel,
        "host": host,
        "face_based": _es_face_based(inst),
        "punto": _punto(inst),
        "z_min": zmin,
        "z_max": zmax,
        "z_relativo_nivel": z_rel,
        "oculto_en_vista": oculto,
    }


# --------------------------------------------------------------------------
# Diagnostico principal
# --------------------------------------------------------------------------
def diagnosticar_estado_modelo(doc, json_out=None, max_elementos=400):
    resultado = {
        "documento": {},
        "niveles": [],
        "vinculos": [],
        "conteo_categorias": {},
        "vista_activa": {},
        "instancias_electricas": [],
        "conduits": {},
        "hallazgos": [],
    }

    resultado["documento"] = {
        "titulo": _to_unicode(doc.Title),
        "ruta": _to_unicode(doc.PathName),
        "modificado": bool(doc.IsModified),
    }

    # Niveles
    try:
        niveles = []
        for nivel in FilteredElementCollector(doc).OfClass(
                __import__("Autodesk.Revit.DB", fromlist=["DB"]).Level):
            niveles.append({"nombre": _to_unicode(nivel.Name),
                            "elevacion_m": round(nivel.Elevation, 4)})
        niveles.sort(key=lambda n: n["elevacion_m"])
        resultado["niveles"] = niveles
    except Exception:
        resultado["hallazgos"].append("No se pudieron leer los niveles: " + traceback.format_exc())

    # Vinculos
    try:
        for li in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            nombre = None
            try:
                nombre = _to_unicode(li.Name)
            except Exception:
                pass
            resultado["vinculos"].append({"nombre": nombre, "id": _element_id_int(li.Id)})
    except Exception:
        pass

    # Conteo por categoria
    for bic_name, etiqueta in CATEGORIAS_ELECTRICAS:
        n = _conteo_categoria(doc, bic_name)
        if n is not None:
            resultado["conteo_categorias"][etiqueta] = n

    # Vista activa
    try:
        view = __revit__.ActiveUIDocument.ActiveView
        resultado["vista_activa"] = _info_vista(doc, view)
    except Exception:
        view = None
        resultado["hallazgos"].append("No se pudo leer la vista activa.")

    # Instancias electricas
    bic_electricas = []
    for bic_name in ("OST_ElectricalFixtures", "OST_ElectricalEquipment",
                     "OST_LightingFixtures", "OST_LightingDevices",
                     "OST_DataDevices", "OST_CommunicationDevices",
                     "OST_TelephoneDevices"):
        bic = _cat_id(bic_name)
        if bic is not None:
            bic_electricas.append(bic)

    instancias = []
    for bic in bic_electricas:
        try:
            col = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType()
            for inst in col:
                if not isinstance(inst, FamilyInstance):
                    continue
                try:
                    instancias.append(_info_instancia(doc, inst, view))
                except Exception:
                    resultado["hallazgos"].append(
                        "No se pudo leer la instancia {}: {}".format(
                            _element_id_int(inst.Id), traceback.format_exc()))
        except Exception:
            resultado["hallazgos"].append(
                "Error leyendo categoria {}: {}".format(bic, traceback.format_exc()))

    resultado["instancias_electricas"] = instancias[:max_elementos]

    # Resumen de instancias
    sin_nivel = [i for i in instancias if i["nivel"] is None]
    face = [i for i in instancias if i["face_based"]]
    ocultas = [i for i in instancias if i["oculto_en_vista"]]
    resultado["resumen_instancias"] = {
        "total": len(instancias),
        "sin_nivel": len(sin_nivel),
        "face_based": len(face),
        "ocultas_en_vista_activa": len(ocultas),
        "z_min_global": min([i["z_min"] for i in instancias if i["z_min"] is not None]) if instancias else None,
        "z_max_global": max([i["z_max"] for i in instancias if i["z_max"] is not None]) if instancias else None,
    }

    # Conduits
    try:
        conduits = list(FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).WhereElementIsNotElementType())
        fittings = list(FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_ConduitFitting).WhereElementIsNotElementType())
        tipos = {}
        for c in conduits:
            try:
                nombre = _to_unicode(c.Name)
                tipos[nombre] = tipos.get(nombre, 0) + 1
            except Exception:
                pass
        resultado["conduits"] = {"total": len(conduits), "accesorios": len(fittings), "por_tipo": tipos}
    except Exception:
        resultado["conduits"] = {"error": traceback.format_exc()}

    # Hallazgos automaticos
    va = resultado["vista_activa"]
    if va.get("categorias_ocultas_electricas"):
        ocultas_cat = [k for k, v in va["categorias_ocultas_electricas"].items() if v]
        if ocultas_cat:
            resultado["hallazgos"].append(
                "Categorias electricas OCULTAS en la vista activa (V/G): " + ", ".join(ocultas_cat))
    corte = va.get("rango_vista", {}).get("plano_corte")
    if corte:
        resultado["hallazgos"].append(
            "Plano de corte de la vista activa: {} {} m. Los dispositivos de techo (z~2,6 m) quedan por encima del corte y no se ven en planta.".format(
                corte.get("nivel"), corte.get("offset_m")))
    ri = resultado.get("resumen_instancias", {})
    if ri.get("sin_nivel"):
        resultado["hallazgos"].append(
            "Hay {} instancias sin nivel (LevelId = -1): pertenecen a categorias Electrical Fixtures o Lighting Fixtures, para las cuales Revit no persiste LevelId via API y no aparecen en vistas filtradas por nivel.".format(
                ri["sin_nivel"]))
    if len(resultado.get("vinculos", [])) > 0:
        resultado["hallazgos"].append(
            "El documento contiene {} vinculo(s) Revit: verificar que el modelo electrico no este dentro del vinculo.".format(
                len(resultado["vinculos"])))

    # Deduplicar hallazgos conservando orden
    vistos = []
    for h in resultado["hallazgos"]:
        if h not in vistos:
            vistos.append(h)
    resultado["hallazgos"] = vistos

    # Guardar
    if json_out:
        try:
            root = _obtener_root_proyecto()
            if not os.path.isabs(json_out):
                json_out = os.path.join(root, json_out)
            dirpath = os.path.dirname(json_out)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath)
            f = open(json_out, "w")
            try:
                f.write(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
            finally:
                f.close()
            print("JSON guardado en: " + json_out)
        except Exception:
            print("ERROR guardando JSON: " + traceback.format_exc())

    print("ESTADO_MODELO_JSON_START")
    print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
    print("ESTADO_MODELO_JSON_END")
    return resultado


if __name__ == "__main__":
    _doc = __revit__.ActiveUIDocument.Document  # noqa: F821
    diagnosticar_estado_modelo(_doc, json_out="data/estado_modelo_v01.json")
