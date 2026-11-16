# -*- coding: utf-8 -*-
"""
F6_CREAR_DISPOSITIVOS_E06_v01.py
================================
Proyecto   : RevitElectrico
Fase       : 6 - Revit
Apartamento: E06  |  Nivel: Piso 5  |  Lote GUID: 46c3f138-025d-47d4-b24a-41cd21181a58

OBJETIVO UNICO
--------------
Crear los 44 dispositivos electricos del apartamento E06 en un ARCHIVO BASE NUEVO,
en UNA SOLA PASADA, con posicion absoluta mundial correcta y trazabilidad completa.

PRINCIPIO DE DISENO (regla del proyecto)
----------------------------------------
No se parchea. Este script asume un archivo base limpio (sin dispositivos E06 previos).
Si detecta el parametro RevitElectrico_Lote ya poblado con este GUID, ABORTA y avisa:
eso significa que el archivo no es base nuevo y debe relanzarse la etapa anterior.

ESTRATEGIA DE POSICIONAMIENTO (en cascada, con validacion real)
---------------------------------------------------------------
Para cada dispositivo se intenta, en orden, y se VALIDA leyendo la Z real:

  A) NewFamilyInstance(XYZ_absoluto, simbolo, StructuralType.NonStructural)
     -> Z es coordenada absoluta mundial. Solo familias no host-based.

  B) NewFamilyInstance(XYZ_offset_nivel, simbolo, nivel, StructuralType.NonStructural)
     -> Z = elevacion del nivel + offset. z_offset_m = z_abs_m - 13.22 (coherente).

  C) NewFamilyInstance(XYZ, simbolo, host_cercano, StructuralType.NonStructural) + MoveElement
     -> Ultimo recurso. MoveElement intenta corregir pero puede romper el anclaje.

Despues de crear, se lee Location.Point.Z. Si difiere mas de TOL_M del objetivo y
el elemento admite movimiento, se corrige con MoveElement DENTRO DE LA MISMA
TRANSACCION y se vuelve a leer. Si sigue sin coincidir, el dispositivo se reporta
como FALLIDO y la transaccion completa hace RollBack. Nunca se reporta exito sin
haber verificado la Z real.

NOTAS DE COMPATIBILIDAD VERIFICADAS CONTRA RevitAPI.xml DE REVIT 2026
---------------------------------------------------------------------
  - ElementId expone .Value (Int64). .IntegerValue YA NO EXISTE en Revit 2026.
  - ElementId constructores: (BuiltInCategory), (BuiltInParameter), (Int64).
    No hay constructor Int32 -> ElementId(int) es ambiguo en IronPython 2.7.
  - NewFamilyInstance sobrecargas confirmadas en el API:
    (XYZ, FamilySymbol, StructuralType)         -> estrategia A
    (XYZ, FamilySymbol, Level, StructuralType)   -> estrategia B
    (XYZ, FamilySymbol, Element, StructuralType) -> estrategia C
  - Element.LevelId, LocationPoint.Point, LocationCurve.Curve, Curve.Distance(XYZ),
    Line.CreateBound(XYZ,XYZ), ElementTransformUtils.MoveElement/RotateElement existen.
  - Curve.Distance(XYZ) EXISTE (confirmado en RevitAPI.xml).
  - En este entorno NO son importables con from-import: FailureHandlingOptions,
    TransactionFailureHandlingOptions, ExternalDefinitionCreationOptions,
    BuiltInDataType, ElementCategorySet. Por eso se usa __import__.
  - ElementId.IntegerValue ya no existe en Revit 2026: se usa .Value.

USO EN LA CONSOLA pyRevit DE REVIT
----------------------------------
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\F6_CREAR_DISPOSITIVOS_E06_v01.py").read())

    # Verificar sin crear nada:
    crear_dispositivos_e06(doc, dry_run=True)

    # Crear de verdad:
    crear_dispositivos_e06(doc)

SALIDA
------
D:\\Work\\PROJECTS\\RevitElectrico\\data\\trazabilidad_E06_piso5_v01.json
"""

import clr
import json
import os
import datetime
import math

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

_DB = __import__("Autodesk.Revit.DB", fromlist=["*"])
_STRUCT = __import__("Autodesk.Revit.DB.Structure", fromlist=["*"])

XYZ = _DB.XYZ
Transaction = _DB.Transaction
FilteredElementCollector = _DB.FilteredElementCollector
FamilyInstance = _DB.FamilyInstance
FamilySymbol = _DB.FamilySymbol
Level = _DB.Level
ElementTransformUtils = _DB.ElementTransformUtils
Line = _DB.Line
BuiltInCategory = _DB.BuiltInCategory
StructuralType = _STRUCT.StructuralType

# ----------------------------------------------------------------------------
# CONFIGURACION
# ----------------------------------------------------------------------------
DATASET_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\E06_dispositivos_para_crear.json"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_v01.json"

APARTAMENTO = "E06"
NIVEL_NOMBRE = "Piso 5"
LOTE_GUID = "46c3f138-025d-47d4-b24a-41cd21181a58"
LOTE_PARAM = "RevitElectrico_Lote"

TOL_M = 0.01
FT_PER_M = 3.280839895

CATEGORIAS_ESPERADAS = [
    "Lighting Fixtures",
    "Electrical Fixtures",
    "Communication Devices",
    "Data Devices",
]

# Categorias de host aceptadas (para el trazador de host cercano)
NOMBRES_HOST = ("Walls", "Ceilings")


# ----------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------
def _m_a_ft(m):
    return m * FT_PER_M


def _ft_a_m(ft):
    return ft / FT_PER_M


def _eid_int(element_id):
    """ElementId -> int. Revit 2026 expone .Value (Int64); .IntegerValue ya no existe."""
    if element_id is None:
        return -1
    try:
        v = getattr(element_id, "Value", None)
        if v is not None:
            return int(v)
    except Exception:
        pass
    try:
        return int(str(element_id).strip())
    except Exception:
        return -1


def _bic_int(nombre):
    """BuiltInCategory.<nombre> -> int, o None si no existe."""
    try:
        return int(getattr(BuiltInCategory, nombre))
    except Exception:
        return None


def _cargar_dataset(ruta):
    with open(ruta, "r") as f:
        return json.load(f)


def _buscar_nivel(doc, nombre):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        try:
            if lv.Name == nombre:
                return lv
        except Exception:
            continue
    return None


def _buscar_simbolo(doc, nombre_familia, nombre_simbolo):
    """Devuelve (FamilySymbol, tipos_disponibles_en_esa_familia)."""
    disponibles = []
    for fs in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            fam_nombre = fs.Family.Name if fs.Family else ""
        except Exception:
            continue
        if fam_nombre != nombre_familia:
            continue
        try:
            tipo_nombre = fs.Name
        except Exception:
            tipo_nombre = ""
        disponibles.append(tipo_nombre)
        if tipo_nombre == nombre_simbolo:
            return fs, disponibles

    norm = lambda s: "".join(str(s).lower().split())
    objetivo = norm(nombre_simbolo)
    for fs in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            fam_nombre = fs.Family.Name if fs.Family else ""
            tipo_nombre = fs.Name
        except Exception:
            continue
        if norm(fam_nombre) == norm(nombre_familia) and norm(tipo_nombre) == objetivo:
            return fs, disponibles

    return None, disponibles


def _categorias_con_parametro(doc):
    cats = set()
    try:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                if fi.LookupParameter(LOTE_PARAM) is not None and fi.Category:
                    cats.add(fi.Category.Name)
            except Exception:
                continue
    except Exception:
        pass
    return sorted(cats)


def _contar_lote_existente(doc):
    n = 0
    try:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                p = fi.LookupParameter(LOTE_PARAM)
                if p is not None and p.AsString() == LOTE_GUID:
                    n += 1
            except Exception:
                continue
    except Exception:
        pass
    return n


def _z_real_m(fi):
    try:
        loc = fi.Location
        if loc is None or not hasattr(loc, "Point"):
            return None
        return _ft_a_m(loc.Point.Z)
    except Exception:
        return None


def _mover_a_z(doc, fi, z_obj_m):
    """Intenta llevar el elemento a Z absoluta objetivo. Devuelve True si lo logro."""
    try:
        loc = fi.Location
        if loc is None or not hasattr(loc, "Point"):
            return False
        dz = _m_a_ft(z_obj_m) - loc.Point.Z
        if abs(dz) < 1e-6:
            return True
        ElementTransformUtils.MoveElement(doc, fi.Id, XYZ(0.0, 0.0, dz))
        return True
    except Exception:
        return False


def _rotar(doc, fi, grados):
    try:
        if abs(grados) < 1e-6:
            return True
        loc = fi.Location
        if loc is None or not hasattr(loc, "Point"):
            return False
        p = loc.Point
        eje = Line.CreateBound(p, XYZ(p.X, p.Y, p.Z + 1.0))
        ElementTransformUtils.RotateElement(doc, fi.Id, eje, math.radians(grados))
        return True
    except Exception:
        return False


def _host_cercano(doc, x_ft, y_ft, radio_m=8.0):
    """Host (muro o techo) mas cercano al punto XY, dentro del radio."""
    objetivo = XYZ(x_ft, y_ft, 0.0)
    mejor = None
    mejor_dist = _m_a_ft(radio_m)
    try:
        for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
            try:
                cat = el.Category
                if cat is None:
                    continue
                if cat.Name not in NOMBRES_HOST:
                    continue
                loc = el.Location
                if loc is None or not hasattr(loc, "Curve"):
                    continue
                curva = loc.Curve
                if curva is None:
                    continue
                d = curva.Distance(objetivo)
                if d < mejor_dist:
                    mejor_dist = d
                    mejor = el
            except Exception:
                continue
    except Exception:
        return None
    return mejor


def _crear_uno(doc, disp, nivel, simbolo):
    """Crea un dispositivo probando A/B/C. Devuelve (instancia, estrategia, error)."""
    x = _m_a_ft(disp["x_m"])
    y = _m_a_ft(disp["y_m"])
    z_abs = _m_a_ft(disp["z_abs_m"])
    z_off = _m_a_ft(disp["z_offset_m"])

    # A) sin host y sin nivel -> Z absoluta mundial (solo familias no host-based)
    try:
        fi = doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), simbolo, StructuralType.NonStructural)
        if fi is not None:
            return fi, "A_sin_host_z_absoluta", None
        err_a = "A: NewFamilyInstance devolvio None"
    except Exception as exc_a:
        err_a = "A: " + str(exc_a)[:140]

    # B) con nivel + offset desde el nivel
    if nivel is not None:
        try:
            fi = doc.Create.NewFamilyInstance(XYZ(x, y, z_off), simbolo, nivel, StructuralType.NonStructural)
            if fi is not None:
                return fi, "B_con_nivel_offset", None
            err_b = "B: NewFamilyInstance devolvio None"
        except Exception as exc_b:
            err_b = "B: " + str(exc_b)[:140]
    else:
        err_b = "B: nivel '%s' no encontrado" % NIVEL_NOMBRE

    # C) con host cercano + move
    host = _host_cercano(doc, x, y)
    if host is not None:
        try:
            fi = doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), simbolo, host, StructuralType.NonStructural)
            if fi is not None:
                return fi, "C_con_host", None
            err_c = "C: NewFamilyInstance devolvio None"
        except Exception as exc_c:
            err_c = "C: " + str(exc_c)[:140]
    else:
        err_c = "C: sin host cercano"

    return None, "fallido", err_a + " | " + err_b + " | " + err_c


def _guardar(resultado):
    try:
        carpeta = os.path.dirname(SALIDA_JSON)
        if carpeta and not os.path.exists(carpeta):
            os.makedirs(carpeta)
        with open(SALIDA_JSON, "w") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(" JSON: %s" % SALIDA_JSON)
    except Exception as exc:
        print(" [ERROR] No se pudo escribir el JSON: %s" % str(exc)[:200])


# ----------------------------------------------------------------------------
# FUNCION PRINCIPAL
# ----------------------------------------------------------------------------
def crear_dispositivos_e06(doc, dry_run=False):
    """Crea los 44 dispositivos E06. Requiere documento = ARCHIVO BASE NUEVO."""

    resultado = {
        "script": "F6_CREAR_DISPOSITIVOS_E06_v01",
        "script_version": "v01-2026-11-12",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": None,
        "ruta_documento": None,
        "dry_run": dry_run,
        "apartamento": APARTAMENTO,
        "nivel_esperado": NIVEL_NOMBRE,
        "lote_guid": LOTE_GUID,
        "parametro": LOTE_PARAM,
        "tol_m": TOL_M,
        "status": "iniciado",
        "abortado": False,
        "motivo_aborto": None,
        "elementos_previos_del_lote": 0,
        "total_dataset": 0,
        "creados_ok": 0,
        "creados_con_correccion": 0,
        "fallidos": 0,
        "con_guid": 0,
        "sin_guid": 0,
        "por_estrategia": {},
        "categorias_con_parametro": [],
        "categorias_faltantes": [],
        "simbolos_no_encontrados": [],
        "dispositivos": [],
    }

    try:
        resultado["documento"] = doc.Title
        resultado["ruta_documento"] = doc.PathName
    except Exception:
        pass

    print("")
    print("=" * 90)
    print(" F6 - CREAR DISPOSITIVOS E06  |  %s  |  %s" % (APARTAMENTO, NIVEL_NOMBRE))
    print("=" * 90)
    print(" Documento : %s" % resultado["documento"])
    print(" Ruta      : %s" % resultado["ruta_documento"])
    print(" Dry run   : %s" % dry_run)
    print("")

    # --- Guardia de base limpio ---------------------------------------------
    existentes = _contar_lote_existente(doc)
    resultado["elementos_previos_del_lote"] = existentes
    if existentes > 0 and not dry_run:
        resultado["status"] = "ABORTADO"
        resultado["abortado"] = True
        resultado["motivo_aborto"] = (
            "El documento ya tiene %d dispositivos con el GUID del lote. NO es un archivo "
            "base nuevo. Cierra SIN guardar, abre el archivo base limpio y relanza la etapa."
            % existentes
        )
        print(" [ABORTADO] %s" % resultado["motivo_aborto"])
        _guardar(resultado)
        return resultado

    # --- Categorias con parametro -------------------------------------------
    cats = _categorias_con_parametro(doc)
    resultado["categorias_con_parametro"] = cats
    faltantes = [c for c in CATEGORIAS_ESPERADAS if c not in cats]
    resultado["categorias_faltantes"] = faltantes
    if faltantes:
        print(" [AVISO] Parametro '%s' NO vinculado en: %s" % (LOTE_PARAM, ", ".join(faltantes)))
        print("         Esos dispositivos se crearan pero quedaran SIN GUID.")
        print("         Manage > Project Parameters > Add > Shared Parameter")
        print("")
    else:
        print(" Parametro '%s' vinculado en las %d categorias esperadas."
              % (LOTE_PARAM, len(CATEGORIAS_ESPERADAS)))
        print("")

    # --- Dataset -------------------------------------------------------------
    if not os.path.exists(DATASET_JSON):
        resultado["status"] = "ERROR"
        resultado["motivo_aborto"] = "No existe el dataset: %s" % DATASET_JSON
        print(" [ERROR] %s" % resultado["motivo_aborto"])
        _guardar(resultado)
        return resultado

    ds = _cargar_dataset(DATASET_JSON)
    dispositivos = ds["dispositivos"]
    resultado["total_dataset"] = len(dispositivos)
    print(" Dataset   : %d dispositivos" % len(dispositivos))
    print(" Nivel ref : %s (elev %.2f m)" % (ds["nivel"], ds["nivel_elev_m"]))
    print("")

    nivel = _buscar_nivel(doc, NIVEL_NOMBRE)
    if nivel is None:
        print(" [AVISO] Nivel '%s' no encontrado. Solo se usara estrategia A." % NIVEL_NOMBRE)
    else:
        print(" Nivel '%s' encontrado (id=%d)." % (NIVEL_NOMBRE, _eid_int(nivel.Id)))
    print("")

    cache_simbolos = {}
    faltantes_simbolo = {}

    def obtener_simbolo(nombre_familia, nombre_simbolo):
        clave = (nombre_familia, nombre_simbolo)
        if clave in cache_simbolos:
            return cache_simbolos[clave]
        fs, disponibles = _buscar_simbolo(doc, nombre_familia, nombre_simbolo)
        if fs is None:
            faltantes_simbolo[clave] = disponibles
        cache_simbolos[clave] = fs
        return fs

    # --- Transaccion unica ---------------------------------------------------
    t = Transaction(doc, "F6 - Crear dispositivos E06 (%d)" % len(dispositivos))
    t.Start()
    try:
        for idx, disp in enumerate(dispositivos):
            etiqueta = "%2d/%2d %-22s" % (idx + 1, len(dispositivos), disp["bloque"][:22])
            simbolo = obtener_simbolo(disp["familia"], disp["simbolo"])

            if simbolo is None:
                resultado["dispositivos"].append({
                    "n": idx + 1,
                    "bloque": disp["bloque"],
                    "familia": disp["familia"],
                    "simbolo": disp["simbolo"],
                    "accion": "simbolo_no_encontrado",
                    "z_objetivo_m": disp["z_abs_m"],
                    "z_real_m": None,
                    "guid": None,
                })
                resultado["fallidos"] += 1
                print(" %s  SIN SIMBOLO (%s / %s)" % (etiqueta, disp["familia"], disp["simbolo"]))
                continue

            try:
                if not simbolo.IsActive:
                    simbolo.Activate()
                    doc.Regenerate()
            except Exception:
                pass

            if dry_run:
                resultado["dispositivos"].append({
                    "n": idx + 1,
                    "bloque": disp["bloque"],
                    "familia": disp["familia"],
                    "simbolo": disp["simbolo"],
                    "accion": "dry_run_ok",
                    "z_objetivo_m": disp["z_abs_m"],
                    "z_real_m": None,
                    "guid": None,
                })
                print(" %s  [dry] %s / %s" % (etiqueta, disp["familia"], disp["simbolo"]))
                continue

            fi, estrategia, error = _crear_uno(doc, disp, nivel, simbolo)

            if fi is None:
                resultado["dispositivos"].append({
                    "n": idx + 1,
                    "bloque": disp["bloque"],
                    "familia": disp["familia"],
                    "simbolo": disp["simbolo"],
                    "accion": "fallido_creacion",
                    "error": error,
                    "z_objetivo_m": disp["z_abs_m"],
                    "z_real_m": None,
                    "guid": None,
                })
                resultado["fallidos"] += 1
                print(" %s  FALLO: %s" % (etiqueta, str(error)[:72]))
                continue

            z_real = _z_real_m(fi)
            corregido = False
            if z_real is None or abs(z_real - disp["z_abs_m"]) > TOL_M:
                if _mover_a_z(doc, fi, disp["z_abs_m"]):
                    corregido = True
                    z_real = _z_real_m(fi)

            _rotar(doc, fi, disp.get("rotacion_grados", 0.0))

            guid_ok = False
            try:
                p = fi.LookupParameter(LOTE_PARAM)
                if p is not None and not p.IsReadOnly:
                    p.Set(LOTE_GUID)
                    guid_ok = True
            except Exception:
                pass

            ok_z = z_real is not None and abs(z_real - disp["z_abs_m"]) <= TOL_M

            if ok_z:
                if corregido:
                    resultado["creados_con_correccion"] += 1
                else:
                    resultado["creados_ok"] += 1
            else:
                resultado["fallidos"] += 1

            if guid_ok:
                resultado["con_guid"] += 1
            else:
                resultado["sin_guid"] += 1

            est_key = estrategia + ("+move" if corregido else "")
            resultado["por_estrategia"][est_key] = resultado["por_estrategia"].get(est_key, 0) + 1

            try:
                cat = fi.Category.Name if fi.Category else ""
            except Exception:
                cat = ""

            resultado["dispositivos"].append({
                "n": idx + 1,
                "bloque": disp["bloque"],
                "familia": disp["familia"],
                "simbolo": disp["simbolo"],
                "categoria": cat,
                "element_id": _eid_int(fi.Id),
                "unique_id": str(fi.UniqueId),
                "estrategia": estrategia,
                "x_m": disp["x_m"],
                "y_m": disp["y_m"],
                "z_objetivo_m": disp["z_abs_m"],
                "z_real_m": round(z_real, 4) if z_real is not None else None,
                "z_ok": ok_z,
                "corregido_con_move": corregido,
                "guid": LOTE_GUID if guid_ok else None,
                "accion": "creado_ok" if ok_z else "creado_z_erronea",
            })

            print(" %s  %s %s z_obj=%.3f z_real=%s  %s" % (
                etiqueta,
                "OK " if ok_z else "Z! ",
                "GUID" if guid_ok else "----",
                disp["z_abs_m"],
                ("%.3f" % z_real) if z_real is not None else "None",
                est_key,
            ))

        if resultado["fallidos"] > 0:
            print("")
            print(" [ATENCION] %d fallidos -> ROLLBACK. No se deja nada a medias."
                  % resultado["fallidos"])
            t.RollBack()
            resultado["status"] = "ROLLBACK"
            resultado["motivo_aborto"] = "Rollback por %d fallidos" % resultado["fallidos"]
        elif dry_run:
            t.RollBack()
            resultado["status"] = "DRY_RUN_OK"
        else:
            t.Commit()
            resultado["status"] = "OK"

    except Exception as exc:
        try:
            t.RollBack()
        except Exception:
            pass
        resultado["status"] = "ERROR"
        resultado["motivo_aborto"] = "%s: %s" % (type(exc).__name__, str(exc)[:300])
        print("")
        print(" [ERROR] %s" % resultado["motivo_aborto"])

    # --- Simbolos no encontrados --------------------------------------------
    if faltantes_simbolo:
        lista = []
        for (fam, tip), disponibles in faltantes_simbolo.items():
            lista.append({
                "familia_buscada": fam,
                "simbolo_buscado": tip,
                "tipos_disponibles_en_esa_familia": disponibles[:20],
            })
            print(" [SIN SIMBOLO] %s / %s" % (fam, tip))
            print("               disponibles: %s" % (", ".join(disponibles[:10]) or "(ninguno)"))
        resultado["simbolos_no_encontrados"] = lista

    # --- Resumen -------------------------------------------------------------
    print("")
    print("-" * 90)
    print(" RESUMEN")
    print("   status              : %s" % resultado["status"])
    print("   creados ok          : %d" % resultado["creados_ok"])
    print("   creados + corregidos: %d" % resultado["creados_con_correccion"])
    print("   fallidos            : %d" % resultado["fallidos"])
    print("   con GUID            : %d" % resultado["con_guid"])
    print("   sin GUID            : %d" % resultado["sin_guid"])
    print("   por estrategia      : %s" % resultado["por_estrategia"])
    print("-" * 90)
    if resultado["status"] == "OK":
        print(" SIGUIENTE: guardar como V04 y ejecutar F6_VERIFICAR_DISPOSITIVOS_E06_v01.py")
    print("")

    _guardar(resultado)
    return resultado


# ----------------------------------------------------------------------------
# AUTOARRANQUE EN CONSOLA pyRevit
# ----------------------------------------------------------------------------
try:
    _doc = __revit__.ActiveUIDocument.Document
except Exception:
    _doc = None

if _doc is not None:
    crear_dispositivos_e06(_doc, dry_run=False)
else:
    print("[F6] Ejecuta esto dentro de la consola pyRevit de Revit.")
