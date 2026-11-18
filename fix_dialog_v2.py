with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the three templates properly
# Replace the broken wrapper with correct one

# The correct wrapper using Autodesk.Revit.UI.TaskDialogResult
correct_wrapper = r'''var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS BLOQUEANTES: FailureHandlingOptions + DialogBoxShowing
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {
        // TaskDialogResult.Yes = 6 (Autodesk.Revit.UI)
        e.OverrideResult(6);
    }
});
uiapp.DialogBoxShowing += dlgHandler;

try {'''

correct_end = '''}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

# Fix each template by finding the broken wrapper and replacing
for name in ['CS_FACE_WALL', 'CS_FACE_CEILING', 'CS_LEVEL_BASED']:
    start_marker = f'{name} = r"""'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        continue
    search_start = start_idx + len(start_marker)
    end_idx = content.find('"""', search_start)
    while end_idx != -1:
        if end_idx + 3 < len(content) and content[end_idx + 3] in ('\n', '\r'):
            next_pos = end_idx + 3
            while next_pos < len(content) and content[next_pos] in (' ', '\t', '\n', '\r'):
                next_pos += 1
            if next_pos < len(content) and content[next_pos] in ('\n', '#'):
                break
        end_idx = content.find('"""', end_idx + 1)
    if end_idx == -1:
        continue
    
    template_content = content[search_start:end_idx]
    
    # Remove the broken wrapper (from "var doc = document;" to "try {")
    # Find where the actual template code starts (after try {)
    try_pos = template_content.find('try {')
    if try_pos != -1:
        # Get the part after try {
        actual_code = template_content[try_pos + 5:]  # skip "try {"
    else:
        # Fallback: try to find where actual code starts
        actual_code = template_content
    
    # Also remove the trailing "}" if present (from the finally block)
    if actual_code.rstrip().endswith('}'):
        actual_code = actual_code.rstrip()[:-1].rstrip()
    
    # Remove any leading "var doc = document;" that might be duplicated
    if actual_code.strip().startswith('var doc = document;'):
        actual_code = actual_code[actual_code.index('\n')+1:]
    
    # Build new wrapped template
    new_template = correct_wrapper + '\n' + actual_code + '\n' + correct_end
    
    # Replace
    old_def = content[start_idx:end_idx + 3]
    new_def = f'{name} = r"""{new_template}"""'
    content = content.replace(old_def, new_def)
    print(f"Fixed {name}")

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")