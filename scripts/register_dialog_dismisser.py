# -*- coding: utf-8 -*-
"""
register_dialog_dismisser.py
============================
Registra un handler para Application.DialogBoxShowing en Revit 2026 que
auto-cierra los dialogos modales seguros, evitando que bloqueen el thread
principal y por tanto el puerto 8080 del plugin mcp-servers-for-revit.

Sin esto, cualquier TaskDialog que Revit levante durante una llamada MCP
(advertencia, "family already loaded", constraint warning, etc.) bloquea
la respuesta al cliente (OpenClaw, Claude Desktop, etc.) hasta que un
humano haga clic.

COMO USAR
---------
1. Abre Revit 2026 con un documento .rvt cargado.
2. Abre pyRevit Python Shell.
3. Ejecuta:
       exec(open(r"D:\\Work\\Scripts\\register_dialog_dismisser.py").read())

El handler queda activo hasta que cierres Revit. No necesitas repetirlo.

LOG
---
Cada dialogo (cerrado o dejado en pantalla) se registra como una linea JSON
en:
    D:\\Work\\PROJECTS\\RevitElectrico\\data\\dismissed_dialogs.jsonl

ESTRATEGIA
----------
- Dialogos con palabras clave destructivas (delete, purge, overwrite,
  detach, etc.) -> se dejan mostrar (no se auto-cierran).
- Dialogos de warning o info -> se cierran con OK (result_id=1).
- Todo lo demas -> se cierra con Cancel/Close (result_id=0).
- Para cancelar el handler: cerrar Revit, o ejecutar unregister().

LIMITACIONES
------------
- NO captura dialogos del sistema operativo (file pickers nativos,
  MessageBox de Win32 fuera de Revit). Para esos se necesita un watcher
  externo con UI Automation (PowerShell). Mira dismiss_revit_dialogs.ps1.
- NO captura excepciones no controladas que revientan Revit. Eso es
  crash, no dialog.
"""

import json
import os
import time

# Imports Revit / pyRevit
# En pyRevit IronPython estos resuelven automaticamente
try:
    from pyrevit import revit
    from Autodesk.Revit.UI.Events import DialogBoxShowingEventArgs, TaskDialogShowingEventArgs
except Exception as _imp_err:
    print("[ERROR] Imports fallaron. Este script debe correr dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(_imp_err))
    revit = None


# Configuracion
LOG_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dismissed_dialogs.jsonl"

# Palabras que indican un dialogo potencialmente destructivo.
# Si alguna aparece en el mensaje o dialog_id, NO se auto-cierra.
DESTRUCTIVE_KEYWORDS = [
    "delete", "eliminar", "remove", "borrar",
    "purge", "limpiar",
    "overwrite", "sobrescribir",
    "destroy", "destruir",
    "detach", "desconectar",
    "drop", "descartar",
    "lost", "perder",
]


# Globals: mantener referencias vivas para evitar GC del delegate.
_dialog_handler_ref = None  # delegate EventHandler[DialogBoxShowingEventArgs]
_taskdialog_handler_ref = None  # delegate EventHandler[TaskDialogShowingEventArgs]


def _safe_log(entry):
    """Append de una linea JSON al log. Nunca lanza."""
    try:
        log_dir = os.path.dirname(LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[WARN] No pude escribir log a {}: {}".format(LOG_PATH, e))


def _is_destructive(message, dialog_id):
    text = (str(message) + " " + str(dialog_id)).lower()
    for kw in DESTRUCTIVE_KEYWORDS:
        if kw in text:
            return True
    return False


def _pick_result(args):
    """Determina el resultado seguro para OverrideResult.

    Retorna:
        int -> usar este ID con args.OverrideResult(int)
        None -> NO auto-cerrar (dejar mostrar el dialogo)
    """
    message = str(getattr(args, "Message", "") or "")
    dialog_id = str(getattr(args, "DialogId", "") or "")

    if _is_destructive(message, dialog_id):
        return None

    # Heuristica: warnings e infos se cierran con OK (1)
    text = (message + " " + dialog_id).lower()
    if "warning" in text or "info" in text or "informaci" in text:
        return 1

    # Resto: cerrar/cancelar (0 suele funcionar como cerrar generico)
    return 0


def _on_dialog_showing(sender, args):
    """Handler principal. Se llama antes de mostrar cualquier dialogo Revit."""
    try:
        message = str(getattr(args, "Message", "") or "")
        dialog_id = str(getattr(args, "DialogId", "") or "")
        title = ""
        if hasattr(args, "Title"):
            try:
                title = str(getattr(args, "Title", "") or "")
            except Exception:
                title = ""

        result_id = _pick_result(args)

        if result_id is None:
            # Dialogo destructivo: dejar que se muestre para que un humano decida
            entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "TaskDialog" if title else "DialogBox",
                "title": title,
                "message": message[:500],
                "dialog_id": dialog_id,
                "result_id": None,
                "action": "let_show",
            }
            _safe_log(entry)
            print("[let-show] {} | dialog_id={}".format(title or "(no title)", dialog_id))
            return

        # Cerrar el dialogo simulando el boton elegido
        args.OverrideResult(result_id)

        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "TaskDialog" if title else "DialogBox",
            "title": title,
            "message": message[:500],
            "dialog_id": dialog_id,
            "result_id": result_id,
            "action": "dismissed",
        }
        _safe_log(entry)
        print("[dismissed] {} | dialog_id={} | result={}".format(
            title or dialog_id or "(no title)", dialog_id, result_id
        ))
    except Exception as e:
        # Nunca relanzar: un handler que lanza rompe el evento para todos
        print("[ERROR] dismiss fallo: {}".format(e))


def register():
    """Registra el handler en la aplicacion Revit activa. Idempotente."""
    global _dialog_handler_ref, _taskdialog_handler_ref

    if revit is None:
        print("[ERROR] Sin acceso a Revit. Usa pyRevit Python Shell dentro de Revit 2026.")
        return False

    if _dialog_handler_ref is not None and _taskdialog_handler_ref is not None:
        print("[INFO] Handlers ya estaban activos. No se hace nada.")
        return True

    try:
        from System import EventHandler
        # Application.DialogBoxShowing (regular dialogs)
        app = revit.doc.Application
        _dialog_handler_ref = EventHandler[DialogBoxShowingEventArgs](_on_dialog_showing)
        app.DialogBoxShowing += _dialog_handler_ref

        # UIApplication.TaskDialogShowing (TaskDialogs like "Delete duplicate instances")
        uiapp = revit.app  # pyRevit provides revit.app = UIApplication
        _taskdialog_handler_ref = EventHandler[TaskDialogShowingEventArgs](_on_dialog_showing)
        uiapp.TaskDialogShowing += _taskdialog_handler_ref

        print("[OK] Handler registrado: app.DialogBoxShowing")
        print("[OK] Handler registrado: uiapp.TaskDialogShowing")
        print("[OK] Auto-dismisser activo hasta que cierres Revit.")
        print("[OK] Log de dialogos: {}".format(LOG_PATH))
        print("")
        print("[INFO] Palabras clave destructivas (NO auto-cierra):")
        for kw in DESTRUCTIVE_KEYWORDS:
            print("       - {}".format(kw))
        print("")
        print("[INFO] Para desactivar manualmente: ejecuta unregister()")
        return True
    except Exception as e:
        print("[ERROR] No pude registrar el handler: {}".format(e))
        return False


def unregister():
    """Desactiva el handler. Opcional - normalmente basta con cerrar Revit."""
    global _dialog_handler_ref, _taskdialog_handler_ref
    if revit is None:
        print("[INFO] No hay acceso a Revit.")
        return False
    try:
        removed = False
        if _dialog_handler_ref is not None:
            app = revit.doc.Application
            app.DialogBoxShowing -= _dialog_handler_ref
            _dialog_handler_ref = None
            removed = True
        if _taskdialog_handler_ref is not None:
            uiapp = revit.app
            uiapp.TaskDialogShowing -= _taskdialog_handler_ref
            _taskdialog_handler_ref = None
            removed = True
        if removed:
            print("[OK] Handlers removidos.")
        else:
            print("[INFO] No habia handlers activos.")
        return removed
    except Exception as e:
        print("[ERROR] No pude remover: {}".format(e))
        return False


def status():
    """Reporta si el handler esta activo."""
    if _dialog_handler_ref is None and _taskdialog_handler_ref is None:
        print("[STATUS] Inactivo. Ejecuta register() para activarlo.")
    else:
        print("[STATUS] Activo. Log: {}".format(LOG_PATH))


# Ejecutar al cargar
register()
