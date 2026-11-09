# -*- coding: utf-8 -*-
"""
RE_INVENTARIO_APARTAMENTOS_v01.py
=================================
Genera el inventario maestro de los 16 bloques DXF de apartamentos
para el procedimiento de tablero-anclaje (Apartamento Tipo nn).

Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python: 3.12 (script externo, SIN Revit, SIN modificacion al modelo)

OBJETIVO:
  1. Leer cada archivo DXF de apartamento en 3.-Proceso\\.
  2. Identificar el bloque padre (apartamento) y su punto de insercion.
  3. Identificar el bloque hijo del TABLERO/PANEL (capa ELEC-POWER-PANEL o
     nombre TB-Parcial) dentro de cada apartamento.
  4. Extraer los dispositivos hijos (tomas, interruptores, lamparas,
     ventiladores) como entidades separadas con nombre, capa, coordenadas
     absolutas en DXF, rotacion y altura local de montaje.
  5. Separar los marcadores de conductor (no se modelan como FamilyInstance).
  6. Generar data\\inventario_apartamentos_v01.json con la estructura
     definida en procedimiento_tablero_anclaje_apartamentos_v01.md.

ESTE SCRIPT ES SOLO LECTURA: no toca el modelo Revit, no borra, no modifica,
no crea FamilyInstance. Solo genera el plan de modelado.

Convencion de nombrado de salida:
  - Identificador de apartamento: APT-<tipo>-<nro>-P<piso>
  - Identificador de tablero-ancla: TAB-<tipo>-<nro>-P<piso>
  - z_revit en JSON = altura local de montaje (m), nunca Z absoluta.
    Z_absoluta = nivel.Elevation + altura_local (convertir a pies para Revit).

Uso:
    python RE_INVENTARIO_APARTAMENTOS_v01.py
    (lee desde $REVITELECTRICO_ROOT o ruta relativa al proyecto)
"""

import json
import os
import re
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuracion de rutas (variable de entorno o relativa al proyecto)
# ---------------------------------------------------------------------------

def _obtener_root():
    """Obtiene la raiz del proyecto desde $REVITELECTRICO_ROOT o relativa."""
    env = os.environ.get("REVITELECTRICO_ROOT")
    if env:
        return env
    # Si se ejecuta desde src/fase-1-contexto/, subir dos niveles para llegar
    # a la raiz del proyecto (T5-SantaMarta).
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    except NameError:
        return os.path.abspath(".")


ROOT = _obtener_root()
DIR_DXF = os.path.join(ROOT, "3.-Proceso")
DIR_DATA = os.path.join(ROOT, "data")
PATH_INSERTOS = os.path.join(
    ROOT, "3.-Proceso", "_prueba_modelado", "inserts_apartamentos_v3.json"
)
PATH_SALIDA = os.path.join(DIR_DATA, "inventario_apartamentos_v01.json")

# Nivel destino para todos los apartamentos (según CLAUDE.md del proyecto)
NIVEL_REVIT = "Piso 5"
ELEVACION_NIVEL_M = 43.3727  # metros, confirmado en V00

# Tableros oficiales confirmados por el usuario (2026-10-28)
TABLEROS_OFICIALES = {
    "F 01": "TAB-F-01-P5",
    "F 02": "TAB-F-02-P5",
}

# Capas y nombres que identifican al tablero/panel dentro de un apartamento
CAPAS_TABLERO = {"ELEC-POWER-PANEL", "Tablero"}
NOMBRES_TABLERO = {"TB-Parcial", "TB-01", "TF 01", "TF 02"}

# Marcadores de conductor: no se modelan como FamilyInstance, solo se registran
MARCADORES_CONDUCTOR = {
    "1FTN", "1TNR", "1FTNR", "2FT2N", "1FTN2R", "1TN2R", "1FTR",
}

# Tabla de alias para normalizar nombres de apartamentos (ortografia del DXF)
ALIAS_APARTAMENTO = {
    "Apatamento": "Apartamento",
    "Apatamentos": "Apartamentos",
}


# ---------------------------------------------------------------------------
# Utilidades de normalizacion
# ---------------------------------------------------------------------------

def normalizar_nombre_apartamento(nombre):
    """Normaliza inconsistencias de ortografia en nombres de apartamentos."""
    resultado = nombre
    for alias, correcto in ALIAS_APARTAMENTO.items():
        resultado = resultado.replace(alias, correcto)
    return resultado.strip()


def extraer_tipo_nro(nombre_normalizado):
    """
    Extrae el tipo (letra) y numero de apartamento de un nombre normalizado.
    Ejemplos:
      "Apartamento Tipo F 02" -> ("F", "02")
      "Apartamentos Tipo F 18 y 04" -> ("F", "18 y 04")
      "Apartamento Tipo E2 21" -> ("E2", "21")
    Devuelve (tipo, nro) o (None, None) si no se puede parsear.
    """
    m = re.search(r"Tipo\s+([A-Z0-9]+)\s+([0-9]+(?:\s*y\s*[0-9]+)?)",
                  nombre_normalizado, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


def identificador_apartamento(tipo, nro, piso=5):
    """Construye el identificador de apartamento: APT-<tipo>-<nro>-P<piso>."""
    return "APT-{}-{}-P{}".format(tipo, nro, piso)


def identificador_tablero(tipo, nro, piso=5):
    """Construye el identificador de tablero-ancla: TAB-<tipo>-<nro>-P<piso>."""
    return "TAB-{}-{}-P{}".format(tipo, nro, piso)


# ---------------------------------------------------------------------------
# Lectura de DXF (solo lectura, sin dependencias de Revit)
# ---------------------------------------------------------------------------

def _leer_lineas_dxf(ruta_dxf):
    """Lee un DXF y retorna lista de lineas (texto crudo, sin modificar)."""
    try:
        with open(ruta_dxf, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except IOError as exc:
        print("  ERROR no se pudo leer {}: {}".format(ruta_dxf, exc))
        return None


def _extraer_bloques_dxf_simple(ruta_dxf):
    """
    Extrae bloques y entidades de un DXF usando un parser ligero por lineas.

    Este es un parser simplificado que recorre la estructura de pares de codigo
    de grupo DXF. Identifica:
      - BLOCK / ENDBLK (definiciones de bloque)
      - INSERT (instancias de bloque, con coordenadas y nombre)
      - Entidades sueltas dentro de bloques (para detectar el tablero por capa)

    Retorna un diccionario con:
      - bloques_padre: lista de definiciones de bloque con nombre y punto base
      - inserts: lista de INSERT con nombre_bloque, x, y, rotacion, capa
      - capas: set de capas encontradas
    """
    lineas = _leer_lineas_dxf(ruta_dxf)
    if lineas is None:
        return None

    bloques_padre = []
    inserts = []
    capas = set()

    i = 0
    n = len(lineas)
    en_bloque = False
    nombre_bloque_actual = None
    punto_base = None
    entidad_actual = None
    capa_actual = "0"
    # Estado para leer entidades ATTRIB (atributos de un bloque INSERT)
    leyendo_atributo = False
    atributo_actual = {}

    def _guardar_entidad():
        """Guarda la entidad INSERT actual si tiene nombre de bloque."""
        nonlocal entidad_actual
        if entidad_actual is not None and entidad_actual.get("nombre_bloque"):
            # Asociar el bloque padre (definicion de bloque que la contiene)
            entidad_actual["bloque_padre"] = nombre_bloque_actual or "MODELO"
            inserts.append(dict(entidad_actual))
        entidad_actual = None

    while i < n:
        codigo = lineas[i].strip()
        valor = lineas[i + 1].strip() if i + 1 < n else ""
        i += 2
        if i > n:
            break

        if codigo == "0":
            # Codigo de grupo 0: indica el tipo de entidad o seccion
            if valor == "BLOCK":
                _guardar_entidad()
                en_bloque = True
                nombre_bloque_actual = None
                punto_base = None
                leyendo_atributo = False
                atributo_actual = {}
            elif valor == "ENDSEC":
                # Fin de seccion: guardar cualquier entidad pendiente y reiniciar
                _guardar_entidad()
                en_bloque = False
                leyendo_atributo = False
                atributo_actual = {}
            elif valor == "ENDBLK":
                _guardar_entidad()
                en_bloque = False
                leyendo_atributo = False
                atributo_actual = {}
                if nombre_bloque_actual and punto_base is not None:
                    bloques_padre.append({
                        "nombre": nombre_bloque_actual,
                        "punto_base": punto_base,
                    })
                nombre_bloque_actual = None
                punto_base = None
            elif valor == "INSERT":
                # Nueva entidad INSERT (dentro o fuera de una definicion de bloque)
                _guardar_entidad()
                entidad_actual = {"nombre_bloque": None, "x": 0.0, "y": 0.0,
                                  "rotacion": 0.0, "capa": "0",
                                  "tiene_atributos": False,
                                  "atributos": {}}
                capa_actual = "0"
                leyendo_atributo = False
                atributo_actual = {}
            elif valor == "ATTRIB":
                # Entidad ATTRIB (atributo de un bloque INSERT). Se asocia al
                # INSERT inmediatamente anterior si este tiene tiene_atributos=True.
                if entidad_actual is not None and entidad_actual.get("tiene_atributos"):
                    leyendo_atributo = True
                    atributo_actual = {}
                else:
                    leyendo_atributo = False
                    atributo_actual = {}
            # Otros codigos de grupo 0 (SECTION, ENDSEC, EOF, TABLE, etc.)
            # se ignoran; no afectan el estado del parser.
        elif leyendo_atributo:
            if codigo == "2":
                atributo_actual["nombre"] = valor
            elif codigo == "1":
                atributo_actual["valor"] = valor
            elif codigo == "0":
                # Fin del ATTRIB: guardar el atributo leído en el INSERT actual
                if entidad_actual is not None and atributo_actual.get("nombre"):
                    entidad_actual.setdefault("atributos", {})[
                        atributo_actual["nombre"]] = atributo_actual.get("valor", "")
                leyendo_atributo = False
                atributo_actual = {}
                # No consumimos este codigo 0 como nueva entidad; se procesa en la
                # siguiente iteracion (el valor 'valor' es el tipo de la nueva entidad)
                # Retrocedemos una posicion para que el ciclo lo procese como codigo 0.
                i -= 2
            continue
        elif en_bloque and codigo == "2":
            # Nombre del bloque (codigo 2 dentro de BLOCK)
            nombre_bloque_actual = valor
        elif en_bloque and codigo == "10":
            # Punto base X del bloque
            try:
                if punto_base is None:
                    punto_base = [float(valor), 0.0, 0.0]
                else:
                    punto_base[0] = float(valor)
            except ValueError:
                pass
        elif en_bloque and codigo == "20":
            try:
                if punto_base is None:
                    punto_base = [0.0, float(valor), 0.0]
                else:
                    punto_base[1] = float(valor)
            except ValueError:
                pass
        elif entidad_actual is not None:
            if codigo == "66":
                # Código 66=1 en INSERT indica que la entidad tiene atributos asociados
                try:
                    entidad_actual["tiene_atributos"] = (int(valor) == 1)
                except ValueError:
                    pass
            elif codigo == "2":
                entidad_actual["nombre_bloque"] = valor
            elif codigo == "8":
                capa_actual = valor
                entidad_actual["capa"] = valor
                capas.add(valor)
            elif codigo == "10":
                try:
                    entidad_actual["x"] = float(valor)
                except ValueError:
                    pass
            elif codigo == "20":
                try:
                    entidad_actual["y"] = float(valor)
                except ValueError:
                    pass
            elif codigo == "50":
                try:
                    entidad_actual["rotacion"] = float(valor)
                except ValueError:
                    pass

    # Si queda un atributo sin cerrar al final del archivo, lo guardamos
    if entidad_actual is not None and atributo_actual.get("nombre"):
        entidad_actual.setdefault("atributos", {})[
            atributo_actual["nombre"]] = atributo_actual.get("valor", "")

    _guardar_entidad()

    return {
        "bloques_padre": bloques_padre,
        "inserts": inserts,
        "capas": sorted(capas),
    }


# ---------------------------------------------------------------------------
# Procesamiento por apartamento
# ---------------------------------------------------------------------------

def _cargar_insertos_apartamentos():
    """Carga el mapeo de insertos de apartamentos desde inserts_apartamentos_v3.json."""
    if not os.path.exists(PATH_INSERTOS):
        print("  AVISO: no se encontro {}".format(PATH_INSERTOS))
        return {}
    try:
        with open(PATH_INSERTOS, "r", encoding="utf-8", errors="replace") as f:
            datos = json.load(f)
        mapeo = {}
        for item in datos:
            nombre = normalizar_nombre_apartamento(item.get("nombre", ""))
            mapeo[nombre] = {
                "x_dxf": item.get("x_dxf"),
                "y_dxf": item.get("y_dxf"),
                "x_revit": item.get("x_revit"),
                "y_revit": item.get("y_revit"),
            }
        return mapeo
    except (IOError, ValueError) as exc:
        print("  ERROR cargando insertos: {}".format(exc))
        return {}


def _es_tablero(nombre_bloque, capa):
    """Determina si un bloque hijo es el tablero/panel del apartamento."""
    if capa in CAPAS_TABLERO:
        return True
    if nombre_bloque and any(t in nombre_bloque for t in NOMBRES_TABLERO):
        return True
    return False


def _es_marcador_conductor(nombre_bloque):
    """Determina si un bloque hijo es un marcador de conductor (no se modela)."""
    return nombre_bloque in MARCADORES_CONDUCTOR


def _altura_local_por_capa(capa):
    """
    Estima la altura local de montaje (m) segun la capa del dispositivo.
    Valores segun el analisis del piloto F 02:
      - 0.3 m: tomas (ELEC-APPL-TOMAS, ELEC-APPL-NETWORD)
      - 1.1 m: interruptores (ELEC-APPL-ILUM con familia M_Interruptor)
      - 1.2 m: tablero (ELEC-POWER-PANEL)
      - 2.6 m: techo/luminarias/ventiladores (techo)
    Estos son estimados; el script de modelado de Fase 6 usara el mapa v3 real.
    """
    if capa == "ELEC-POWER-PANEL" or capa == "Tablero":
        return 1.2
    if capa in ("ELEC-APPL-TOMAS", "ELEC-APPL-NETWORD"):
        return 0.3
    if "ILUM" in capa or "VENT" in capa:
        return 2.6
    if "TOMAS" in capa or "NETWORD" in capa:
        return 0.3
    # Valor por defecto conservador (muro)
    return 0.3


def _anfitrion_por_capa(capa):
    """Determina el anfitrión (muro/ceiling) segun la capa."""
    if capa == "ELEC-POWER-PANEL" or capa == "Tablero":
        return "muro"
    if "ILUM" in capa:
        return "ceiling"
    return "muro"


def _estimar_simbolo(nombre_bloque, capa):
    """Estima el simbolo de Revit segun nombre de bloque y capa (heuristica)."""
    nb = (nombre_bloque or "").upper()
    if "GFCI" in nb or "T-D" in nb or "T-GFCI" in nb:
        return "GFCI"
    if "TIMBRE" in nb or "I-S" in nb or "F-CONTROL" in nb:
        return "Estándar"
    if "CAMPANA" in nb:
        return "Puerta motorizada"
    if "VENT" in nb:
        return "Estándar"
    if "Bala" in nb or "LED" in nb:
        if "22W" in nb:
            return "MOUNTING RING trimless, 064-1906700"
        if "10W" in nb:
            return "MOUNTING RING trimless, 064-1906300"
        if "13W" in nb:
            return "MOUNTING RING trimless, 064-1906500"
        return "MOUNTING RING trimless"
    if "Toma" in nb or "TEL" in nb or "NET" in nb:
        return "Estándar"
    if "Panel" in nb or "TB" in nb:
        return "EPB25-304C"
    return "Estándar"


def _estimar_familia(nombre_bloque, capa, simbolo):
    """Estima la familia de Revit segun nombre, capa y simbolo."""
    nb = (nombre_bloque or "").upper()
    if "Panel" in nb or "TB" in nb:
        if "Distrib" in nb or "EPB" in simbolo.upper():
            return "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN"
        return "M_Panel"
    if "GFCI" in nb or "T-D" in nb:
        return "M_Toma doble"
    if "T-GFCI" in nb:
        return "M_Toma doble"
    if "TEL" in nb or "NET" in nb or "TAKE" in nb:
        return "M_Toma simple"
    if "EXT" in nb:
        return "M_Toma resistente a la intemperie"
    if "TIMBRE" in nb or "I-S" in nb or "F-CONTROL" in nb:
        return "M_Interruptor bipolar"
    if "CAMPANA" in nb:
        return "M_Interruptor"
    if "VENT" in nb:
        return "M_Ventilador"
    if "Bala" in nb or "LED" in nb:
        return "COMBO MOUNTING RING"
    return "M_Toma doble"


def procesar_apartamento(nombre_dxf, mapeo_insertos, ruta_dxf=None):
    """
    Procesa un archivo DXF de apartamento y retorna su entrada de inventario.

    Si ruta_dxf se indica, se usa directamente; de lo contrario se busca en
    DIR_DXF/nombre_dxf (ruta por defecto del proyecto). Esto permite probar
    con DXF temporales generados en tmp_path durante los tests.
    """
    if ruta_dxf is None:
        ruta_dxf = os.path.join(DIR_DXF, nombre_dxf)
    if not os.path.exists(ruta_dxf):
        print("  ERROR: no se encontro {}".format(ruta_dxf))
        return None

    print("  Procesando DXF: {}".format(nombre_dxf))
    parse = _extraer_bloques_dxf_simple(ruta_dxf)
    if parse is None:
        return None

    nombre_normalizado = normalizar_nombre_apartamento(
        os.path.splitext(nombre_dxf)[0])
    tipo, nro = extraer_tipo_nro(nombre_normalizado)
    if tipo is None:
        print("  AVISO: no se pudo parsear tipo/nro de '{}'".format(
            nombre_normalizado))
        tipo = "?"
        nro = "?"

    id_ap = identificador_apartamento(tipo, nro)
    id_tab = identificador_tablero(tipo, nro)

    insert_info = mapeo_insertos.get(nombre_normalizado, {})
    insert_padre = {
        "x": insert_info.get("x_dxf", 0.0),
        "y": insert_info.get("y_dxf", 0.0),
    }

    dispositivos_hijos = []
    marcadores_conductor = []
    tablero = None

    for ins in parse["inserts"]:
        nombre_bloque = ins.get("nombre_bloque") or ""
        capa = ins.get("capa") or "0"
        x = ins.get("x", 0.0)
        y = ins.get("y", 0.0)
        rot = ins.get("rotacion", 0.0)

        if _es_marcador_conductor(nombre_bloque):
            marcadores_conductor.append({
                "nombre_bloque_hijo": nombre_bloque,
                "capa": capa,
                "x_dxf": round(x, 4),
                "y_dxf": round(y, 4),
                "rotacion": rot,
                "orden": len(marcadores_conductor),
            })
            continue

        if _es_tablero(nombre_bloque, capa):
            if tablero is None:
                atributos = ins.get("atributos", {}) or {}
                nombre_panel = atributos.get("TABLERO", "")
                tablero = {
                    "nombre_bloque_hijo": nombre_bloque,
                    "capa": capa,
                    "x_dxf": round(x, 4),
                    "y_dxf": round(y, 4),
                    "z_local_m": 1.2,
                    "z_absoluta_m": round(ELEVACION_NIVEL_M + 1.2, 4),
                    "familia_revit": _estimar_familia(
                        nombre_bloque, capa, _estimar_simbolo(nombre_bloque, capa)),
                    "simbolo": _estimar_simbolo(nombre_bloque, capa),
                    "anfitrion": _anfitrion_por_capa(capa),
                    "rotacion": rot,
                    "identificador_ancla": id_tab,
                    "orden": len(dispositivos_hijos),
                    # Atributo DXF del panel (para validacion en Revit: Properties > General > Panel Name)
                    "tiene_atributo_panel": bool(nombre_panel),
                    "nombre_panel_atributo": nombre_panel,
                    "panel_name_revit_sugerido": nombre_panel if nombre_panel else id_tab,
                }
            continue

        # Dispositivo hijo ordinario (toma, interruptor, lampara, ventilador)
        dispositivos_hijos.append({
            "nombre_bloque_hijo": nombre_bloque,
            "capa": capa,
            "x_dxf": round(x, 4),
            "y_dxf": round(y, 4),
            "z_local_m": _altura_local_por_capa(capa),
            "familia_revit": _estimar_familia(
                nombre_bloque, capa, _estimar_simbolo(nombre_bloque, capa)),
            "simbolo": _estimar_simbolo(nombre_bloque, capa),
            "anfitrion": _anfitrion_por_capa(capa),
            "rotacion": rot,
            "orden": len(dispositivos_hijos),
        })

    entrada = {
        "nombre_normalizado": nombre_normalizado,
        "nombre_dxf_original": nombre_dxf,
        "tipo": tipo,
        "nro": nro,
        "piso": 5,
        "nivel_revit": NIVEL_REVIT,
        "elevacion_nivel_m": ELEVACION_NIVEL_M,
        "identificador_apartamento": id_ap,
        "identificador_tablero": id_tab,
        "insert_padre_dxf": insert_padre,
        "insert_revit": {
            "x": insert_info.get("x_revit"),
            "y": insert_info.get("y_revit"),
        },
        "tablero": tablero,
        "dispositivos_hijos": dispositivos_hijos,
        "marcadores_conductor": marcadores_conductor,
        "offset_calculado": {
            "offset_x": None,
            "offset_y": None,
            "nota": "pendiente de colocacion manual del tablero en Revit (Paso 1)",
        },
        "total_dispositivos_hijos": len(dispositivos_hijos),
        "total_marcadores": len(marcadores_conductor),
        "tiene_tablero": tablero is not None,
    }
    return entrada


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("RE_INVENTARIO_APARTAMENTOS_v01 — Inventario de bloques DXF")
    print("Proyecto: RevitElectrico / T5-SantaMarta / Fase 6")
    print("Python 3.12 — SOLO LECTURA, no toca el modelo Revit")
    print("=" * 60)
    print("Raiz del proyecto: {}".format(ROOT))
    print("Directorio DXF:    {}".format(DIR_DXF))
    print("Salida:            {}".format(PATH_SALIDA))
    print("")

    if not os.path.isdir(DIR_DXF):
        print("ERROR: no existe el directorio DXF: {}".format(DIR_DXF))
        return 1

    os.makedirs(DIR_DATA, exist_ok=True)

    mapeo_insertos = _cargar_insertos_apartamentos()
    print("Insertos de apartamentos cargados: {}".format(len(mapeo_insertos)))
    print("")

    # Buscar archivos DXF de apartamentos en el directorio.
    # Se normaliza el nombre antes de filtrar para capturar archivos con
    # ortografia inconsistente (ej. "Apatamento" en lugar de "Apartamento").
    archivos_dxf = sorted([
        f for f in os.listdir(DIR_DXF)
        if f.lower().endswith(".dxf")
        and "apartamento" in normalizar_nombre_apartamento(f).lower()
    ])
    print("Archivos DXF de apartamentos encontrados: {}".format(len(archivos_dxf)))
    for f in archivos_dxf:
        print("  - {}".format(f))
    print("")

    apartamentos = []
    for nombre_dxf in archivos_dxf:
        entrada = procesar_apartamento(nombre_dxf, mapeo_insertos)
        if entrada is not None:
            apartamentos.append(entrada)
            print("  [OK] {} | dispositivos={} | marcadores={} | tablero={}".format(
                entrada["nombre_normalizado"],
                entrada["total_dispositivos_hijos"],
                entrada["total_marcadores"],
                "SI" if entrada["tiene_tablero"] else "NO"))

    inventario = {
        "version": "v01",
        "proyecto": "RevitElectrico - T5-SantaMarta",
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nivel_revit": NIVEL_REVIT,
        "elevacion_nivel_m": ELEVACION_NIVEL_M,
        "total_apartamentos": len(apartamentos),
        "apartamentos": apartamentos,
        "regla_datum": "z_revit = altura local (m); Z_absoluta = nivel.Elevation + z_revit (convertir a pies para Revit)",
        "tableros_oficiales": TABLEROS_OFICIALES,
    }

    with open(PATH_SALIDA, "w", encoding="utf-8") as f:
        json.dump(inventario, f, indent=2, ensure_ascii=False)

    print("")
    print("=" * 60)
    print("Inventario guardado en: {}".format(PATH_SALIDA))
    print("Total apartamentos: {}".format(len(apartamentos)))
    total_disp = sum(a["total_dispositivos_hijos"] for a in apartamentos)
    total_marc = sum(a["total_marcadores"] for a in apartamentos)
    con_tablero = sum(1 for a in apartamentos if a["tiene_tablero"])
    print("Total dispositivos hijos: {}".format(total_disp))
    print("Total marcadores de conductor: {}".format(total_marc))
    print("Apartamentos con tablero identificado: {}".format(con_tablero))
    print("=" * 60)

    # Advertencia: apartamentos sin tablero identificado
    sin_tablero = [a["nombre_normalizado"] for a in apartamentos
                   if not a["tiene_tablero"]]
    if sin_tablero:
        print("")
        print("AVISO: los siguientes apartamentos NO tienen tablero identificado:")
        for nombre in sin_tablero:
            print("  - {}".format(nombre))
        print("Revisar manualmente que capa/nombre usa el tablero en esos DXF.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
