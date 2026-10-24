from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
# Do not resolve Qt's Windows ICU imports against Poppler/libheif or other
# tools on the calling terminal's PATH. Only app dependencies and Windows.
os.environ['PATH'] = os.pathsep.join([
    str(Path(sys.base_prefix)), str(Path(sys.executable).parent),
    str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32'),
    str(Path(os.environ.get('SystemRoot', 'C:/Windows'))),
])
a = Analysis(
    [str(root / 'app.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('pypdfium2_raw'),
    datas=[(str(root/'assets'), 'assets'), (str(root/'packaging'/'INSTALAR.txt'), '.'),
           (str(root/'.cache'/'ocr-runtime'), 'ocr')]
          + collect_data_files('pypdfium2_raw') + collect_data_files('pypdfium2'),
    hiddenimports=collect_submodules('fontTools') + collect_submodules('pypdf') + ['packaging_smoke'],
    excludes=['tkinter','matplotlib','scipy','IPython','pytest','winrt','ocr_local'],
    noarchive=False,
)
# These are inbox Windows components on our supported Windows 10/11 target.
# In particular, Poppler's ICU exports versioned names, incompatible with Qt's
# unversioned imports from the Windows ICU API of the same filename.
foreign_names={'icuuc.dll','icudt78.dll','ucrtbase.dll'}
allowed_roots=[root.resolve(),Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve(),
               Path(os.environ.get('SystemRoot','C:/Windows')).resolve()]
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in foreign_names
            and not Path(entry[0]).name.lower().startswith('api-ms-win-')
            and any(Path(entry[1]).resolve().is_relative_to(allowed) for allowed in allowed_roots)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FaroPDF', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root/'assets'/'faro.ico'), version=str(root/'packaging'/'version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FaroPDF')
