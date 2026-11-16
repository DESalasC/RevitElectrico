# -*- coding: utf-8 -*-
# RE_F0_VERIFICAR_E06_v02.py
# F0 - Veredicto del lote E06 por UniqueId (RE-P-051), complemento de v01.
#
# Por que existe: v01 busca el GUID del lote en los parametros de las instancias.
# Si el parametro compartido "RevitElectrico_Lote" nunca se vinculo en Revit
# (RE-P-054), el GUID no esta guardado en ningun sitio y v01 responde
# "no_encontrado" sin poder distinguir entre:
#     (a) el lote no se persistio, o
#     (b) el lote existe pero sin marcador.
#
# Este script resuelve la ambiguedad por la via fuerte: el reporte de la corrida
# v13 guardo el UniqueId de cada dispositivo creado. UniqueId es estable entre
# sesiones y copias del mismo documento, asi que su busqueda no depende del
# parametro de lote.
#
# SOLO LECTURA: no crea, no mueve, no borra, no abre transacciones.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_F0_VERIFICAR_E06_v02.py")
#   verificar_e06_por_uniqueid(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
import json
import os
import time

FEET_PER_METER = 3.280839895

REPORTE_V13_RELATIVO = os.path.join("data", "colocar_dispositivos_E06_v13_resultado.json")
SALIDA_RELATIVA = os.path.join("data", "veredicto_e06_v02.json")


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


def _z_m(inst):
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


def _json_seguro(texto):
    """True si el valor se puede serializar con ensure_ascii=True (se valida, no se supone)."""
    try:
        json.dumps(texto, ensure_ascii=True)
        return True
    except Exception:
        return False


def _transliterar(texto):
    """Sustituye vocales acentuadas y enie por ASCII (el json de IronPython no las maneja)."""
    mapa = {
        u"\u00e1": "a", u"\u00e9": "e", u"\u00ed": "i", u"\u00f3": "o", u"\u00fa": "u",
        u"\u00c1": "A", u"\u00c9": "E", u"\u00cd": "I", u"\u00d3": "O", u"\u00da": "U",
        u"\u00f1": "n", u"\u00d1": "N", u"\u00fc": "u", u"\u00dc": "U",
    }
    try:
        partes = []
        for caracter in texto:
            partes.append(mapa.get(caracter, caracter))
        return "".join(partes)
    except Exception:
        return texto


def _a_texto(valor):
    """Deja el valor serializable: decodifica si se puede y verifica el resultado con json.

    En IronPython 2.7 fallaron como discriminadores ``hasattr(decode)``,
    ``isinstance(bytes)``, ``tipo_texto = unicode`` y la sonda ``encode('ascii')``.
    Por eso ya no se clasifica el tipo: se decodifica y se comprueba con la propia
    biblioteca json; si aun asi no pasa, se usa ``repr`` (siempre ASCII).
    """
    texto = valor
    for codec in ("utf-8", "cp1252", "latin-1"):
        try:
            texto = valor.decode(codec)
            break
        except Exception:
            texto = valor
            continue

    if not _json_seguro(texto):
        texto = _transliterar(texto)
    if not _json_seguro(texto):
        try:
            texto = repr(valor)
            for prefijo in ("b'", 'b"', "u'", 'u"'):
                if texto[:2] == prefijo:
                    texto = texto[2:]
                    break
            if texto.endswith(("'", '"')):
                texto = texto[:-1]
        except Exception:
            texto = "valor_no_serializable"

    try:
        if texto[:1] == u"\ufeff":
            texto = texto[1:]
    except Exception:
        pass
    return texto


def _normalizar(objeto):
    """Recorre dict/list y garantiza texto unicode antes de serializar."""
    if isinstance(objeto, dict):
        salida = {}
        for clave, valor in objeto.items():
            salida[_a_texto(clave)] = _normalizar(valor)
        return salida
    if isinstance(objeto, (list, tuple)):
        return [_normalizar(item) for item in objeto]
    return _a_texto(objeto)


def cargar_declarados(ruta_reporte):
    """Lee el reporte v13 y devuelve las entradas creadas con su UniqueId."""
    with open(ruta_reporte, "r") as fh:
        datos = json.load(fh)
    detalle = datos.get("detalle") or datos.get("results") or []
    declarados = []
    for item in detalle:
        if item.get("accion") != "creado":
            continue
        uid = item.get("unique_id")
        if not uid:
            continue
        declarados.append({
            "handle": item.get("handle"),
            "nombre": item.get("nombre"),
            "unique_id": uid,
            "z_esperada_m": item.get("z_m"),
            "host_id_declarado": item.get("host_id"),
        })
    return datos.get("lote_guid"), declarados


def evaluar(total, encontrados):
    """Veredicto segun cuantos UniqueId declarados siguen existiendo."""
    if total == 0:
        return "sin_datos", "El reporte no contiene UniqueId de dispositivos creados."
    if encontrados == 0:
        return "no_persistido", "Ninguno de los {n} UniqueId declarados existe en este documento: el lote nunca se guardo.".format(n=total)
    if encontrados == total:
        return "persistido", "Los {n} UniqueId declarados existen en este documento.".format(n=total)
    return "parcial", "Existen {e} de {n} UniqueId declarados; el lote quedo incompleto.".format(e=encontrados, n=total)


def verificar_e06_por_uniqueid(doc, reporte_json=None, salida_json=None):
    """Resuelve por UniqueId si el lote E06 de v13 vive en el documento activo."""
    ruta_reporte = _ruta(REPORTE_V13_RELATIVO, reporte_json)
    ruta_salida = _ruta(SALIDA_RELATIVA, salida_json)

    if ruta_reporte is None or ruta_salida is None:
        print("ERROR: falta REVITELECTRICO_ROOT. Pasa reporte_json y salida_json explicitos.")
        return {"error": "rutas_no_definidas"}

    print("=== F0 - VERIFICAR E06 POR UNIQUEID (RE-P-051) ===")
    print("Fecha    : {t}".format(t=time.strftime("%Y-%m-%d %H:%M:%S")))
    print("Documento: {t}".format(t=doc.Title))
    print("Reporte  : {r}".format(r=ruta_reporte))
    print("Modo     : SOLO LECTURA")

    lote_guid, declarados = cargar_declarados(ruta_reporte)
    print("Lote GUID: {g}".format(g=lote_guid))
    print("Declarados con UniqueId: {n}".format(n=len(declarados)))

    detalle = []
    encontrados = 0
    for item in declarados:
        uid = item["unique_id"]
        inst = None
        try:
            inst = doc.GetElement(uid)
        except Exception:
            inst = None
        if inst is None:
            detalle.append({
                "handle": item["handle"],
                "nombre": item["nombre"],
                "unique_id": uid,
                "encontrado": False,
            })
            continue
        encontrados += 1
        z = _z_m(inst)
        detalle.append({
            "handle": item["handle"],
            "nombre": item["nombre"],
            "unique_id": uid,
            "encontrado": True,
            "element_id": _eid(inst.Id),
            "familia": _familia(inst),
            "tipo": _tipo(inst),
            "z_m": z,
            "z_esperada_m": item["z_esperada_m"],
            "delta_z_m": round(z - item["z_esperada_m"], 4) if (z is not None and item["z_esperada_m"] is not None) else None,
            "host_id": _host_id(inst),
        })

    veredicto, motivo = evaluar(len(declarados), encontrados)

    resumen = {
        "version": "2.0",
        "proyecto": "RE",
        "fase": "F0",
        "pendiente": "RE-P-051",
        "documento": doc.Title,
        "lote_guid": lote_guid,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metodo": "UniqueId (independiente del parametro de lote)",
        "declarados": len(declarados),
        "encontrados": encontrados,
        "veredicto": veredicto,
        "motivo": motivo,
        "detalle": detalle,
    }

    print("Encontrados por UniqueId : {e} de {n}".format(e=encontrados, n=len(declarados)))
    print("Veredicto                : {v}".format(v=veredicto))
    print("Motivo                   : {m}".format(m=motivo))

    directorio = os.path.dirname(ruta_salida)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(ruta_salida, "w") as fh:
        json.dump(_normalizar(resumen), fh, ensure_ascii=True, indent=2, sort_keys=True)

    print("JSON guardado en: {r}".format(r=ruta_salida))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        verificar_e06_por_uniqueid(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
