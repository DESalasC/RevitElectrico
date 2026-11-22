# -*- coding: utf-8 -*-
"""
RE7_CREAR_UNIONES_CAJAS_v01.py — Crea uniones/cajas de empate (conduit fittings)
en los puntos de conexión detectados entre conductos existentes en Revit.

Lee el reporte de uniones detectadas por RE7_ANALIZAR_UNIONES_v01 y, para cada
punto de unión, coloca una instancia de familia de accesorio de conduit
(Conduit Coupling, Conduit Elbow, Conduit Junction Box Tee/Cross) en el punto
central del cluster, intentando conectar los conectores de los conductos
implicados.

Familias usadas (deben estar cargadas en CENTRAL-V01):
  - Conduit Coupling         -> "Conduit Coupling - PVC"
  - Conduit Elbow            -> "Conduit Elbow - Steel"
  - Conduit Junction Box Tee -> "Conduit Junction Box - Tee - PVC"
  - Conduit Junction Box Cross -> "Conduit Junction Box - Cross - PVC"

USO (desde pyRevit Python Shell dentro de Revit 2026):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_CREAR_UNIONES_CAJAS_v01.py").read())
  crear_uniones_cajas(doc, json_path="data/f7_uniones_detectadas_v01.json",
                      primeros=0, solo_primeros=False)

Parametros:
  doc             : Document de Revit (obligatorio)
  json_path       : Ruta al JSON de uniones detectadas (relativo al proyecto o absoluto)
  primeros        : Si >0, solo procesar uniones que involucren al menos uno
                    de los primeros N conduits (por ID ascendente). Sirve para
                    piloto sobre las primeras tuberías creadas.
  solo_primeros   : Si True, solo procesar uniones donde TODOS los conduits
                    del punto estén entre los primeros N.

Devuelve: dict con resumen de creaciones (ok, fallidos, saltados).
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilySymbol,
    FamilyInstance,
    Transaction,
    ElementId,
    BuiltInCategory,
    XYZ,
    Level,
    Structure,
    ConnectorSet,
    Connector,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

import json
import os
import sys
from datetime import datetime

FT_A_MM = 304.8  # pies a milímetros


def _raiz_proyecto():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return r"D:\Work\PROJECTS\RevitElectrico"


def _resolver_ruta(p):
    p = p.strip()
    if os.path.isabs(p):
        return p
    return os.path.join(_raiz_proyecto(), p)


def _mm_a_pie(mm):
    """Convierte milímetros a pies (unidad interna de Revit)."""
    return mm / FT_A_MM


def _punto_revit(x_mm, y_mm, z_mm):
    """Crea un XYZ de Revit a partir de coordenadas en milímetros."""
    return XYZ(_mm_a_pie(x_mm), _mm_a_pie(y_mm), _mm_a_pie(z_mm))


def _buscar_simbolo_familia(doc, nombre_familia, nombre_tipo=None):
    """Busca un FamilySymbol por nombre de familia y opcionalmente por nombre de tipo.

    Retorna el primer FamilySymbol que coincida, o None si no se encuentra.
    """
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    for fs in collector:
        try:
            nombre_fam = fs.Family.Name
        except Exception:
            continue
        if nombre_familia.lower() not in nombre_fam.lower():
            continue
        if nombre_tipo is not None:
            try:
                nombre_sym = fs.Name
            except Exception:
                nombre_sym = ""
            if nombre_tipo.lower() not in nombre_sym.lower():
                continue
        return fs
    return None


def _mapeo_tipo_a_familia(tipo_accesorio):
    """Mapea el tipo de accesorio recomendado a un patrón de nombre de familia Revit.

    Los nombres de familia son los reales de CENTRA_V02-f (modelo de referencia
    validado), no nombres genéricos en inglés.
    """
    mapeo = {
        "Conduit Coupling": ("M_Casquillo reductor de tubo - PVC", None),
        "Conduit Elbow": ("M_Codo de tubo - Extremo abocardado - PVC", None),
        "Conduit Junction Box - Tee": ("M_Caja de conexiones de tubo - Te - PVC", None),
        "Conduit Junction Box - Cross": ("M_Caja de conexiones de tubo - Cruz - PVC", None),
    }
    return mapeo.get(tipo_accesorio, (None, None))


def _obtener_conductos_en_punto(doc, conduit_ids):
    """Obtiene los elementos Conduit de Revit por sus IDs (enteros)."""
    conductos = []
    for cid in conduit_ids:
        try:
            eid = ElementId(Int64(int(cid)))
            elem = doc.GetElement(eid)
            if elem is not None and isinstance(elem, Conduit):
                conductos.append(elem)
        except Exception:
            continue
    return conductos


def _conectar_conductos_al_accesorio(doc, accesorio, conductos):
    """Intenta conectar los conectores de los conductos al accesorio colocado.

    Para cada conducto, busca el conector más cercano al punto del accesorio
    e intenta ConnectTo con un conector libre del accesorio.
    """
    conectados = 0
    if accesorio is None:
        return conectados

    try:
        mep_model = accesorio.MEPModel
        if mep_model is None:
            return conectados
        conectores_accesorio = list(mep_model.ConnectorSet)
    except Exception:
        conectores_accesorio = []

    for cond in conductos:
        try:
            cm = cond.ConnectorManager
            if cm is None:
                continue
            conectores_cond = list(cm.Connectors)
        except Exception:
            continue

        # Obtener la ubicación del conducto para encontrar el conector más cercano
        try:
            loc = cond.Location
            if loc is None:
                continue
            punto_cond = None
            if hasattr(loc, "Point") and loc.Point is not None:
                punto_cond = loc.Point
            elif hasattr(loc, "Curve") and loc.Curve is not None:
                # Tomar el punto medio de la curva
                curva = loc.Curve
                punto_cond = curva.Evaluate(0.5, True)
            else:
                continue
        except Exception:
            continue

        # Encontrar el conector del conducto más cercano al accesorio
        punto_acc = None
        try:
            punto_acc = accesorio.Location.Point
        except Exception:
            pass

        mejor_conector = None
        mejor_dist = float("inf")
        for cn in conectores_cond:
            try:
                origen = cn.Origin
                if punto_acc is not None:
                    d = punto_acc.DistanceTo(origen)
                else:
                    d = punto_cond.DistanceTo(origen)
                if d < mejor_dist:
                    mejor_dist = d
                    mejor_conector = cn
            except Exception:
                continue

        if mejor_conector is None:
            continue

        # Intentar conectar con un conector libre del accesorio
        for cn_acc in conectores_accesorio:
            try:
                if cn_acc.IsConnected:
                    continue
                mejor_conector.ConnectTo(cn_acc)
                conectados += 1
                break
            except Exception:
                continue

    return conectados


def _tipo_accesorio_a_categoria(tipo_accesorio):
    """Devuelve la BuiltInCategory del accesorio."""
    if "Coupling" in tipo_accesorio:
        return BuiltInCategory.OST_ConduitFitting
    if "Elbow" in tipo_accesorio:
        return BuiltInCategory.OST_ConduitFitting
    if "Junction Box" in tipo_accesorio:
        return BuiltInCategory.OST_ConduitFitting
    return BuiltInCategory.OST_ConduitFitting


def crear_uniones_cajas(doc, json_path="data/f7_uniones_detectadas_v01.json",
                        primeros=0, solo_primeros=False):
    """Crea uniones/cajas de empate en los puntos de conexión detectados.

    Args:
        doc: Document de Revit.
        json_path: Ruta al JSON de uniones detectadas.
        primeros: Si >0, filtrar por los primeros N conduits (por ID).
        solo_primeros: Si True, requiere que TODOS los conduits del punto
                       estén entre los primeros N.

    Returns:
        dict con claves: ok, fallidos, saltados, total, detalles.
    """
    ruta_json = _resolver_ruta(json_path)
    if not os.path.exists(ruta_json):
        raise IOError("No existe el archivo JSON: {}".format(ruta_json))

    with open(ruta_json, "r") as f:
        reporte = json.load(f)

    puntos_union = reporte.get("puntos_union", [])
    if not puntos_union:
        print("RE7_CREAR_UNIONES_CAJAS_v01: no hay puntos de unión en el JSON.")
        return {"ok": 0, "fallidos": 0, "saltados": 0, "total": 0, "detalles": []}

    # Filtrar por primeros conduits si se solicita
    puntos_a_procesar = []
    ids_primeros = set()
    if primeros and primeros > 0:
        # Obtener los IDs de los primeros N conduits ordenados ascendente
        # Los IDs están en los puntos de unión; los ordenamos y tomamos los primeros N
        todos_ids = sorted(set(
            cid for p in puntos_union for cid in p["conduit_ids"]
        ))
        ids_primeros = set(todos_ids[:primeros])

    for p in puntos_union:
        ids = p["conduit_ids"]
        if primeros and primeros > 0:
            if solo_primeros:
                if not all(cid in ids_primeros for cid in ids):
                    continue
            else:
                if not any(cid in ids_primeros for cid in ids):
                    continue
        puntos_a_procesar.append(p)

    print("=" * 60)
    print("RE7_CREAR_UNIONES_CAJAS_v01 - Creación de uniones/cajas de empate")
    print("ejecutado_utc={}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)
    print("Puntos de unión en JSON: {}".format(len(puntos_union)))
    print("Puntos a procesar: {}".format(len(puntos_a_procesar)))
    if primeros:
        print("Filtro primeros {} conduit(s): {}".format(primeros, "solo_primeros={}".format(solo_primeros)))
    print("")

    resultados = {"ok": 0, "fallidos": 0, "saltados": 0, "total": len(puntos_a_procesar), "detalles": []}

    t = Transaction(doc, "RE7 Crear uniones y cajas de empate")
    t.Start()

    try:
        for idx, p in enumerate(puntos_a_procesar):
            punto_mm = p["punto_mm"]
            ids_conduits = p["conduit_ids"]
            tipo_accesorio = p["tipo_accesorio_recomendado"]
            num_conduits = p["num_conduits"]

            # Mapear tipo a familia
            patron_familia, nombre_tipo = _mapeo_tipo_a_familia(tipo_accesorio)
            if patron_familia is None:
                resultados["saltados"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "saltado",
                    "motivo": "tipo de accesorio no mapeado",
                })
                continue

            # Buscar símbolo de familia
            simbolo = _buscar_simbolo_familia(doc, patron_familia, nombre_tipo)
            if simbolo is None:
                resultados["fallidos"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "fallido",
                    "motivo": "familia no encontrada: {}".format(patron_familia),
                })
                continue

            # Activar símbolo si es necesario
            try:
                if not simbolo.IsActive:
                    simbolo.Activate()
            except Exception:
                pass

            # Obtener nivel del documento (primer nivel disponible)
            nivel = None
            try:
                nivel_collector = FilteredElementCollector(doc).OfClass(Level)
                for lv in nivel_collector:
                    nivel = lv
                    break
            except Exception:
                pass

            # Crear el punto XYZ en Revit
            xyz = _punto_revit(punto_mm[0], punto_mm[1], punto_mm[2])

            # Colocar FamilyInstance
            simbolo_nombre = simbolo.Name if simbolo else None
            familia_nombre = simbolo.Family.Name if simbolo else None
            try:
                if nivel is not None:
                    instancia = doc.Create.NewFamilyInstance(xyz, simbolo, nivel,
                                                             Structure.StructuralType.NonStructural)
                else:
                    instancia = doc.Create.NewFamilyInstance(xyz, simbolo,
                                                             Structure.StructuralType.NonStructural)
            except Exception as ex:
                resultados["fallidos"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "fallido",
                    "motivo": "error al crear instancia: {}".format(str(ex)),
                    "familia": familia_nombre,
                    "simbolo": simbolo_nombre,
                })
                continue

            # Obtener los elementos Conduit de Revit y tratar de conectar
            conductos = _obtener_conductos_en_punto(doc, ids_conduits)
            conectados = 0
            if conductos:
                try:
                    conectados = _conectar_conductos_al_accesorio(doc, instancia, conductos)
                except Exception:
                    conectados = 0

            resultados["ok"] += 1
            resultados["detalles"].append({
                "punto": punto_mm,
                "tipo": tipo_accesorio,
                "estado": "ok",
                "conduit_ids": ids_conduits,
                "conectores_conectados": conectados,
                "familia": simbolo.Family.Name if simbolo else None,
                "simbolo": simbolo.Name if simbolo else None,
            })

            if (idx + 1) % 10 == 0:
                print("  Procesados {}/{}...".format(idx + 1, len(puntos_a_procesar)))

    except Exception as ex:
        t.RollBack()
        print("ERROR: transacción revertida: {}".format(str(ex)))
        raise

    t.Commit()

    print("")
    print("RESULTADOS:")
    print("  OK:       {}".format(resultados["ok"]))
    print("  Fallidos: {}".format(resultados["fallidos"]))
    print("  Saltados: {}".format(resultados["saltados"]))
    print("  Total:    {}".format(resultados["total"]))
    print("")
    # Mostrar detalles de fallos y saltos
    if resultados["fallidos"] > 0 or resultados["saltados"] > 0:
        print("DETALLES DE FALLOS / SALTOS:")
        for d in resultados["detalles"]:
            if d["estado"] in ("fallido", "saltado"):
                print("  punto={} tipo={} estado={} motivo={} familia={} simbolo={}".format(
                    d["punto"], d["tipo"], d["estado"], d.get("motivo", ""),
                    d.get("familia", ""), d.get("simbolo", "")))
    print("=" * 60)

    return resultados


def diagnosticar_familias_conduit(doc):
    """Lista todas las familias y símbolos de conduit cargados en el modelo.

    Útil para verificar los nombres exactos de familia antes de ejecutar
    crear_uniones_cajas.
    """
    print("=" * 60)
    print("DIAGNOSTICO: Familias de conduit cargadas en el modelo")
    print("=" * 60)
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    encontrados = []
    for fs in collector:
        try:
            nom_fam = fs.Family.Name
        except Exception:
            continue
        if "conduit" in nom_fam.lower():
            encontrados.append((nom_fam, fs.Name))
    if not encontrados:
        print("  No se encontraron familias con 'conduit' en el nombre.")
    else:
        for nom_fam, nom_sym in sorted(encontrados):
            print("  Familia: {:<45} | Tipo: {}".format(nom_fam, nom_sym))
    print("=" * 60)
    return encontrados


# Si se ejecuta directamente en pyRevit sin pasar doc, intentar obtenerlo de __revit__
if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        diagnosticar_familias_conduit(doc)
        resultado = crear_uniones_cajas(doc)
        print("Resumen: {} OK, {} fallidos, {} saltados de {} totales".format(
            resultado["ok"], resultado["fallidos"], resultado["saltados"], resultado["total"]))
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso: exec(open(ruta_script).read())")
        print("     crear_uniones_cajas(doc, json_path=..., primeros=...)")
        print("     diagnosticar_familias_conduit(doc)")

