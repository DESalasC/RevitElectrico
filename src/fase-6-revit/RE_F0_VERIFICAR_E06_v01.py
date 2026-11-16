# -*- coding: utf-8 -*-
# RE_F0_VERIFICAR_E06_v01.py
# F0 - Veredicto del lote de dispositivos E06 (RE-P-051).
#
# SOLO LECTURA: no crea, no mueve, no borra y no abre ninguna transaccion.
#
# Busca en el documento activo las FamilyInstance vinculadas al lote GUID
# declarado (parametro de lote o, si no esta vinculado, el parametro Comments)
# y emite un veredicto explicito: conservar / descartar / revisar / no_encontrado.
# No se inventa un veredicto si no hay evidencia.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_F0_VERIFICAR_E06_v01.py")
#   verificar_e06(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
import json
import os
import time

FEET_PER_METER = 3.280839895

GUID_LOTE = "46c3f138-025d-47d4-b24a-41cd21181a58"
NIVEL_ESPERADO_M = 13.22
Z_TECHO_ESPERADA_M = 15.82
Z_MURO_RANGO_M = (13.30, 14.45)   # 13.22 + 0.30 .. 13.22 + 1.10 (+margen)
UMBRAL_TECHO_M = 2.0

SALIDA_POR_DEFECTO = None  # se resuelve desde $REVITELECTRICO_ROOT (regla 7: sin rutas absolutas)


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _m(ft):
    return ft / FEET_PER_METER


def _texto_param(parametro):
    """Devuelve el valor del parametro como texto, o None si no es textual."""
    try:
        valor = parametro.AsString()
        if valor is not None:
            return valor
    except Exception:
        pass
    try:
        valor = parametro.AsValueString()
        if valor is not None:
            return valor
    except Exception:
        pass
    return None


def _nombre_parametro(parametro):
    try:
        definicion = parametro.Definition
        if definicion is None:
            return ""
        return definicion.Name or ""
    except Exception:
        return ""


def _nivel_nombre(doc, inst):
    """Nombre del nivel: primero Schedule Level, luego LevelId."""
    try:
        p = inst.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
        if p is not None:
            nivel = doc.GetElement(p.AsElementId())
            if nivel is not None:
                return nivel.Name
    except Exception:
        pass
    try:
        lid = inst.LevelId
        if lid is not None and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel is not None:
                return nivel.Name
    except Exception:
        pass
    return "SinNivel"


def _z_absoluta_m(inst):
    try:
        loc = inst.Location
        if loc is not None and hasattr(loc, "Point"):
            return round(_m(loc.Point.Z), 4)
    except Exception:
        pass
    return None


def _host_id(inst):
    try:
        host = inst.Host
        if host is not None:
            return _eid(host.Id)
    except Exception:
        pass
    return None


def _familia(inst):
    try:
        return inst.Symbol.Family.Name
    except Exception:
        return "Desconocida"


def _tipo(inst):
    try:
        return inst.Name
    except Exception:
        return "Desconocido"


def buscar_lote(doc, guid):
    """Recorre FamilyInstance y devuelve las que referencian el GUID del lote."""
    encontradas = []
    revisadas = 0
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        revisadas += 1
        try:
            tiene_lote = False
            origen = None
            for p in inst.Parameters:
                texto = _texto_param(p)
                if texto is None:
                    continue
                if guid not in texto:
                    continue
                nombre = _nombre_parametro(p)
                if "lote" in nombre.lower():
                    tiene_lote = True
                    origen = "parametro_lote:" + nombre
                    break
                if "comment" in nombre.lower():
                    tiene_lote = True
                    origen = "comments"
                    break
            if not tiene_lote:
                continue
            encontradas.append({
                "element_id": _eid(inst.Id),
                "unique_id": str(inst.UniqueId),
                "familia": _familia(inst),
                "tipo": _tipo(inst),
                "nivel": _nivel_nombre(doc, inst),
                "z_m": _z_absoluta_m(inst),
                "host_id": _host_id(inst),
                "origen_deteccion": origen,
            })
        except Exception:
            continue
    return encontradas, revisadas


def evaluar_veredicto(instancias):
    """Emite veredicto basado en evidencia de posicion, sin suponer."""
    total = len(instancias)
    if total == 0:
        return "no_encontrado", "No hay instancias con el GUID del lote en el documento."

    z_validas = [i["z_m"] for i in instancias if i["z_m"] is not None]
    if not z_validas:
        return "revisar", "Hay instancias con el lote pero ninguna reporta Z; no se puede evaluar."

    z_min = min(z_validas)
    z_max = max(z_validas)

    if z_max < UMBRAL_TECHO_M:
        return "descartar", "Todas las instancias estan por debajo de {u} m: quedaron en el nivel base.".format(u=UMBRAL_TECHO_M)

    en_rango = [z for z in z_validas if Z_MURO_RANGO_M[0] <= z <= Z_MURO_RANGO_M[1] or z >= Z_TECHO_ESPERADA_M - 0.10]
    proporcion = float(len(en_rango)) / float(len(z_validas))

    if proporcion >= 0.95:
        return "conservar", "El {p:.0f}% de las instancias esta en el rango de altura esperado (Z {a}..{b} m).".format(
            p=proporcion * 100.0, a=round(z_min, 2), b=round(z_max, 2))
    if proporcion <= 0.50:
        return "descartar", "Solo el {p:.0f}% de las instancias esta en el rango esperado; el lote no es confiable.".format(
            p=proporcion * 100.0)
    return "revisar", "El {p:.0f}% de las instancias esta en rango; se requiere revision del operador.".format(
        p=proporcion * 100.0)


def guardar_json(ruta, datos):
    directorio = os.path.dirname(ruta)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(ruta, "w") as fh:
        json.dump(datos, fh, ensure_ascii=True, indent=2, sort_keys=True)


def resolver_salida(salida_json):
    """Resuelve la ruta de salida: la indicada o $REVITELECTRICO_ROOT/data/veredicto_e06_v01.json."""
    if salida_json:
        return salida_json
    raiz = os.environ.get("REVITELECTRICO_ROOT")
    if raiz:
        return os.path.join(raiz, "data", "veredicto_e06_v01.json")
    return None


def verificar_e06(doc, salida_json=None, guid_lote=None):
    """Busca el lote E06 en el documento activo y escribe el veredicto. Solo lectura."""
    salida_json = resolver_salida(salida_json)
    if salida_json is None:
        print("ERROR: falta --salida. Define REVITELECTRICO_ROOT o pasa salida_json explicita:")
        print("  verificar_e06(doc, salida_json=r'<ruta>\\veredicto_e06_v01.json')")
        return {"error": "salida_no_definida"}
    if guid_lote is None:
        guid_lote = GUID_LOTE

    print("=== F0 - VERIFICAR E06 (RE-P-051) ===")
    print("Documento: {t}".format(t=doc.Title))
    print("Lote GUID: {g}".format(g=guid_lote))
    print("Modo: SOLO LECTURA")

    instancias, revisadas = buscar_lote(doc, guid_lote)
    veredicto, motivo = evaluar_veredicto(instancias)

    z_validas = [i["z_m"] for i in instancias if i["z_m"] is not None]
    resumen = {
        "version": "1.0",
        "proyecto": "RE",
        "fase": "F0",
        "pendiente": "RE-P-051",
        "documento": doc.Title,
        "guid_lote": guid_lote,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "instancias_revisadas": revisadas,
        "instancias_del_lote": len(instancias),
        "veredicto": veredicto,
        "motivo": motivo,
        "z_min_m": round(min(z_validas), 4) if z_validas else None,
        "z_max_m": round(max(z_validas), 4) if z_validas else None,
        "niveles": sorted(set([i["nivel"] for i in instancias])),
        "detalle": instancias,
    }

    print("FamilyInstances revisadas: {n}".format(n=revisadas))
    print("Instancias del lote      : {n}".format(n=len(instancias)))
    if z_validas:
        print("Z medida                 : {a} .. {b} m".format(a=round(min(z_validas), 3), b=round(max(z_validas), 3)))
    print("Veredicto                : {v}".format(v=veredicto))
    print("Motivo                   : {m}".format(m=motivo))

    guardar_json(salida_json, resumen)
    print("JSON guardado en: {r}".format(r=salida_json))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        verificar_e06(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
