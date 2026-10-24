"""Fetch pinned upstream OCR binaries/models; extract without installing them."""
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
import pefile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'ocr-downloads'
DEST = ROOT / '.cache' / 'ocr-runtime'
MODELS = '87416418657359cb625c412a48b6e1d6d41c29bd'
MODEL_HASHES = {'eng': '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
                'spa': '6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464'}


def fetch(name, url, digest=None):
    path = CACHE / name
    if not path.exists() or (digest and hashlib.sha256(path.read_bytes()).hexdigest() != digest):
        request = urllib.request.Request(url, headers={'User-Agent': 'FaroPDF-build'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if digest and hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('SHA-256 incorrecto: ' + name)
        path.write_bytes(data)
    return path


def run(*args):
    result = subprocess.run([str(a) for a in args], capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace') or result.stdout.decode('utf-8', 'replace'))


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    seven = fetch('7zr.exe', 'https://github.com/ip7z/7zip/releases/download/26.05/7zr.exe',
                  '9bf582b894dfa665f852d7e9112b02290a1c303c2d95a21fcdc41ffcb03143b7')
    package = fetch('7z2605-x64.exe', 'https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe',
                    'fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0')
    extractor = CACHE / '7zip'
    run(seven, 'x', package, '-y', '-o' + str(extractor))
    installer = fetch('tesseract-5.5.3.exe',
        'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe',
        'bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4')
    extracted = CACHE / 'tesseract'
    run(extractor / '7z.exe', 'x', installer, '-y', '-o' + str(extracted))
    # Keep the isolated CLI and its DLLs together, never in Qt's search path.
    files = {p.name.lower(): p for p in extracted.iterdir() if p.is_file()}
    needed = set(); pending = ['tesseract.exe']
    while pending:
        name = pending.pop()
        if name in needed: continue
        needed.add(name)
        binary = pefile.PE(str(files[name]), fast_load=True)
        binary.parse_data_directories(directories=[1, 13])
        for dependency in getattr(binary, 'DIRECTORY_ENTRY_IMPORT', []) + getattr(binary, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
            dependency = dependency.dll.decode().lower()
            if dependency in files: pending.append(dependency)
        binary.close()
    for name in needed: shutil.copy2(files[name], DEST / files[name].name)
    for path in DEST.glob('*.dll'):
        if path.name.lower() not in needed: path.unlink()
    tessdata = DEST / 'tessdata'
    tessdata.mkdir(exist_ok=True)
    for lang in ('spa', 'eng'):
        model = fetch(lang + '.traineddata',
                      f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{MODELS}/{lang}.traineddata',
                      MODEL_HASHES[lang])
        shutil.copy2(model, tessdata / model.name)
    # Tesseract's output configurations/font are required for text-only PDFs.
    for name in ('configs', 'pdf.ttf'):
        source = extracted / 'tessdata' / name
        if source.is_dir(): shutil.copytree(source, tessdata / name, dirs_exist_ok=True)
        elif source.is_file(): shutil.copy2(source, tessdata / name)
    licenses = DEST / 'licenses'
    licenses.mkdir(exist_ok=True)
    for path in extracted.rglob('*'):
        if path.is_file() and ('license' in path.name.lower() or path.name.lower().startswith(('copying', 'notice'))):
            relative = path.relative_to(extracted)
            target = licenses / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    shutil.copy2(ROOT / 'licenses' / 'OCR-NOTICES.md', licenses / 'OCR-NOTICES.md')
    shutil.copytree(ROOT / 'licenses' / 'ocr', licenses / 'upstream', dirs_exist_ok=True)
    for name in ('LICENSE-LGPL-3.0.txt', 'LICENSE-GPL-3.0.txt'):
        shutil.copy2(ROOT / name, licenses / name)
    run(DEST / 'tesseract.exe', '--version')
    manifest = {'engine': 'Tesseract 5.5.3', 'models_commit': MODELS,
                'files': {p.relative_to(DEST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in DEST.rglob('*') if p.is_file() and p.name != 'manifest.json'}}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'OCR preparado: {sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file()) / 1000000:.1f} MB')


if __name__ == '__main__':
    main()
