with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

# Helper to wrap C# template with dialog suppression
def wrap_cs_template(template, template_name):
    """Wrap a C# template with DialogBoxShowing handler and FailureHandlingOptions."""
    
    # Remove the return statement at the end to wrap everything
    # Find the last return statement
    lines = template.split('\n')
    
    # Build the wrapper
    wrapper_start = f'''var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS BLOQUEANTES: FailureHandlingOptions + DialogBoxShowing
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {{
        e.OverrideResult((int)System.Windows.Forms.DialogResult.Yes);
    }}
}});
uiapp.DialogBoxShowing += dlgHandler;

try {{'''

    wrapper_end = '''}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

    # Remove the outer "var doc = document;" and insert our wrapper
    # The template already starts with "var doc = document;"
    template_without_doc = template
    if template_without_doc.startswith('var doc = document;'):
        template_without_doc = template_without_doc[len('var doc = document;'):]
    
    # Also need to fix the return statements to use the wrapped context
    # The template uses return "JSON" directly - we keep that but it's inside try now
    # Need to ensure the return is inside the try block
    
    return wrapper_start + template_without_doc + '\n' + wrapper_end


# Apply to all three templates
for name in ['CS_FACE_WALL', 'CS_FACE_CEILING', 'CS_LEVEL_BASED']:
    # Find the template definition
    start_marker = f'{name} = r"""'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f"WARNING: {name} not found")
        continue
    
    # Find the closing """
    # The template ends with """\n\n (triple quote then double newline)
    search_start = start_idx + len(start_marker)
    end_idx = content.find('"""', search_start)
    while end_idx != -1:
        # Check if it's the real end (followed by \n\n or \n#)
        if end_idx + 3 < len(content) and content[end_idx + 3] in ('\n', '\r'):
            # Check next non-whitespace char
            next_pos = end_idx + 3
            while next_pos < len(content) and content[next_pos] in (' ', '\t', '\n', '\r'):
                next_pos += 1
            if next_pos < len(content) and content[next_pos] in ('\n', '#'):
                break
        end_idx = content.find('"""', end_idx + 1)
    
    if end_idx == -1:
        print(f"WARNING: closing delimiter for {name} not found")
        continue
    
    # Extract the template content (without the r""" and """)
    template_content = content[search_start:end_idx]
    
    # Wrap it
    wrapped = wrap_cs_template(template_content, name)
    
    # Replace in content
    old_def = content[start_idx:end_idx + 3]
    new_def = f'{name} = r"""{wrapped}"""'
    content = content.replace(old_def, new_def)
    print(f"Wrapped {name} with dialog suppression")

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")