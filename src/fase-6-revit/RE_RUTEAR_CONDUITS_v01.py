# -*- coding: utf-8 -*-
"""
RE_RUTEAR_CONDUITS_v01.py — Crea los conduits de ruteo en Revit 2026 desde el
JSON que genera el pipeline Python (src/fase-6-revit/ruteo/cli.py).

Entrada: data\\ruteo_apartamento_F02_v01.json
Salida : data\\ruteo_conduits_revit_resultado.json

USO (pyRevit Python Shell, con el modelo abierto en Revit 2026):

    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\RE_RUTEAR_CONDUITS_v01.py").read())
    r = rutear_conduits(doc, dry_run=True)      # 1) simular y revisar
    r = rutear_conduits(doc, dry_run=False)     # 2) crear de verdad

Antes de crear:
  - Ejecutar el CLI de Python y revisar el reporte HTML (avisos y tramos sin marcador).
  - Confirmar que existe un ConduitType por diametro (CREAR_TIPOS_CONDUIT_v04.py).
  - Confirmar que el nivel del JSON existe en el modelo.

Ultimos tres cambios
--------------------
1. 2026-11-09 v01: primera version. Lee el JSON de ruteo, resuelve ConduitType por
   diametro y crea conduits por segmento con Servicio_Conduit.
2. Las distancias del JSON estan en metros; Revit trabaja en pies internos.
3. dry_run por defecto para no tocar el modelo sin revision del operador.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    BuiltInParameter,
    Level,
    Transaction,
    UnitUtils,
    UnitTypeId,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System.Collections.Generic import List

import json
import os
import traceback
from datetime import datetime


DIAMETRO_A_PULGADAS = {
    "1/2": 0.5,
    "3/4": 0.75,
    "1": 1.0,
    "1-1/4": 1.25,
    "1-1/2": 1.5,
    "2": 2.0,
    "2-1/2": 2.5,
    "3": 3.0,
    "3-1/2": 3.5,
    "4": 4.0,
}

# Mapeo de designacion de diametro a milimetros (registro 2026-11-10:
# 1/2" = 21 mm, 3/4" = 27 mm, por usuario).
# Los tipos de conduit del modelo no exponen el diametro como parametro
# legible, por lo que el match se hace por diametro de instancias existentes.
DIAMETRO_A_MM = {
    "1/2": 21,
    "3/4": 27,
    "1": 33,
    "1-1/4": 42,
    "1-1/2": 48,
    "2": 60,
    "2-1/2": 73,
    "3": 89,
    "3-1/2": 102,
    "4": 114,
}


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


def _token_pulgadas(texto):
    """Normaliza '1/2\"' o '1/2' a '1/2' para buscar en DIAMETRO_A_PULGADAS."""
    t = (texto or "").replace('"', "").strip()
    t = t.replace(" ", "")
    return t


def _buscador_nivel(doc, nombre):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name.strip().lower() == (nombre or "").strip().lower():
            return lv
    return None


def _buscar_symbolo_caja(doc, familia_nombre, tipo_nombre):
    """Localiza el FamilySymbol de la caja de conexiones por familia y tipo."""
    objetivo_fam = (familia_nombre or "").strip().lower()
    objetivo_tipo = (tipo_nombre or "").strip().lower()
    if not objetivo_fam:
        return None, "sin familia configurada"
    try:
        from Autodesk.Revit.DB import FamilySymbol
        symbols = list(FilteredElementCollector(doc).OfClass(FamilySymbol))
    except Exception as exc:
        return None, "no se pudieron listar FamilySymbol: %s" % exc

    candidatos = []
    for sym in symbols:
        try:
            nombre_fam = sym.Family.Name if sym.Family else ""
            if objetivo_fam not in nombre_fam.strip().lower():
                continue
            nombre_tipo = sym.Name or ""
            candidatos.append((sym, nombre_fam, nombre_tipo))
        except Exception:
            continue

    if not candidatos:
        return None, "familia '%s' no cargada" % familia_nombre
    if objetivo_tipo:
        for sym, nombre_fam, nombre_tipo in candidatos:
            if objetivo_tipo == nombre_tipo.strip().lower():
                return sym, None
        return None, ("familia '%s' encontrada pero sin el tipo '%s' (tipos: %s)"
                      % (familia_nombre, tipo_nombre,
                         [c[2] for c in candidatos]))
    return candidatos[0][0], None


def _crear_cajas(doc, cajas, symbol, nivel, off_x, off_y, reporte):
    """Crea las cajas de conexion como FamilyInstance en la cota indicada."""
    from Autodesk.Revit.DB import XYZ, Structure
    creadas = 0
    for caja in cajas:
        try:
            x = _m_a_pies(float(caja.get("x", 0.0)) + off_x)
            y = _m_a_pies(float(caja.get("y", 0.0)) + off_y)
            z = _m_a_pies(float(caja.get("z_absoluta_m", 0.0)))
            punto = XYZ(x, y, z)
            inst = doc.Create.NewFamilyInstance(punto, symbol, nivel,
                                                Structure.StructuralType.NonStructural)
            try:
                p = inst.LookupParameter("Servicio_Conduit")
                if p is not None and not p.IsReadOnly:
                    p.Set(caja.get("servicio") or "")
            except Exception:
                pass
            creadas += 1
            if len(reporte["detalle"]) < 200:
                reporte["detalle"].append({
                    "id": caja.get("id"), "accion": "caja_creada",
                    "element_id": _eid_str(inst.Id),
                    "aparato": caja.get("aparato_nombre"),
                })
        except Exception as exc:
            reporte["errores"] += 1
            reporte["detalle"].append({
                "id": caja.get("id"), "accion": "error_caja", "motivo": str(exc)
            })
    return creadas


def _offset_por_ancla(doc, ancla):
    """Calcula el offset XY entre el DXF y el modelo usando el panel como ancla.

    Regla G7 del proyecto: el panel electrico del apartamento es el origen.
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
        from Autodesk.Revit.DB import FamilyInstance, BuiltInCategory
        for cat in (BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures):
            for fi in FilteredElementCollector(doc).OfCategory(cat).OfClass(FamilyInstance):
                candidatos.append(fi)
    except Exception:
        pass
    if not candidatos:
        try:
            from Autodesk.Revit.DB import FamilyInstance
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


def _nombre_seguro(ct):
    """Lee el nombre de un elemento de forma segura (IronPython 2.7 compatible)."""
    try:
        return ct.Name
    except Exception:
        pass
    try:
        p = ct.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            return p.AsString() or ""
    except Exception:
        pass
    return ""


def _eid_str(element_id):
    """Convierte ElementId a string de forma segura en IronPython 2.7."""
    try:
        return str(element_id)
    except Exception:
        return element_id.ToString()


def _tipos_conduit(doc):
    """Devuelve lista de (ElementId, nombre, elemento) de los tipos de conduit."""
    salida = []
    vistos = set()
    for ct in FilteredElementCollector(doc).OfClass(ConduitType):
        try:
            nombre = _nombre_seguro(ct)
            clave = ("CT", _eid_str(ct.Id))
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append((ct.Id, nombre, ct))
        except Exception:
            continue
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType():
        try:
            clave = ("FS", _eid_str(fs.Id))
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append((fs.Id, fs.Name, fs))
        except Exception:
            continue
    return salida


def _diametro_tipo_por_instancias(doc, ct):
    """Determina el diametro mas comun (mm) de las instancias existentes de un tipo de conduit.

    Como ConduitType no expone el diametro como parametro legible en IronPython 2.7,
    se infiere del diametro de las instancias ya creadas en el modelo.
    """
    from collections import Counter
    diametros = []
    try:
        for inst in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit
        ).WhereElementIsNotElementType():
            try:
                if _eid_str(inst.GetTypeId()) == _eid_str(ct.Id):
                    p = inst.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                    if p is not None:
                        diametros.append(round(p.AsDouble() * 304.8, 1))
            except Exception:
                continue
    except Exception:
        pass
    if not diametros:
        return None
    return Counter(diametros).most_common(1)[0][0]


def _pulgadas_de_tipo(nombre):
    """Extrae el diametro en pulgadas del nombre del tipo de conduit (fallback)."""
    texto = (nombre or "").replace('"', "").replace("CONDUIT", "").replace("Conduit", "").strip()
    texto = texto.replace(" ", "")
    for token, valor in DIAMETRO_A_PULGADAS.items():
        if texto.startswith(token) or token in texto:
            return valor, token
    return None, None


def _resolver_tipos(doc, diametros_requeridos):
    """Mapea cada designacion ('1/2"') al ElementId del tipo de conduit.

    Estrategia:
      1. Analiza instancias existentes para inferir el diametro mas comun (mm)
         de cada tipo de conduit.
      2. Convierte cada diametro requerido de pulgadas a mm
         (DIAMETRO_A_MM: 1/2"=21mm, 3/4"=27mm, etc.).
      3. Hace match por diametro mm.
      4. Fallback: intenta parsear el nombre del tipo (pulgadas).
    """
    tipos = _tipos_conduit(doc)

    # Construir mapa: id_del_tipo -> {id, nombre, diam_mm_inferido}
    tipo_info = {}
    for elem_id, nombre, ct in tipos:
        d_mm = _diametro_tipo_por_instancias(doc, ct)
        tipo_info[_eid_str(elem_id)] = {
            "id": elem_id,
            "nombre": nombre,
            "diam_mm": d_mm,
        }

    mapa = {}
    detalle = []
    for pulgadas_txt in sorted(set(diametros_requeridos)):
        token_buscado = _token_pulgadas(pulgadas_txt)
        objetivo_mm = DIAMETRO_A_MM.get(token_buscado)
        objetivo_pulg = DIAMETRO_A_PULGADAS.get(token_buscado)
        encontrado = None

        # Estrategia 1: match por diametro de instancias (mm)
        if objetivo_mm is not None:
            for info in tipo_info.values():
                if info["diam_mm"] == objetivo_mm:
                    encontrado = (info["id"], info["nombre"])
                    break

        # Estrategia 2: fallback - parsear nombre del tipo (pulgadas)
        if encontrado is None and objetivo_pulg is not None:
            for elem_id, nombre, _elem in tipos:
                valor, token = _pulgadas_de_tipo(nombre)
                if valor is not None and abs(valor - objetivo_pulg) < 1e-6:
                    encontrado = (elem_id, nombre)
                    break

        mapa[pulgadas_txt] = encontrado[0] if encontrado else None
        detalle.append({
            "diametro": pulgadas_txt,
            "token": token_buscado,
            "tipo_encontrado": encontrado[1] if encontrado else None,
            "ok": encontrado is not None,
        })
    return mapa, detalle, [t[1] for t in tipos]


def _buscar_tipo_por_nombre(doc, patron, excluir=None):
    """Busca un ConduitType cuyo nombre contenga el patron dado."""
    tipos = _tipos_conduit(doc)
    for elem_id, nombre, ct in tipos:
        nombre_lower = (nombre or "").lower()
        if patron.lower() in nombre_lower:
            if excluir and excluir.lower() in nombre_lower:
                continue
            return elem_id
    return None


def _set_servicio(conduit, servicio):
    """Escribe el servicio en Servicio_Conduit; si no existe, cae a Comments."""
    escrito = None
    for nombre in ("Servicio_Conduit", "Servicio Conduit"):
        try:
            p = conduit.LookupParameter(nombre)
            if p is not None and not p.IsReadOnly and p.StorageType.ToString() == "String":
                p.Set(servicio)
                escrito = nombre
                break
        except Exception:
            continue
    if escrito is None:
        try:
            p = conduit.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                p.Set("[%s]" % servicio)
                escrito = "Comments"
        except Exception:
            pass
    return escrito


def _set_circuito(conduit, red):
    """Escribe el circuito/red del tramo en el objeto Conduit de Revit.

    Intenta el parametro 'Circuito_Conduit'; si no existe, cae a Comments.
    """
    if not red:
        return None
    escrito = None
    for nombre in ("Circuito_Conduit", "Circuito Conduit", "RED", "Circuit"):
        try:
            p = conduit.LookupParameter(nombre)
            if p is not None and not p.IsReadOnly and p.StorageType.ToString() == "String":
                p.Set(red)
                escrito = nombre
                break
        except Exception:
            continue
    if escrito is None:
        try:
            p = conduit.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                existente = p.AsString() or ""
                p.Set((existente + " | " if existente else "") + "Circuito: %s" % red)
                escrito = "Comments"
        except Exception:
            pass
    return escrito


def _rutas_json_conduits(apartamento):
    """Devuelve las rutas de JSON de entrada y salida para un apartamento."""
    apartamento = (apartamento or "E06").strip().upper()
    json_in = "data\\ruteo_apartamento_%s_v02.json" % apartamento
    json_out = "data\\ruteo_conduits_revit_resultado_%s.json" % apartamento
    return _ruta(json_in), _ruta(json_out)


def rutear_conduits(doc, apartamento="E06", json_in=None, json_out=None,
                    dry_run=True, solo_servicios=None,
                    limite=None, nombre_nivel=None, crear_cajas=True):
    """Crea los conduits definidos en el JSON de ruteo.

    dry_run=True  -> no modifica el modelo; solo valida y reporta.
    apartamento -> identificador del apartamento (ej: "E06", "E05").
    solo_servicios -> lista opcional, p.ej. ["TOMAS"].
    limite -> cantidad maxima de tramos a procesar (para pruebas).
    """
    json_in = _ruta(json_in) if json_in else _rutas_json_conduits(apartamento)[0]
    json_out = _ruta(json_out) if json_out else _rutas_json_conduits(apartamento)[1]

    if not os.path.exists(json_in):
        raise IOError("No existe el JSON de ruteo: %s" % json_in)

    with open(json_in, "r") as f:
        datos = json.load(f)

    tramos = datos.get("tramos", [])
    cajas = datos.get("cajas", [])
    if solo_servicios:
        filtro = set([s.upper() for s in solo_servicios])
        tramos = [t for t in tramos if (t.get("servicio") or "").upper() in filtro]
    if limite:
        tramos = tramos[:int(limite)]

    nombre_nivel = nombre_nivel or datos.get("nivel") or "Piso 5"
    nivel = _buscador_nivel(doc, nombre_nivel)

    ancla = datos.get("ancla") or {}
    off_x, off_y, ancla_nombre, ancla_ok = _offset_por_ancla(doc, ancla)

    diametros = [t.get("diametro_pulgadas") for t in tramos]
    mapa_tipos, detalle_tipos, nombres_tipos = _resolver_tipos(doc, diametros)

    reporte = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "json_entrada": json_in,
        "dry_run": bool(dry_run),
        "nivel_solicitado": nombre_nivel,
        "nivel_encontrado": nivel.Name if nivel else None,
        "ancla_dxf": ancla,
        "ancla_en_revit": ancla_nombre,
        "ancla_encontrada": ancla_ok,
        "offset_xy_m": [round(off_x, 4), round(off_y, 4)],
        "tramos_en_json": len(datos.get("tramos", [])),
        "tramos_a_procesar": len(tramos),
        "cajas_en_json": len(cajas),
        "cajas_pendientes_de_modelar": len(cajas),
        "familia_caja": (datos.get("config_cajas") or {}).get("familia") or "",
        "tipos_conduit_disponibles": nombres_tipos,
        "resolucion_diametros": detalle_tipos,
        "creados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalle": [],
    }

    if nivel is None:
        reporte["error_fatal"] = "No existe el nivel '%s' en el documento" % nombre_nivel
        _escribir(json_out, reporte)
        return reporte

    faltantes = [d for d in detalle_tipos if not d["ok"]]
    if faltantes:
        reporte["error_fatal"] = (
            "Faltan tipos de conduit para: %s. Ejecutar CREAR_TIPOS_CONDUIT_v04.py "
            "o crear los tipos con esos diametros."
            % ", ".join(d["diametro"] for d in faltantes)
        )
        _escribir(json_out, reporte)
        return reporte

    # plan de segmentos
    segmentos = []
    for tramo in tramos:
        puntos = tramo.get("puntos_3d") or []
        if len(puntos) < 2:
            reporte["omitidos"] += 1
            reporte["detalle"].append({"id": tramo.get("id"), "motivo": "sin puntos_3d"})
            continue
        pts = [XYZ(_m_a_pies(p[0] + off_x), _m_a_pies(p[1] + off_y),
                   nivel.Elevation + _m_a_pies(p[2])) for p in puntos]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if a.DistanceTo(b) < 1e-6:
                continue
            segmentos.append((tramo, a, b))

    reporte["segmentos_planificados"] = len(segmentos)

    reporte["circuito_pendiente"] = sum(1 for t in tramos if t.get("red"))

    if dry_run:
        for tramo, a, b in segmentos:
            reporte["detalle"].append({
                "id": tramo.get("id"),
                "servicio": tramo.get("servicio"),
                "diametro": tramo.get("diametro_pulgadas"),
                "circuito": tramo.get("red"),
                "longitud_m": round(a.DistanceTo(b) * 0.3048, 3),
                "accion": "simulado",
            })
        cfg_cajas = datos.get("config_cajas") or {}
        if cajas and crear_cajas:
            symbol, error = _buscar_symbolo_caja(
                doc, cfg_cajas.get("familia"), cfg_cajas.get("tipo"))
            reporte["caja_symbol_encontrado"] = symbol is not None
            reporte["caja_symbol_error"] = error
        reporte["ok"] = True
        _escribir(json_out, reporte)
        return reporte

    t = Transaction(doc, "RUTEO DE CONDUITS")
    t.Start()
    try:
        for tramo, a, b in segmentos:
            # Seleccionar tipo de conduit por diametro (del JSON de ruteo).
            # El mapa se resuelve por diametro de instancia en _resolver_tipos:
            #   1/2" (21mm) -> tipo con instancias a 21mm
            #   3/4" (27mm) -> tipo con instancias a 27mm
            diametro = tramo.get("diametro_pulgadas")
            tipo_id = mapa_tipos.get(diametro) if diametro else None
            if tipo_id is None:
                reporte["errores"] += 1
                reporte["detalle"].append({
                    "id": tramo.get("id"),
                    "accion": "error",
                    "motivo": "No hay tipo de conduit para diametro %s" % diametro,
                })
                continue
            try:
                conduit = Conduit.Create(doc, tipo_id, a, b, nivel.Id)
                if conduit is None:
                    raise Exception("Conduit.Create devolvio None")
                _set_servicio(conduit, tramo.get("servicio") or "")
                circuito_escrito = _set_circuito(conduit, tramo.get("red"))
                reporte["creados"] += 1
                if len(reporte["detalle"]) < 200:
                    reporte["detalle"].append({
                        "id": tramo.get("id"),
                        "servicio": tramo.get("servicio"),
                        "diametro": tramo.get("diametro_pulgadas"),
                        "circuito": tramo.get("red"),
                        "circuito_escrito": circuito_escrito,
                        "element_id": _eid_str(conduit.Id),
                        "accion": "creado",
                    })
            except Exception as exc:
                reporte["errores"] += 1
                if len(reporte["detalle"]) < 200:
                    reporte["detalle"].append({
                        "id": tramo.get("id"),
                        "accion": "error",
                        "motivo": str(exc),
                        "trace": traceback.format_exc()[-500:],
                    })
        t.Commit()
        reporte["ok"] = True

        if cajas and crear_cajas:
            cfg_cajas = datos.get("config_cajas") or {}
            symbol, error = _buscar_symbolo_caja(
                doc, cfg_cajas.get("familia"), cfg_cajas.get("tipo"))
            reporte["caja_symbol_encontrado"] = symbol is not None
            reporte["caja_symbol_error"] = error
            if symbol is None:
                reporte["cajas_creadas"] = 0
                reporte["cajas_pendientes_de_modelar"] = len(cajas)
            else:
                t2 = Transaction(doc, "CAJAS DE CONEXION")
                t2.Start()
                try:
                    if not symbol.IsActive:
                        symbol.Activate()
                        doc.Regenerate()
                    reporte["cajas_creadas"] = _crear_cajas(
                        doc, cajas, symbol, nivel, off_x, off_y, reporte)
                    reporte["cajas_pendientes_de_modelar"] = len(cajas) - reporte["cajas_creadas"]
                    t2.Commit()
                except Exception as exc:
                    t2.RollBack()
                    reporte["cajas_creadas"] = 0
                    reporte["caja_symbol_error"] = str(exc)
    except Exception as exc:
        t.RollBack()
        reporte["ok"] = False
        reporte["error_fatal"] = str(exc)
        reporte["trace"] = traceback.format_exc()[-1500:]

    _escribir(json_out, reporte)
    return reporte


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


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
    except NameError:
        doc = None
        print("ERROR: __revit__ no disponible. Ejecutar dentro de Revit 2026.")

    if doc is not None:
        print("Documento activo: %s" % doc.Title)
        resultado = rutear_conduits(doc, dry_run=True)
        print("Simulacion lista. Revisar el reporte y volver a ejecutar con dry_run=False.")
