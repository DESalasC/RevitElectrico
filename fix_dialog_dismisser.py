with open("D:/Work/PROJECTS/RevitElectrico/scripts/register_dialog_dismisser.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: Update imports
old_imports = '''try:
    from pyrevit import revit
    from Autodesk.Revit.UI.Events import DialogBoxShowingEventArgs, TaskDialogShowingEventArgs
except Exception as _imp_err:
    print("[ERROR] Imports fallaron. Este script debe correr dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(_imp_err))
    revit = None'''

new_imports = '''try:
    from pyrevit import revit
    from Autodesk.Revit.UI.Events import DialogBoxShowingEventArgs, TaskDialogShowingEventArgs
except Exception as _imp_err:
    print("[ERROR] Imports fallaron. Este script debe correr dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(_imp_err))
    revit = None'''

content = content.replace(old_imports, new_imports)

# Fix 2: Update register() to also subscribe to UIApplication.TaskDialogShowing
old_register = '''def register():
    """Registra el handler en la aplicacion Revit activa. Idempotente."""
    global _dialog_handler_ref

    if revit is None:
        print("[ERROR] Sin acceso a Revit. Usa pyRevit Python Shell dentro de Revit 2026.")
        return False

    if _dialog_handler_ref is not None:
        print("[INFO] Handler ya estaba activo. No se hace nada.")
        return True

    try:
        from System import EventHandler
        app = revit.doc.Application

        # Crear el delegate explicitamente y guardarlo para evitar GC
        _dialog_handler_ref = EventHandler[DialogBoxShowingEventArgs](_on_dialog_showing)
        app.DialogBoxShowing += _dialog_handler_ref

        print("[OK] Handler registrado: app.DialogBoxShowing")
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
        return False'''

new_register = '''def register():
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
        return False'''

content = content.replace(old_register, new_register)

# Fix 3: Update unregister() to remove both
old_unregister = '''def unregister():
    """Desactiva el handler. Opcional - normalmente basta con cerrar Revit."""
    global _dialog_handler_ref
    if revit is None or _dialog_handler_ref is None:
        print("[INFO] No hay handler activo.")
        return False
    try:
        app = revit.doc.Application
        app.DialogBoxShowing -= _dialog_handler_ref
        _dialog_handler_ref = None
        print("[OK] Handler removido.")
        return True
    except Exception as e:
        print("[ERROR] No pude remover: {}".format(e))
        return False'''

new_unregister = '''def unregister():
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
        return False'''

content = content.replace(old_unregister, new_unregister)

# Fix 4: Add global for taskdialog handler
old_global = '''# Globals: mantener referencias vivas para evitar GC del delegate.
_dialog_handler_ref = None  # delegate EventHandler[DialogBoxShowingEventArgs]'''

new_global = '''# Globals: mantener referencias vivas para evitar GC del delegate.
_dialog_handler_ref = None  # delegate EventHandler[DialogBoxShowingEventArgs]
_taskdialog_handler_ref = None  # delegate EventHandler[TaskDialogShowingEventArgs]'''

content = content.replace(old_global, new_global)

# Fix 5: Update status()
old_status = '''def status():
    """Reporta si el handler esta activo."""
    if _dialog_handler_ref is None:
        print("[STATUS] Inactivo. Ejecuta register() para activarlo.")
    else:
        print("[STATUS] Activo. Log: {}".format(LOG_PATH))'''

new_status = '''def status():
    """Reporta si el handler esta activo."""
    if _dialog_handler_ref is None and _taskdialog_handler_ref is None:
        print("[STATUS] Inactivo. Ejecuta register() para activarlo.")
    else:
        print("[STATUS] Activo. Log: {}".format(LOG_PATH))'''

content = content.replace(old_status, new_status)

with open("D:/Work/PROJECTS/RevitElectrico/scripts/register_dialog_dismisser.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Script updated - now registers both DialogBoxShowing and TaskDialogShowing")