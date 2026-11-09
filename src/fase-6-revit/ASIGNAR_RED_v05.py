# -*- coding: utf-8 -*-
"""
ASIGNAR_RED_v05.py — Marca dispositivos electricos con RED=SI
usando el parametro de instancia Comments (ya existe en FamilyInstance).
No crea shared parametros. No depende de ElementIds fijos del DXF.

Estrategia escalable (repetible para cualquier piso/bloque):
  1. Lee el JSON de reporte de modelado (tiene x_revit, y_revit, z_revit, capa, nombre_bloque).
  2. Filtra dispositivos de capa 'ELEC-APPL-NETWORD' (red de datos/voz = RED=SI).
  3. Busca en Revit una FamilyInstance cuya Location.Point coincida (tolerancia 0.02 m).
  4. Marca Comments = 'RED=SI' (agrega si ya hay comentario previo).

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r".../src/fase-6-revit/ASIGNAR_RED_v05.py").read()))
  asignar_red(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json", json_out="data\\asignar_red_v05_resultado.json")


Ultimos tres cambios
--------------------
1. 2026-11-08 v05: version vigente conservada tras la limpieza de duplicados;
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
    FamilyInstance,
    BuiltInParameter,
    Transaction,
    XYZ,
)
from System import Int64
import json
import os

VALOR_RED = "SI"
MARCA_COMENTARIO = "RED={}".format(VALOR_RED)
TOLERANCIA_M = 0.02  # metros, tolerancia de coincidencia XYZ
CAPA_RED = "ELEC-APPL-NETWORD"  # capa de dispositivos de red (datos/voz)


def _nombre_elemento_seguro(elemento):
    try:
        n = getattr(elemento, "Name", None)
        if n:
            return n
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


def _comentario_actual(p_comments):
    try:
        if p_comments is None:
            return ""
        v = p_comments.AsString()
        return v if v is not None else ""
    except Exception:
        return ""


def _cargar_reporte(ruta_json):
    """Carga el JSON de reporte de modelado y retorna la lista de acciones."""
    with open(ruta_json, "r") as f:
        datos = json.load(f)
    acciones = datos.get("acciones_modelar", [])
    if not acciones:
        # Soporte para el reporte _resultado.json (clave 'exitos')
        acciones = datos.get("exitos", [])
    return acciones


def _filtrar_dispositivos_red(acciones):
    """Retorna dispositivos de capa RED con sus coordenadas y nombre de bloque."""
    red = []
    for accion in acciones:
        capa = accion.get("capa", "")
        if capa != CAPA_RED:
            continue
        try:
            x = float(accion.get("x_revit", 0))
            y = float(accion.get("y_revit", 0))
            z = float(accion.get("z_revit", 0))
        except (TypeError, ValueError):
            continue
        red.append({
            "nombre_bloque": accion.get("nombre_bloque", ""),
            "orden": accion.get("orden", None),
            "capa": capa,
            "x": x,
            "y": y,
            "z": z,
        })
    return red


def _buscar_instancia_por_posicion(doc, x, y, z, tolerancia=TOLERANCIA_M):
    """Busca una FamilyInstance cuya Location.Point este cerca de (x,y,z)."""
    colector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for inst in colector.ToElements():
        try:
            # OfClass(FamilyInstance) ya garantiza que sea FamilyInstance en Revit.
            # Verificamos que tenga Location con punto valido.
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


def asignar_red(doc, reporte_json=None, json_out=None, capa_red=CAPA_RED):
    """
    Asigna RED=SI al parametro Comments de los dispositivos de red encontrados.

    Parametros:
      doc: Documento de Revit activo.
      reporte_json: Ruta al JSON de reporte de modelado (acciones_modelar).
      json_out: Ruta opcional para guardar el JSON de resultado.
      capa_red: Capa que identifica dispositivos de RED (default ELEC-APPL-NETWORD).
    """
    if reporte_json is None:
        raise ValueError("se requiere reporte_json (ruta al JSON de reporte de modelado)")

    acciones = _cargar_reporte(reporte_json)
    dispositivos = _filtrar_dispositivos_red(acciones)

    trans = Transaction(doc, "ASIGNAR_RED — dispositivos electricos (v05)")
    trans.Start()

    exitos = 0
    fallos = 0
    no_encontrados = 0
    detalle = []

    for disp in dispositivos:
        try:
            inst = _buscar_instancia_por_posicion(doc, disp["x"], disp["y"], disp["z"])
            if inst is None:
                no_encontrados += 1
                fallos += 1
                detalle.append({
                    "nombre_bloque": disp["nombre_bloque"],
                    "orden": disp["orden"],
                    "x": disp["x"],
                    "y": disp["y"],
                    "z": disp["z"],
                    "motivo": "Instancia no encontrada en Revit (posicion no coincide)",
                })
                print("  NO ENCONTRADO {} ({},{})".format(disp["nombre_bloque"], disp["x"], disp["y"]))
                continue

            p_comments = _buscar_param_comments(inst)
            if p_comments is None:
                fallos += 1
                detalle.append({
                    "nombre_bloque": disp["nombre_bloque"],
                    "orden": disp["orden"],
                    "motivo": "Parametro Comments no encontrado",
                })
                print("  FALLO {}: parametro Comments no encontrado".format(disp["nombre_bloque"]))
                continue

            if not p_comments.IsReadOnly:
                try:
                    actual = _comentario_actual(p_comments)
                    if actual and "RED=" not in actual:
                        nuevo = actual + " | " + MARCA_COMENTARIO
                    else:
                        nuevo = MARCA_COMENTARIO
                    p_comments.Set(nuevo)
                    exitos += 1
                    detalle.append({
                        "id": inst.Id.ToString(),
                        "nombre_bloque": disp["nombre_bloque"],
                        "orden": disp["orden"],
                        "x": disp["x"],
                        "y": disp["y"],
                        "z": disp["z"],
                        "motivo": "OK — Comments='{}'".format(nuevo),
                    })
                    print("  OK id={} {} Comments='{}'".format(
                        inst.Id.ToString(), disp["nombre_bloque"], nuevo))
                except Exception as exc:
                    fallos += 1
                    detalle.append({
                        "nombre_bloque": disp["nombre_bloque"],
                        "orden": disp["orden"],
                        "motivo": "Error seteando Comments: {}".format(exc),
                    })
                    print("  FALLO {}: {}".format(disp["nombre_bloque"], exc))
            else:
                fallos += 1
                detalle.append({
                    "nombre_bloque": disp["nombre_bloque"],
                    "orden": disp["orden"],
                    "motivo": "Parametro Comments es de solo lectura",
                })
                print("  FALLO {}: Comments es de solo lectura".format(disp["nombre_bloque"]))

        except Exception as exc:
            fallos += 1
            detalle.append({
                "nombre_bloque": disp["nombre_bloque"],
                "orden": disp["orden"],
                "motivo": "Error: {}".format(exc),
            })
            print("  FALLO {}: {}".format(disp["nombre_bloque"], exc))

    trans.Commit()

    print("\n" + "=" * 60)
    print("ASIGNACIÓN RED COMPLETADA (v05 — por posicion XY)")
    print("Documento: {}".format(doc.Title))
    print("Reporte: {}".format(reporte_json))
    print("Dispositivos de red en reporte: {}".format(len(dispositivos)))
    print("Exitos: {}".format(exitos))
    print("Fallos: {}".format(fallos))
    print("  - no encontrados en Revit: {}".format(no_encontrados))
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
                "campo": "Comments (ALL_MODEL_INSTANCE_COMENTARIOS)",
                "valor": MARCA_COMENTARIO,
                "estrategia": "posicion_XY_tolerancia_{}m".format(TOLERANCIA_M),
                "dispositivos_red_reporte": len(dispositivos),
                "exitos": exitos,
                "fallos": fallos,
                "no_encontrados": no_encontrados,
                "detalle": detalle,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return {
        "exitos": exitos,
        "fallos": fallos,
        "no_encontrados": no_encontrados,
        "total_reporte": len(dispositivos),
        "detalle": detalle,
    }
