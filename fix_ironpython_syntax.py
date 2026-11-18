with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace all {**d, ...} with dict(d, ...) or copy+update
# Pattern: results.append({**d, "status": ..., "error": ...})
# Need to handle multiple cases

replacements = [
    # Skip case
    ('results.append({**d, "status": "skip", "error": "Sin mapeo Revit"})',
     'r = dict(d); r["status"] = "skip"; r["error"] = "Sin mapeo Revit"; results.append(r)'),
    # Symbol not found
    ('results.append({**d, "status": "error", "error": "Symbol not found: {} / {}".format(fam, tip)})',
     'r = dict(d); r["status"] = "error"; r["error"] = "Symbol not found: {} / {}".format(fam, tip); results.append(r)'),
    # In _place_on_wall_face error returns
    ('return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",',
     'r = {}; r["device_id"] = dev.get("handle"); r["family"] = dev.get("familia_revit"); r["status"] = "error"; return r'),
    # Actually let me do a more targeted fix - just the 3 places in main loop
]

# Better: just fix the three occurrences in the main function
# 1. skip
content = content.replace(
    'results.append({**d, "status": "skip", "error": "Sin mapeo Revit"})',
    'r = dict(d); r["status"] = "skip"; r["error"] = "Sin mapeo Revit"; results.append(r)'
)

# 2. symbol not found
content = content.replace(
    'results.append({**d, "status": "error", "error": "Symbol not found: {} / {}".format(fam, tip)})',
    'r = dict(d); r["status"] = "error"; r["error"] = "Symbol not found: {} / {}".format(fam, tip); results.append(r)'
)

# 3. The merge at end: results.append({**d, **result})
content = content.replace(
    'results.append({**d, **result})',
    'r = dict(d); r.update(result); results.append(r)'
)

with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed IronPython 2.7 dict unpacking syntax")