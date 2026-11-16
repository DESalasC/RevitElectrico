# -*- coding: utf-8 -*-
# RE_F0_CENSO_BENCHMARK_v01.py
# F0 - Verificacion del documento benchmark (CENTRA_V02-f.rvt).
#
# Para que sirve: el plan asume que V02-f contiene dos apartamentos modelados a mano
# con ruteo de tuberia, y que sirve como verdad de referencia. Ese supuesto nunca se
# ha medido. Este script lo convierte en datos, sin modificar nada:
#
#   Bloque A - identidad del documento (titulo, ruta, estado de modificacion)
#   Bloque B - censo: niveles, categorias, dispositivos electricos, conduits, paneles
#   Bloque C - lote E06 de v13 por UniqueId (misma comprobacion que el verificador v02)
#
# SOLO LECTURA: no crea, no mueve, no borra, no abre transacciones.
#
# ADVERTENCIA: si el operador guarda el documento despues de correr esto, el hash del
# benchmark deja de coincidir con data/baseline_hashes.json y la referencia se invalida.
# El script avisa si el documento ya tiene cambios sin guardar.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_F0_CENSO_BENCHMARK_v01.py")
#   censo_benchmark(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
import json
import os
import time

FEET_PER_METER = 3.280839895

REPORTE_V13_RELATIVO = os.path.join("data", "colocar_dispositivos_E06_v13_resultado.json")
SALIDA_RELATIVA = os.path.join("data", "censo_benchmark_v01.json")

# Categorias que cuentan como "electricas" para el resumen (coincidencia por nombre).
CLAVES_ELECTRICAS = ("lighting", "electrical", "communication", "data", "switch", "device")

# Familias de conduit: se detectan por categoria, no por nombre de familia.
TOP_FAMILIAS = 40
TOP_CATEGORIAS = 30


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return str(eid)


def _m(ft):
    return ft / FEET_PER_METER


def _raiz():
    return os.environ.get("REVITELECTRICO_ROOT")


def _ruta(relativa, explicita):
    if explicita:
        return explicita
    raiz = _raiz()
    if raiz:
        return os.path.join(raiz, relativa)
    return None


def _nombre_categoria(elemento):
    try:
        cat = elemento.Category
        if cat is not None:
            return cat.Name
    except Exception:
        pass
    return "SinCategoria"


def _es_electrica(nombre_categoria):
    bajo = nombre_categoria.lower()
    for clave in CLAVES_ELECTRICAS:
        if clave in bajo:
            return True
    return False


def _familia_y_tipo(inst):
    familia = "Desconocida"
    tipo = "Desconocido"
    try:
        familia = inst.Symbol.Family.Name
    except Exception:
        pass
    try:
        tipo = inst.Name
    except Exception:
        pass
    return familia, tipo


def _xy_m(inst):
    try:
        loc = inst.Location
        if loc is not None and hasattr(loc, "Point"):
            return (_m(loc.Point.X), _m(loc.Point.Y), _m(loc.Point.Z))
    except Exception:
        pass
    return None


def _longitud_m(elemento):
    """Longitud de un elemento basado en curva (conduit), en metros."""
    try:
        loc = elemento.Location
        if loc is not None and hasattr(loc, "Curve"):
            curva = loc.Curve
            if curva is not None:
                return _m(curva.Length)
    except Exception:
        pass
    return None


def censo_niveles(doc):
    niveles = []
    for nivel in FilteredElementCollector(doc).OfClass(Level):
        try:
            niveles.append({
                "nombre": nivel.Name,
                "elevacion_m": round(_m(nivel.Elevation), 4),
            })
        except Exception:
            continue
    niveles.sort(key=lambda n: n["elevacion_m"])
    return niveles


def censo_family_instances(doc):
    """Recorre una sola vez todas las FamilyInstance y agrega por categoria y familia."""
    por_categoria = {}
    por_familia = {}
    electricas = 0
    total = 0
    xy_min = None
    xy_max = None

    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        total += 1
        cat = _nombre_categoria(inst)
        por_categoria[cat] = por_categoria.get(cat, 0) + 1

        familia, tipo = _familia_y_tipo(inst)
        clave = familia + "|" + tipo
        por_familia[clave] = por_familia.get(clave, 0) + 1

        if _es_electrica(cat):
            electricas += 1
            p = _xy_m(inst)
            if p is not None:
                x, y = p[0], p[1]
                if xy_min is None:
                    xy_min = [x, y]
                    xy_max = [x, y]
                else:
                    xy_min[0] = min(xy_min[0], x)
                    xy_min[1] = min(xy_min[1], y)
                    xy_max[0] = max(xy_max[0], x)
                    xy_max[1] = max(xy_max[1], y)

    categorias = sorted(por_categoria.items(), key=lambda kv: -kv[1])[:TOP_CATEGORIAS]
    familias = sorted(por_familia.items(), key=lambda kv: -kv[1])[:TOP_FAMILIAS]

    return {
        "total_family_instances": total,
        "total_electricas": electricas,
        "por_categoria": [{"categoria": k, "n": v} for k, v in categorias],
        "por_familia_tipo": [
            {"familia": k.split("|")[0], "tipo": k.split("|")[1], "n": v} for k, v in familias
        ],
        "rango_xy_electricas_m": {"min": xy_min, "max": xy_max} if xy_min else None,
    }


def censo_conduits(doc):
    """Cuenta conduits por tipo y suma longitud, usando la categoria OST_Conduit."""
    total = 0
    con_longitud = 0
    longitud_total = 0.0
    por_tipo = {}

    try:
        filtro = ElementCategoryFilter(BuiltInCategory.OST_Conduit)
        for elemento in FilteredElementCollector(doc).WherePasses(filtro).WhereElementIsNotElementType():
            total += 1
            nombre_tipo = "Desconocido"
            try:
                nombre_tipo = elemento.Name
            except Exception:
                pass
            por_tipo[nombre_tipo] = por_tipo.get(nombre_tipo, 0) + 1
            largo = _longitud_m(elemento)
            if largo is not None:
                con_longitud += 1
                longitud_total += largo
    except Exception as exc:
        return {"error": str(exc), "total": total, "por_tipo": [], "longitud_total_m": None}

    tipos = sorted(por_tipo.items(), key=lambda kv: -kv[1])
    return {
        "total": total,
        "con_longitud_medible": con_longitud,
        "longitud_total_m": round(longitud_total, 3),
        "por_tipo": [{"tipo": k, "n": v} for k, v in tipos],
    }


def censo_paneles(doc):
    """Lista los paneles de distribucion con su posicion, si existen."""
    paneles = []
    try:
        filtro = ElementCategoryFilter(BuiltInCategory.OST_ElectricalEquipment)
        for elemento in FilteredElementCollector(doc).WherePasses(filtro).WhereElementIsNotElementType():
            familia, tipo = _familia_y_tipo(elemento)
            p = _xy_m(elemento)
            paneles.append({
                "id": _eid(elemento.Id),
                "familia": familia,
                "tipo": tipo,
                "x_m": round(p[0], 3) if p else None,
                "y_m": round(p[1], 3) if p else None,
                "z_m": round(p[2], 4) if p else None,
            })
    except Exception:
        pass
    return paneles


def lote_v13(doc, ruta_reporte):
    """Comprueba por UniqueId si el lote de v13 vive en este documento."""
    if not ruta_reporte or not os.path.exists(ruta_reporte):
        return {"estado": "sin_reporte", "declarados": 0, "encontrados": 0}
    try:
        with open(ruta_reporte, "r") as fh:
            datos = json.load(fh)
    except Exception as exc:
        return {"estado": "reporte_ilegible", "detalle": str(exc), "declarados": 0, "encontrados": 0}

    detalle = datos.get("detalle") or []
    declarados = 0
    encontrados = 0
    for item in detalle:
        if item.get("accion") != "creado":
            continue
        uid = item.get("unique_id")
        if not uid:
            continue
        declarados += 1
        try:
            if doc.GetElement(uid) is not None:
                encontrados += 1
        except Exception:
            pass

    if declarados == 0:
        estado = "sin_datos"
    elif encontrados == 0:
        estado = "no_persistido"
    elif encontrados == declarados:
        estado = "persistido"
    else:
        estado = "parcial"
    return {
        "estado": estado,
        "lote_guid": datos.get("lote_guid"),
        "declarados": declarados,
        "encontrados": encontrados,
    }


def evaluar_benchmark(censo, conduits):
    """Veredicto sobre si el benchmark contiene lo que el plan asume."""
    if censo["total_family_instances"] == 0:
        return "vacio", "El documento no contiene FamilyInstances."
    if censo["total_electricas"] == 0:
        return "sin_electricas", "Hay geometria pero ninguna FamilyInstance de categoria electrica."
    if conduits.get("total", 0) == 0:
        return "sin_ruteo", "Hay dispositivos electricos pero no se encontraron conduits en la categoria OST_Conduit."
    return "con_ruteo", "Hay {d} dispositivos electricos y {c} conduits ({l} m): el benchmark si contiene aparatos y ruteo.".format(
        d=censo["total_electricas"], c=conduits.get("total", 0), l=conduits.get("longitud_total_m"))


def censo_benchmark(doc, salida_json=None, reporte_json=None):
    """Ejecuta el censo completo y escribe el JSON. Solo lectura."""
    ruta_salida = _ruta(SALIDA_RELATIVA, salida_json)
    ruta_reporte = _ruta(REPORTE_V13_RELATIVO, reporte_json)
    if ruta_salida is None:
        print("ERROR: falta REVITELECTRICO_ROOT. Pasa salida_json explicita.")
        return {"error": "salida_no_definida"}

    print("=== F0 - CENSO DEL BENCHMARK ===")
    print("Documento: {t}".format(t=doc.Title))
    print("Modo     : SOLO LECTURA")

    # --- Bloque A: identidad ---
    ruta_doc = ""
    modificado = None
    try:
        ruta_doc = doc.PathName
    except Exception:
        pass
    try:
        modificado = bool(doc.IsModified)
    except Exception:
        modificado = None

    print("\n--- A. Identidad ---")
    print("Ruta     : {r}".format(r=ruta_doc))
    print("Modificado en esta sesion: {m}".format(m=modificado))
    if modificado:
        print("  AVISO: el documento tiene cambios sin guardar. NO guardar: invalida el hash del benchmark.")

    # --- Bloque B: censo ---
    niveles = censo_niveles(doc)
    censo = censo_family_instances(doc)
    conduits = censo_conduits(doc)
    paneles = censo_paneles(doc)
    veredicto, motivo = evaluar_benchmark(censo, conduits)

    print("\n--- B. Censo ---")
    print("Niveles              : {n}".format(n=len(niveles)))
    print("FamilyInstances      : {n}".format(n=censo["total_family_instances"]))
    print("  de categoria electrica: {n}".format(n=censo["total_electricas"]))
    print("Conduits             : {n}  ({l} m)".format(
        n=conduits.get("total", 0), l=conduits.get("longitud_total_m")))
    print("Paneles              : {n}".format(n=len(paneles)))
    print("Veredicto            : {v}".format(v=veredicto))
    print("Motivo               : {m}".format(m=motivo))

    if censo["rango_xy_electricas_m"]:
        r = censo["rango_xy_electricas_m"]
        print("Rango XY electricas  : ({a}, {b}) .. ({c}, {d}) m".format(
            a=round(r["min"][0], 2), b=round(r["min"][1], 2),
            c=round(r["max"][0], 2), d=round(r["max"][1], 2)))

    # --- Bloque C: lote v13 ---
    lote = lote_v13(doc, ruta_reporte)
    print("\n--- C. Lote E06 de v13 ---")
    print("Estado    : {e}".format(e=lote.get("estado")))
    print("Declarados: {d} · Encontrados: {f}".format(
        d=lote.get("declarados"), f=lote.get("encontrados")))

    resumen = {
        "version": "1.0",
        "proyecto": "RE",
        "fase": "F0",
        "documento": doc.Title,
        "ruta": ruta_doc,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "modificado_en_sesion": modificado,
        "censo": {
            "niveles": niveles,
            "family_instances": censo,
            "conduits": conduits,
            "paneles": paneles,
        },
        "lote_v13": lote,
        "veredicto_benchmark": veredicto,
        "motivo": motivo,
    }

    directorio = os.path.dirname(ruta_salida)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(ruta_salida, "w") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2, sort_keys=True)

    print("\nJSON guardado en: {r}".format(r=ruta_salida))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        censo_benchmark(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
