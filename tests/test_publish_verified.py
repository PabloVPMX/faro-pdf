"""Offline regression for source identity, permissions and repeat publication."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).resolve().parents[1]/'packaging/publish_verified.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
SHA = 'a'*40
HEAD = 'b'*40


class FakeGitHub:
    repository = 'PabloVPMX/faro-pdf'

    def __init__(self, expected):
        self.calls = []
        self.tag = SHA
        self.annotated = False
        self.same_workflows = False
        self.expected = expected
        self.run = dict(status='completed', conclusion='success', head_sha=SHA,
            head_repository={'full_name': self.repository}, name='Build and verify Windows',
            path='.github/workflows/build-windows.yml', event='push')
        self.release = dict(id=42, tag_name='v1.6.3', target_commitish=SHA, draft=False,
            html_url='https://github.com/'+self.repository+'/releases/tag/v1.6.3',
            assets=[dict(name=n, state='uploaded', **v) for n, v in expected.items()])

    def request(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        if method == 'GET':
            if path.startswith('/actions/runs/'):
                return copy.deepcopy(self.run)
            if path == '':
                return {'default_branch': 'main'}
            if path == '/git/ref/tags/v1.6.3':
                return {'object': dict(type='tag' if self.annotated else 'commit', sha=self.tag)} if self.tag else None
            if path == '/git/tags/'+SHA:
                return {'object': {'type': 'commit', 'sha': SHA}}
            if path == '/git/ref/heads/main':
                return {'object': {'sha': HEAD}}
            if path.startswith('/contents/.github?ref='):
                same = self.same_workflows or path.endswith(HEAD)
                return [{'path': '.github/workflows', 'sha': 'c'*40 if same else 'd'*40}]
            if path == '/releases/tags/v1.6.3':
                return copy.deepcopy(self.release)
            if path.startswith('/contents/RELEASE_NOTES.md?ref='):
                return {'content': base64.b64encode(b'Faro PDF 1.6.3 fixture').decode()}
        elif method == 'POST' and path == '/git/refs':
            assert data == {'ref': 'refs/tags/v1.6.3', 'sha': SHA}
            self.tag = data['sha']
            return {}
        elif method == 'POST' and path == '/releases':
            assert self.tag == SHA and data['target_commitish'] == 'main'
            self.release = dict(id=42, assets=[], html_url='https://github.com/'+self.repository+'/releases/tag/v1.6.3', **data)
            return copy.deepcopy(self.release)
        elif method == 'PATCH' and path == '/releases/42':
            assert self.tag == SHA and data['target_commitish'] == 'main'
            self.release.update(data)
            return copy.deepcopy(self.release)
        raise AssertionError((method, path, data))

    def upload(self, release_id, path):
        assert self.release['draft'] and release_id == 42
        self.calls.append(('UPLOAD', path.name, None))
        asset = dict(name=path.name, state='uploaded', **self.expected[path.name])
        self.release['assets'].append(asset)
        return asset


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        installer = self.folder/'FaroPDF-1.6.3-Instalar.exe'
        installer.write_bytes(b'MZ synthetic installer')
        portable = self.folder/'FaroPDF-1.6.3-Portable.zip'
        with zipfile.ZipFile(portable, 'w') as archive:
            archive.writestr('FaroPDF.exe', b'MZ synthetic reader')
        names = ('source', 'frozen', 'native', 'installer', 'update-handoff', 'update-handoff-frozen',
                 'lifecycle_source', 'lifecycle_frozen', 'lifecycle_installed')
        artifacts = [dict(file=p.name, bytes=p.stat().st_size, sha256=publisher.digest(p)) for p in (installer, portable)]
        report = dict(version='1.6.3', unsigned=True, private_documents_included=False,
            portable_integrity_verified=True, checks={name: {'passed': True} for name in names}, artifacts=artifacts)
        (self.folder/'verification.json').write_text(json.dumps(report), encoding='utf-8')
        (self.folder/'SHA256SUMS.txt').write_text(''.join(a['sha256']+'  '+a['file']+'\n' for a in artifacts))
        self.expected = publisher.validate(self.folder)[1]
        self.api = FakeGitHub(self.expected)

    def publish(self):
        return publisher.publish(self.api, self.folder, '1234', SHA)

    def assert_no_writes(self):
        self.assertFalse([c for c in self.api.calls if c[0] != 'GET'])

    def test_old_source_tag_stays_exact_while_release_uses_default_branch(self):
        result = self.publish()
        self.assertEqual(result['source_sha'], SHA)
        self.assertEqual(self.api.tag, SHA)
        self.assertEqual(self.api.release['target_commitish'], 'main')
        writes = [c for c in self.api.calls if c[0] != 'GET']
        self.assertEqual(writes, [('PATCH', '/releases/42', {'target_commitish': 'main'})])
        self.assertFalse(self.api.same_workflows)  # Reproduces the original permission mismatch.

    def test_repeated_publication_preserves_assets_and_makes_no_more_writes(self):
        self.publish()
        original = copy.deepcopy(self.api.release)
        self.api.calls.clear()
        self.assertEqual(self.publish()['result'], 'already-published-and-verified')
        self.assertEqual(self.api.release, original)
        self.assert_no_writes()

    def test_wrong_tag_rejected_before_release_changes(self):
        self.api.tag = HEAD
        with self.assertRaisesRegex(AssertionError, 'tag does not point'):
            self.publish()
        self.assert_no_writes()

    def test_annotated_tag_is_peeled(self):
        self.api.annotated = True
        self.assertEqual(self.publish()['source_sha'], SHA)

    def test_modified_public_asset_is_never_replaced(self):
        self.api.release['assets'][0]['digest'] = 'sha256:'+'0'*64
        with self.assertRaises(AssertionError):
            self.publish()
        self.assert_no_writes()

    def test_failed_fork_or_pr_build_rejected(self):
        for key, value in [('conclusion', 'failure'), ('head_sha', HEAD), ('event', 'pull_request'),
                           ('head_repository', {'full_name': 'somebody/fork'})]:
            with self.subTest(key=key):
                api = FakeGitHub(self.expected)
                api.run[key] = value
                with self.assertRaises(AssertionError):
                    publisher.publish(api, self.folder, '1234', SHA)
                self.assertFalse([c for c in api.calls if c[0] != 'GET'])

    def test_new_tag_with_different_workflows_fails_before_write(self):
        self.api.tag = None
        self.api.release = None
        with self.assertRaisesRegex(AssertionError, 'different workflows'):
            self.publish()
        self.assert_no_writes()

    def test_new_release_tags_verified_source_then_publishes_complete_draft(self):
        self.api.tag = None
        self.api.release = None
        self.api.same_workflows = True
        self.assertEqual(self.publish()['result'], 'published')
        self.assertEqual(self.api.tag, SHA)
        publisher.check_assets(self.api.release['assets'], self.expected)
        self.assertFalse(self.api.release['draft'])
        self.assertEqual(self.api.release['target_commitish'], 'main')

    def test_draft_recovery_uploads_only_missing_files(self):
        self.api.release['draft'] = True
        self.api.release['assets'] = self.api.release['assets'][:2]
        self.publish()
        self.assertEqual(len([c for c in self.api.calls if c[0] == 'UPLOAD']), 2)

    def test_tampered_local_package_rejected_before_write(self):
        (self.folder/'FaroPDF-1.6.3-Instalar.exe').write_bytes(b'MZ changed contents')
        with self.assertRaises(AssertionError):
            self.publish()
        self.assert_no_writes()


if __name__ == '__main__':
    unittest.main()
