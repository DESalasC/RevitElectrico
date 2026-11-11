# -*- coding: utf-8 -*-
"""
RE_COLOCAR_DISPOSITIVOS_E06_v01.py
==================================
Coloca los dispositivos eléctricos del apartamento Tipo E 06 en Revit 2026,
leyendo los extremos de cada tramo del JSON de ruteo.

Cada tramo tiene 'extremos' con datos de dispositivo:
  - nombre: nombre de la familia (ej: "ELEC-T-D-t-15A", "ELEC-TEL")
  - x, y: posición en metros (coordenadas DXF del apartamento)
  - altura_m: altura sobre el suelo en metros
  - servicio: tipo de servicio (TOMAS, ILUMINACION, COMUNICACIONES)

Los dispositivos se colocan como FamilyInstance libres (no hostados) en la
elevación del nivel Piso 5 + altura_m, con offset calculado desde el panel
TE 06 como ancla.

Requisitos previos:
  - Las familias de dispositivos deben estar cargadas en el modelo Revit
  - El panel TE 06 debe existir en el modelo (para calcular el offset XY)

USO (pyRevit Python Shell, modelo abierto en Revit 2026):

    exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_COLOCAR_DISPOSITIVOS_E06_v01.py").read())
    r = colocar_dispositivos(doc, dry_run=True)   # 1) simular
    r = colocar_dispositivos(doc, dry_run=False)  # 2) crear de verdad
"""

import json
import os
import unicodedata

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FamilyInstance,
    FamilySymbol,
    FilteredElementCollector,
    Level,
    Structure,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import UnitUtils, UnitTypeId


def _root():
    raiz = os.environ.get("REVITELECTRICO_ROOT")
    if raiz:
        return raiz
    try:
        aqui = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(os.path.dirname(aqui)))
    except Exception:
        return os.getcwd()


def _ruta(ruta_rel):
    if os.path.isabs(ruta_rel):
        return ruta_rel
    return os.path.join(_root(), ruta_rel)


def _m_a_pies(m):
    try:
        return UnitUtils.ConvertToInternalUnits(float(m), UnitTypeId.Meters)
    except Exception:
        return float(m) / 0.3048


def _norm(t):
    if t is None:
        return ""
    try:
        t = unicode(t)  # noqa: F821
    except Exception:
        t = str(t)
    import unicodedata
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c for c in t if ord(c) < 128).strip().lower()


def _eid_str(element_id):
    try:
        return str(element_id)
    except Exception:
        return element_id.ToString()


def _familia(doc, nombre):
    """Busca una Family por nombre (normalizado)."""
    objetivo = _norm(nombre)
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            if _norm(fam.Name) == objetivo:
                return fam
        except Exception:
            continue
    return None


def _simbolo(doc, fam, nombre):
    """Busca un FamilySymbol dentro de una familia, por nombre o primero disponible."""
    objetivo = _norm(nombre)
    syms = []
    for sid in fam.GetFamilySymbolIds():
        try:
            s = doc.GetElement(sid)
            p = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            n = p.AsString() if p is not None else ""
            syms.append((sid, n or ""))
        except Exception:
            pass
    for sid, n in syms:
        if _norm(n) == objetivo:
            return doc.GetElement(sid)
    for sid, n in syms:
        nn = _norm(n)
        if objetivo and (objetivo in nn or nn in objetivo):
            return doc.GetElement(sid)
    return doc.GetElement(syms[0][0]) if syms else None


def _buscador_nivel(doc, nombre):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name.strip().lower() == (nombre or "").strip().lower():
            return lv
    return None


def _offset_por_ancla(doc, ancla):
    """Calcula el offset XY entre el DXF y el modelo usando el panel como ancla.

    Devuelve (dx_m, dy_m, nombre_encontrado, encontrado).
    """
    if not ancla:
        return 0.0, 0.0, "", False
    x_dxf = float(ancla.get("x_dxf", 0.0))
    y_dxf = float(ancla.get("y_dxf", 0.0))
    objetivo = (ancla.get("nombre_en_revit") or ancla.get("bloque_dxf") or "").strip().lower()
    if not objetivo:
        return 0.0, 0.0, "", False

    candidatos = []
    try:
        for cat in (BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures):
            for fi in FilteredElementCollector(doc).OfCategory(cat).OfClass(FamilyInstance):
                candidatos.append(fi)
    except Exception:
        pass
    if not candidatos:
        try:
            candidatos = list(FilteredElementCollector(doc).OfClass(FamilyInstance))
        except Exception:
            candidatos = []

    mejor = None
    for fi in candidatos:
        try:
            nombre = fi.Name or ""
            tipo = ""
            try:
                tipo = fi.Symbol.Name if fi.Symbol else ""
            except Exception:
                tipo = ""
            if objetivo in (nombre + " " + tipo).lower():
                mejor = fi
                break
        except Exception:
            continue

    if mejor is None:
        return 0.0, 0.0, "", False

    try:
        p = mejor.Location.Point
        return (p.X * 0.3048 - x_dxf, p.Y * 0.3048 - y_dxf, mejor.Name, True)
    except Exception:
        return 0.0, 0.0, "", False


def _extraer_dispositivos_unicos(datos):
    """Extrae dispositivos únicos de los 'extremos' de todos los tramos.

    Deduplica por (nombre, x, y, altura_m) para no colocar el mismo
    dispositivo dos veces cuando varios tramos comparten el mismo extremo.
    """
    dispositivos = {}
    for tramo in datos.get("tramos", []):
        for extremo in tramo.get("extremos", []):
            if extremo.get("tipo") != "dispositivo":
                continue
            clave = (
                extremo.get("nombre"),
                round(float(extremo.get("x", 0) or 0), 4),
                round(float(extremo.get("y", 0) or 0), 4),
                round(float(extremo.get("altura_m", 0) or 0), 3),
            )
            if clave not in dispositivos:
                dispositivos[clave] = extremo
    return list(dispositivos.values())


def _escribir(ruta, reporte):
    carpeta = os.path.dirname(ruta)
    if carpeta and not os.path.exists(carpeta):
        os.makedirs(carpeta)
    with open(ruta, "w") as f:
        f.write(json.dumps(reporte, indent=2, ensure_ascii=True))
    print("Reporte -> %s" % ruta)
    print("  creados=%s omitidos=%s errores=%s dry_run=%s"
          % (reporte.get("creados"), reporte.get("omitidos"),
             reporte.get("errores"), reporte.get("dry_run")))
    if reporte.get("error_fatal"):
        print("  ERROR: %s" % reporte["error_fatal"])


def colocar_dispositivos(doc, json_in=None, json_out=None, dry_run=True,
                         nombre_nivel=None, crear=True):
    """Coloca dispositivos del JSON E 06 como FamilyInstance en Revit.

    dry_run=True  -> no modifica el modelo; solo valida y reporta.
    """
    json_in = _ruta(json_in or "data\\ruteo_apartamento_E06_v02.json")
    json_out = _ruta(json_out or "data\\colocar_dispositivos_E06_resultado.json")

    if not os.path.exists(json_in):
        raise IOError("No existe el JSON: %s" % json_in)

    with open(json_in, "r") as f:
        datos = json.load(f)

    nombre_nivel = nombre_nivel or datos.get("nivel") or "Piso 5"
    nivel = _buscador_nivel(doc, nombre_nivel)

    ancla = datos.get("ancla") or {}
    off_x, off_y, ancla_nombre, ancla_ok = _offset_por_ancla(doc, ancla)

    dispositivos = _extraer_dispositivos_unicos(datos)

    reporte = {
        "fecha": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "json_entrada": json_in,
        "dry_run": bool(dry_run),
        "nivel_solicitado": nombre_nivel,
        "nivel_encontrado": nivel.Name if nivel else None,
        "ancla_encontrada": ancla_ok,
        "ancla_en_revit": ancla_nombre,
        "offset_xy_m": [round(off_x, 4), round(off_y, 4)],
        "dispositivos_encontrados": len(dispositivos),
        "creados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalle": [],
    }

    if nivel is None:
        reporte["error_fatal"] = "No existe el nivel '%s'" % nombre_nivel
        _escribir(json_out, reporte)
        return reporte

    if not ancla_ok:
        reporte["error_fatal"] = "No se encontró el ancla del panel '%s'" % (ancla.get("nombre_en_revit") or "")
        _escribir(json_out, reporte)
        return reporte

    if dry_run:
        for disp in dispositivos:
            reporte["detalle"].append({
                "nombre": disp.get("nombre"),
                "x": disp.get("x"),
                "y": disp.get("y"),
                "altura_m": disp.get("altura_m"),
                "servicio": disp.get("servicio"),
                "accion": "simulado",
            })
        reporte["ok"] = True
        _escribir(json_out, reporte)
        return reporte

    t = Transaction(doc, "COLOCAR DISPOSITIVOS E 06")
    t.Start()
    try:
        for disp in dispositivos:
            nombre_fam = disp.get("nombre")
            x_m = float(disp.get("x", 0) or 0) + off_x
            y_m = float(disp.get("y", 0) or 0) + off_y
            altura_m = float(disp.get("altura_m", 0) or 0)
            z_abs_ft = nivel.Elevation + _m_a_pies(altura_m)

            try:
                fam = _familia(doc, nombre_fam)
                if fam is None:
                    reporte["errores"] += 1
                    reporte["detalle"].append({
                        "nombre": nombre_fam,
                        "motivo": "familia no cargada en el modelo",
                        "accion": "error",
                    })
                    continue

                sym = _simbolo(doc, fam, nombre_fam)
                if sym is None:
                    reporte["errores"] += 1
                    reporte["detalle"].append({
                        "nombre": nombre_fam,
                        "motivo": "symbolo no encontrado",
                        "accion": "error",
                    })
                    continue

                if not sym.IsActive:
                    sym.Activate()
                    doc.Regenerate()

                punto = XYZ(_m_a_pies(x_m), _m_a_pies(y_m), z_abs_ft)
                inst = doc.Create.NewFamilyInstance(
                    punto, sym, nivel, Structure.StructuralType.NonStructural
                )

                # Marcar con servicio en parámetro Comments
                try:
                    p = inst.LookupParameter("Servicio_Conduit")
                    if p is None:
                        p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if p is not None and not p.IsReadOnly:
                        p.Set(disp.get("servicio") or "")
                except Exception:
                    pass

                reporte["creados"] += 1
                reporte["detalle"].append({
                    "nombre": nombre_fam,
                    "x": round(x_m, 4),
                    "y": round(y_m, 4),
                    "z_m": round(UnitUtils.ConvertFromInternalUnits(z_abs_ft, UnitTypeId.Meters), 3),
                    "servicio": disp.get("servicio"),
                    "element_id": _eid_str(inst.Id),
                    "accion": "creado",
                })
            except Exception as exc:
                reporte["errores"] += 1
                reporte["detalle"].append({
                    "nombre": nombre_fam,
                    "motivo": str(exc),
                    "accion": "error",
                })

        t.Commit()
        reporte["ok"] = True
    except Exception as exc:
        t.RollBack()
        reporte["ok"] = False
        reporte["error_fatal"] = str(exc)
        import traceback
        reporte["trace"] = traceback.format_exc()[-1500:]

    _escribir(json_out, reporte)
    return reporte


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
    except NameError:
        doc = None
        print("ERROR: __revit__ no disponible. Ejecutar dentro de Revit 2026.")

    if doc is not None:
        print("Documento activo: %s" % doc.Title)
        resultado = colocar_dispositivos(doc, dry_run=True)
        print("Simulacion lista. Revisar el reporte y volver a ejecutar con dry_run=False.")
