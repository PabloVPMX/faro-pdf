"""Offline update integration checks; never install, network or use private PDFs."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

import update_service as service


class FixtureTransport:
    def __init__(self):
        self.payload = b'MZ'+b'Faro synthetic installer fixture'*100
        self.candidate = service.Candidate('2.0.0', hashlib.sha256(self.payload).hexdigest(), len(self.payload), True)
        self.report = dict(version='2.0.0', unsigned=True, private_documents_included=False,
                           portable_integrity_verified=True,
                           checks={k: {'passed': True} for k in ('source','frozen','native','installer')},
                           artifacts=[dict(file=self.candidate.filename, bytes=len(self.payload), sha256=self.candidate.sha256)])
        self.manifest = json.dumps(self.report).encode()
        self.release = dict(tag_name='v2.0.0', draft=False, prerelease=True, published_at='2026-10-23', assets=[
            dict(name=self.candidate.filename, state='uploaded', size=len(self.payload),
                 digest='sha256:'+self.candidate.sha256, browser_download_url=self.candidate.url),
            dict(name='verification.json', state='uploaded', size=len(self.manifest),
                 digest='sha256:'+hashlib.sha256(self.manifest).hexdigest(),
                 browser_download_url=service.asset_url('2.0.0', 'verification.json'))])
        self.opens = 0
        self.delay = 0

    def read(self, url, limit=0):
        if self.delay:
            time.sleep(self.delay)
        if url == service.API:
            return json.dumps([self.release]).encode()
        assert url == service.asset_url('2.0.0','verification.json')
        return self.manifest

    def open(self, url):
        assert url == self.candidate.url
        self.opens += 1
        return io.BytesIO(self.payload)


def rejects(call):
    try:
        call()
    except service.UpdateError:
        return
    raise AssertionError('An invalid update was accepted')


def check_service(work):
    transport = FixtureTransport()
    candidate = service.find_update('1.1.1', transport)
    assert candidate == transport.candidate
    assert service.find_update('2.0.0', transport) is None
    transport.release['draft'] = True
    assert service.find_update('1.1.1', transport) is None
    transport.release['draft'] = False
    transport.release['assets'][0]['browser_download_url'] = 'https://example.org/payload.exe'
    rejects(lambda: service.find_update('1.1.1', transport))
    transport = FixtureTransport()
    transport.manifest += b' '
    rejects(lambda: service.find_update('1.1.1', transport))
    transport = FixtureTransport()
    for url in ('http://github.com/file','https://evil.example/file','https://github.com@evil.example/file'):
        rejects(lambda: service.checked_https(url))
    rejects(lambda: service.package_path(work, replace(candidate,version='../2.0.0')))
    root = Path(work)/'updater-cache'
    target = service.stage_update(candidate, root, transport)
    assert target.read_bytes() == transport.payload
    assert service.load_staged(root, '1.1.1') == candidate
    assert service.load_staged(root, '2.0.0') is None
    service.stage_update(candidate, root, transport)
    assert transport.opens == 1  # reuse only after a fresh hash check
    target.write_bytes(b'MZ'+b'x'*(candidate.size-2))
    rejects(lambda: service.verify_package(target,candidate))
    service.stage_update(candidate, root, transport)
    cancel = threading.Event(); cancel.set()
    rejects(lambda: service.stage_update(candidate,root,transport,cancel))
    bad = FixtureTransport(); bad.payload = bad.payload[:-10]
    rejects(lambda: service.stage_update(candidate,Path(work)/'truncated',bad))
    assert not list((Path(work)/'truncated').rglob('*.part'))
    failed = FixtureTransport()
    def unavailable(url):
        raise service.UpdateError('Offline')
    failed.open = unavailable
    rejects(lambda: service.stage_update(candidate,Path(work)/'offline',failed))
    assert not list((Path(work)/'offline').rglob('*.part'))
    calls = []
    with patch.object(service,'installed_directory',return_value=Path(work)/'installed'), \
            patch.object(service,'other_instances',return_value=True):
        assert not service.launch_installer(candidate,root,launch=lambda *a,**k:calls.append(a))
    assert not calls
    with patch.object(service,'installed_directory',return_value=None):
        rejects(lambda: service.launch_installer(candidate,root,launch=lambda *a,**k:calls.append(a)))
    with patch.object(service,'installed_directory',return_value=Path(work)/'installed'), \
            patch.object(service,'other_instances',return_value=False):
        assert service.launch_installer(candidate,root,reopen=True,launch=lambda *a,**k:calls.append(a))
    assert len(calls) == 1 and '/FAROREOPEN=1' in calls[0][0]
    assert '/NOCLOSEAPPLICATIONS' in calls[0][0]
    target.write_bytes(b'MZ'+b'x'*(candidate.size-2))
    with patch.object(service,'installed_directory',return_value=Path(work)/'installed'), \
            patch.object(service,'other_instances',return_value=False):
        rejects(lambda: service.launch_installer(candidate,root,launch=lambda *a,**k:calls.append(a)))
    assert len(calls) == 1
    return {'updates_verified_manifest_hash_download_and_tampering': True,
            'updates_cancel_offline_partial_cleanup_and_portable': True,
            'updates_multiple_instances_and_final_hash_guard': True}


def check_updates(window, app, work):
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtTest import QTest
    checks = check_service(work)
    controller = window.updates
    controller.settings = QSettings(str(Path(work)/'update-settings.ini'), QSettings.Format.IniFormat)
    controller.settings.clear()
    controller.root = Path(work)/'qt-update-cache'
    controller.transport = FixtureTransport()
    controller.transport.delay = .08
    controller.installed = True
    controller.version = '1.1.1'
    controller.candidate = None; controller.ready = False
    ticks = []
    timer = QTimer(); timer.setInterval(10); timer.timeout.connect(lambda:ticks.append(True)); timer.start()
    controller.show_dialog()
    deadline = time.monotonic()+8
    while controller.worker and time.monotonic()<deadline:
        QTest.qWait(10)
    timer.stop()
    assert controller.worker is None and controller.ready, controller.message
    assert len(ticks)>2, 'Network work blocked the UI thread'
    assert controller.auto_check.isChecked() and controller.auto_install.isChecked()
    controller.auto_check.setChecked(False)
    assert not controller.option('auto_install')
    controller.auto_install.setChecked(True)
    assert controller.option('auto_check')
    confirm = window.confirm_discard
    try:
        window.confirm_discard = lambda:False
        with patch.object(service,'launch_installer') as launch:
            controller.install_now()
            assert window.isVisible() and not controller.force_install
            launch.assert_not_called()
    finally:
        window.confirm_discard = confirm
    controller.dialog.close(); app.processEvents()
    controller.settings.setValue('updates/auto_install',False)
    controller.settings.setValue('updates/auto_check',False)
    controller.ready = False
    # Closing during a slow request cancels it without destroying a live QThread.
    controller.check()
    assert controller.wait_before_close()
    controller.close_when_idle = False  # test owns the main window
    deadline = time.monotonic()+8
    while controller.worker and time.monotonic()<deadline:
        QTest.qWait(10)
    assert controller.worker is None
    checks['updates_background_responsive_preferences_and_cancelled_document_close'] = True
    return checks


if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='faro-update-checks-') as directory:
        print(json.dumps(check_service(directory),indent=2))
