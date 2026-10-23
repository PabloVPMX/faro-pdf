"""Build our small vector-style icon and collect dependency notices."""
from pathlib import Path
from importlib.metadata import distribution
import sys
import shutil
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
assets = ROOT / 'assets'
assets.mkdir(exist_ok=True)
image = Image.new('RGBA', (256, 256))
d = ImageDraw.Draw(image)
d.rounded_rectangle((8, 8, 248, 248), radius=48, fill='#142b3a')
d.polygon([(110, 104), (146, 104), (170, 210), (86, 210)], fill='white')
d.rectangle((101, 74, 155, 109), fill='#4fe0cc')
d.polygon([(94, 72), (128, 40), (162, 72)], fill='white')
d.polygon([(92, 86), (30, 60), (30, 112)], fill='#4fe0cc')
d.polygon([(164, 86), (226, 60), (226, 112)], fill='#4fe0cc')
d.rectangle((116, 171, 140, 210), fill='#087f7b')
image.save(assets / 'faro.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
notices = assets / 'licenses'
notices.mkdir(exist_ok=True)
for name in ('LICENSE','LICENSE-LGPL-3.0.txt','LICENSE-GPL-3.0.txt','THIRD_PARTY_NOTICES.md'):
    shutil.copyfile(ROOT/name,notices/name)
if (ROOT/'licenses/qt').exists():
    shutil.copytree(ROOT/'licenses/qt',notices/'Qt',dirs_exist_ok=True)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    (notices / 'Python-LICENSE.txt').write_bytes(python_license.read_bytes())
packages = ['PySide6-Essentials', 'shiboken6', 'pypdfium2', 'fonttools', 'Pillow', 'numpy', 'pypdf']
manifest = ['Faro PDF 1.1.1 - Dependencias de terceros', '',
            'Las bibliotecas mantienen sus respectivas licencias. Qt se distribuye como DLLs reemplazables.',
            'Esta aplicacion no incluye fuentes de Windows ni documentos de prueba.', '']
for package in packages:
    dist = distribution(package)
    manifest.append(f'{dist.metadata["Name"]} {dist.version}')
    for f in dist.files or []:
        if any(word in str(f).lower() for word in ('license', 'copying', 'notice')) and dist.locate_file(f).is_file():
            destination = notices / package / str(f).replace('../','').replace('..\\','')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(dist.locate_file(f).read_bytes())
(notices / 'DEPENDENCIAS.txt').write_text('\n'.join(manifest), encoding='utf-8')
print('Icono y licencias preparados.')
