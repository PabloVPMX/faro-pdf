"""Check the actual native imports in the bundled Qt against resolved DLLs."""
from pathlib import Path
import json
import os
import pefile

root=Path(__file__).resolve().parents[1]
bundle=root/'dist/FaroPDF/_internal'
system=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'
folders=[bundle,bundle/'PySide6',bundle/'shiboken6',system]
cache={}
def read(path):
    if path not in cache:
        pe=pefile.PE(str(path),fast_load=True,max_symbol_exports=100000)
        pe.parse_data_directories(directories=[1,0])
        cache[path]=pe
    return cache[path]

rows=[]
for name in ['PySide6/QtCore.pyd','PySide6/Qt6Core.dll','PySide6/Qt6Gui.dll','PySide6/Qt6Widgets.dll','PySide6/QtPrintSupport.pyd','PySide6/Qt6PrintSupport.dll','PySide6/pyside6.abi3.dll','shiboken6/Shiboken.pyd']:
    for dep in getattr(read(bundle/name),'DIRECTORY_ENTRY_IMPORT',[]):
        dll=dep.dll.decode()
        if dll.lower().startswith(('api-ms-','ext-ms-')):continue
        target=next((folder/dll for folder in folders if (folder/dll).exists()),None)
        if target is None:raise AssertionError('Missing DLL: '+dll)
        exports=getattr(read(target),'DIRECTORY_ENTRY_EXPORT',None)
        symbols=exports.symbols if exports else []
        names={s.name for s in symbols};ordinals={s.ordinal for s in symbols}
        missing=[i.name.decode() if i.name else '#'+str(i.ordinal) for i in dep.imports if (i.name not in names if i.name else i.ordinal not in ordinals)]
        if missing:raise AssertionError(f'{name} / {dll}: {missing}')
        rows.append({'source':name,'dependency':dll,'resolved_in_bundle':target.is_relative_to(bundle),'missing_symbols':[]})
assert not (bundle/'icuuc.dll').exists(), 'Windows ICU must not be shadowed'
report=root/'.cache/validation/native.json'
report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps({'passed':True,'imports':rows},indent=2),encoding='utf8')
print('Native Qt imports verified.')
