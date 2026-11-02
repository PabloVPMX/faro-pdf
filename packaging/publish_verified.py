"""Publish verified artifacts using GITHUB_TOKEN; never replace public assets.

The existing tag, rather than release.target_commitish, identifies the source.
GitHub checks workflow-write permission against target_commitish even when the
tag exists. Use the default branch for that metadata after checking the tag.
"""
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile


class GitHub:
    def __init__(self, repository, token):
        self.repository, self.token = repository, token

    def request(self, method, path, data=None):
        url = 'https://api.github.com/repos/'+self.repository+path
        headers = {'Authorization': 'Bearer '+self.token, 'Accept': 'application/vnd.github+json',
                   'User-Agent': 'Faro-PDF-verified-publisher', 'Content-Type': 'application/json'}
        request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and method == 'GET':
                return None
            raise RuntimeError(f'GitHub rejected {method} {path}: HTTP {error.code}') from None

    def upload(self, release_id, path):
        url = ('https://uploads.github.com/repos/'+self.repository+'/releases/'+str(release_id)+
               '/assets?name='+urllib.parse.quote(path.name, safe=''))
        with path.open('rb') as stream:
            request = urllib.request.Request(url, data=stream, method='POST', headers={
                'Authorization': 'Bearer '+self.token, 'User-Agent': 'Faro-PDF-verified-publisher',
                'Content-Type': 'application/octet-stream', 'Content-Length': str(path.stat().st_size)})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(folder):
    report = json.loads((folder/'verification.json').read_text(encoding='utf-8'))
    version = report['version']
    assert re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', version), 'Invalid release version'
    assert report['unsigned'] is True and report['private_documents_included'] is False
    assert report['portable_integrity_verified'] is True
    for name in ('source', 'frozen', 'native', 'installer', 'update-handoff',
                 'update-handoff-frozen', 'lifecycle_source', 'lifecycle_frozen', 'lifecycle_installed'):
        assert report['checks'][name]['passed'] is True, name
    packages = {f'FaroPDF-{version}-Instalar.exe', f'FaroPDF-{version}-Portable.zip'}
    names = packages | {'verification.json', 'SHA256SUMS.txt'}
    assert {p.name for p in folder.iterdir()} == names, 'Unexpected release files'
    assert all(p.is_file() and not p.is_symlink() for p in folder.iterdir())
    assert len(report['artifacts']) == 2 and {a['file'] for a in report['artifacts']} == packages
    hashes = {name: digest(folder/name) for name in names}
    for artifact in report['artifacts']:
        path = folder/artifact['file']
        assert path.stat().st_size == artifact['bytes'] and hashes[path.name] == artifact['sha256']
    sums = (folder/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()
    assert len(sums) == 2 and set(sums) == {hashes[n]+'  '+n for n in packages}
    with zipfile.ZipFile(folder/f'FaroPDF-{version}-Portable.zip') as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            parts = name.replace('\\', '/').split('/')
            assert '..' not in parts and not name.startswith(('/', '\\')) and ':' not in name
            assert not name.lower().endswith(('.pdf', '.pfx', '.p12', '.key', '.pem'))
            assert parts[-1].lower() != 'config.json'
    return version, {name: {'size': (folder/name).stat().st_size, 'digest': 'sha256:'+hashes[name]}
                     for name in names}


def tag_commit(api, tag):
    reference = api.request('GET', '/git/ref/tags/'+tag)
    if reference is None:
        return None
    obj = reference['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        assert obj['type'] == 'tag', 'Unsupported tag target'
        obj = api.request('GET', '/git/tags/'+obj['sha'])['object']
    raise AssertionError('Too many nested annotated tags')


def workflows_tree(api, sha):
    rows = api.request('GET', '/contents/.github?ref='+sha) or []
    return next((row['sha'] for row in rows if row['path'] == '.github/workflows'), None)


def check_assets(assets, expected):
    assert len(assets) == len(expected) and {a['name'] for a in assets} == set(expected), 'Release assets differ'
    for asset in assets:
        assert asset['state'] == 'uploaded', asset['name']
        assert all(asset.get(key) == value for key, value in expected[asset['name']].items()), asset['name']


def publish(api, folder, run_id, expected_sha):
    assert str(run_id).isdecimal() and re.fullmatch('[a-f0-9]{40}', expected_sha)
    run = api.request('GET', '/actions/runs/'+str(run_id))
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert run['head_sha'] == expected_sha and run['head_repository']['full_name'] == api.repository
    assert run['name'] == 'Build and verify Windows' and run['path'] == '.github/workflows/build-windows.yml'
    assert run['event'] in ('push', 'workflow_dispatch'), 'PR builds cannot be published'
    version, expected = validate(folder)
    tag = 'v'+version
    repo = api.request('GET', '')
    branch = repo['default_branch']
    target = tag_commit(api, tag)
    if target is None:
        head = api.request('GET', '/git/ref/heads/'+urllib.parse.quote(branch, safe=''))['object']['sha']
        assert workflows_tree(api, expected_sha) == workflows_tree(api, head), (
            'The selected build has different workflows from the default branch. '
            'Build the current default branch before publishing a new tag.')
        api.request('POST', '/git/refs', {'ref': 'refs/tags/'+tag, 'sha': expected_sha})
        target = tag_commit(api, tag)
    assert target == expected_sha, 'The release tag does not point at the verified build'

    release = api.request('GET', '/releases/tags/'+tag)
    if release and not release['draft']:
        # Check everything BEFORE any write. A rerun must never clobber files.
        check_assets(release['assets'], expected)
        if release['target_commitish'] != branch:
            release = api.request('PATCH', '/releases/'+str(release['id']), {'target_commitish': branch})
        result = 'already-published-and-verified'
    else:
        if release is None:
            notes = api.request('GET', '/contents/RELEASE_NOTES.md?ref='+expected_sha)
            body = base64.b64decode(notes['content']).decode('utf-8')
            release = api.request('POST', '/releases', {'tag_name': tag, 'target_commitish': branch,
                'name': 'Faro PDF '+version, 'body': body, 'draft': True, 'prerelease': True})
        present = {a['name']: a for a in release['assets']}
        assert set(present) <= set(expected), 'Unexpected draft assets'
        for name in sorted(expected):
            if name not in present:
                present[name] = api.upload(release['id'], folder/name)
            check_assets([present[name]], {name: expected[name]})
        release = api.request('PATCH', '/releases/'+str(release['id']), {'target_commitish': branch, 'draft': False})
        result = 'published'
    assert tag_commit(api, tag) == expected_sha, 'Tag changed during publication'
    release = api.request('GET', '/releases/tags/'+tag)
    assert release['draft'] is False
    check_assets(release['assets'], expected)
    return {'version': version, 'tag': tag, 'source_sha': expected_sha, 'result': result, 'url': release['html_url']}


if __name__ == '__main__':
    api = GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    result = publish(api, Path('release'), os.environ['VERIFIED_RUN_ID'], os.environ['EXPECTED_SHA'])
    print(json.dumps(result), flush=True)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f"version={result['version']}\ntag={result['tag']}\n")
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
        output.write(f"## Faro PDF {result['version']}\n\n[{result['result']}]({result['url']})\n\n"
                     f"Verified source: `{result['source_sha']}`. All four public assets match SHA-256.\n")
