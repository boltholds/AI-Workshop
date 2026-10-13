# Ghidra Jython 2.7 headless post-script. Metadata only; no decompiled code.
#@category AIWorkshop
import json

args = getScriptArgs()
if len(args) != 1:
    raise ValueError('output path is required')

program = currentProgram
functions = []
count = 0
for func in program.getFunctionManager().getFunctions(True):
    count += 1
    if len(functions) < 10000:
        functions.append({
            'name': func.getName(),
            'entry_point': str(func.getEntryPoint()),
            'external': bool(func.isExternal()),
            'thunk': bool(func.isThunk()),
        })

summary = {
    'program_name': program.getName(),
    'executable_format': program.getExecutableFormat(),
    'language_id': str(program.getLanguageID()),
    'function_count': count,
    'functions_truncated': count > len(functions),
    'functions': functions,
}
with open(args[0], 'w') as output:
    json.dump(summary, output)
