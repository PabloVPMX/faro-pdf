from pathlib import Path
import hashlib,json,zipfile

root=Path(__file__).resolve().parents[1]
version='1.1.0'
release=root/'release'
bundle=root/'dist/FaroPDF'
with zipfile.ZipFile(release/f'FaroPDF-{version}-Portable.zip') as archive:
    assert archive.testzip() is None
    names={name for name in archive.namelist() if not name.endswith('/')}
    expected={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
    assert names==expected
    for name in names:
        assert not name.lower().endswith(('.pdf','.pfx','.p12','.key','.pem'))
        assert not name.lower().endswith('/config.json')
        assert hashlib.sha256(archive.read(name)).digest()==hashlib.sha256((bundle/name).read_bytes()).digest()
artifacts=[]
for filename in [f'FaroPDF-{version}-Instalar.exe',f'FaroPDF-{version}-Portable.zip']:
    file=release/filename
    artifacts.append({'file':filename,'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
checks={}
for name in ['source','frozen','native','installer']:
    result=json.loads((root/f'.cache/validation/{name}.json').read_text(encoding='utf-8-sig'))
    assert result['passed'],name
    checks[name]=result
report={'version':version,'unsigned':True,'private_documents_included':False,'portable_integrity_verified':True,'artifacts':artifacts,'checks':checks}
(release/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
(release/'SHA256SUMS.txt').write_text('\n'.join(a['sha256']+'  '+a['file'] for a in artifacts)+'\n',encoding='utf8')
print(json.dumps({'version':version,'checks_passed':list(checks),'artifacts':artifacts},indent=2))
