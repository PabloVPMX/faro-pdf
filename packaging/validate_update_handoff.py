"""Real inbox helper: wait for parent exit, defer launches, reject tampering."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_service as service
import windows_lifetime as lifetime


def wait_for(condition, timeout=30):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(.05)
    raise AssertionError('Timed out waiting for update handoff')


def validate(report, command):
    work = report.parent/('update handoff acentos á '+str(os.getpid()))
    work.mkdir(parents=True)
    package = work/'99.0.0/FaroPDF-99.0.0-Instalar.exe'
    package.parent.mkdir()
    package.write_bytes(b'MZ'+b'Not an executable: offline update fixture'*200)
    parent_command = [*command, '--update-handoff-probe', str(work)] if command else [sys.executable, __file__, '--parent', str(work)]
    process = subprocess.Popen(parent_command,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    helper_handle = None
    api = lifetime.kernel()
    try:
        wait_for(lambda: (work/'parent.ready').exists() or process.poll() is not None)
        assert process.poll() is None, process.stderr.read().decode('utf-8', 'replace')
        config = json.loads(next(work.glob('handoff-*.json')).read_text())
        helper_pid = int(Path(config['ready']).read_text(encoding='ascii').strip())
        from ctypes import wintypes as W
        api.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        api.OpenProcess.restype = W.HANDLE
        api.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        api.WaitForSingleObject.restype = W.DWORD
        helper_handle = api.OpenProcess(0x100000, False, helper_pid)
        assert helper_handle
        status = lambda: json.loads((work/'install-status.json').read_text(encoding='utf-8-sig'))
        wait_for(lambda: (work/'install-status.json').exists())
        assert status()['state'] == 'waiting'
        assert lifetime.update_guard() is None, 'Second updater was allowed'
        env = {**os.environ, 'LOCALAPPDATA': str(work/'fake-local-appdata')}
        blocked = work/'blocked.json'
        blocked_command = [*command, '--close-probe', 'dialogs', str(blocked)] if command else [sys.executable, __file__, '--blocked', str(blocked)]
        result = subprocess.run(blocked_command,
            env=env, timeout=30, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        if command:
            assert not blocked.exists(), 'Frozen startup passed the update gate'
        else:
            assert json.loads(blocked.read_text()) == {'blocked': True, 'qt_loaded': False}
        assert list((work/'fake-local-appdata/Faro PDF/updates/pending-open').glob('*.json'))
        # Mutate only after the parent has verified the package and reserved the
        # update. It must still be untouched while its closing reader is alive.
        package.write_bytes(b'MZ'+b'x'*(package.stat().st_size-2))
        time.sleep(.25)
        assert status()['state'] == 'waiting' and process.poll() is None
        assert not (work/'install.log').exists()
        (work/'release-parent').touch()
        assert process.wait(timeout=30) == 0, process.stderr.read().decode('utf-8', 'replace')
        wait_for(lambda: status()['state'] == 'failed')
        assert 'verificacion' in status()['detail'], status()
        assert api.WaitForSingleObject(helper_handle, 30000) == 0, 'Updater helper remained alive'
        assert not lifetime.exists(lifetime.UPDATE_MUTEX), 'Update gate survived helper exit'
        assert not lifetime.exists(lifetime.READER_MUTEX), 'Reader marker survived process exit'
        report.write_text(json.dumps(dict(passed=True, waits_for_os_exit=True,
            blocks_new_readers_before_qt=True, preserves_open_request=True,
            serializes_installers=True, verifies_hash_after_exit=True,
            helper_exits_and_releases_gate=True), indent=2), encoding='utf-8')
    finally:
        (work/'release-parent').touch()
        if process.poll() is None:
            process.wait(timeout=30)
        if helper_handle:
            api.CloseHandle(helper_handle)


if __name__ == '__main__':
    mode = sys.argv[1]
    destination = Path(sys.argv[2]).resolve()
    if mode == '--parent':
        from update_checks import handoff_parent
        handoff_parent(destination)
    elif mode == '--blocked':
        allowed = lifetime.enter_reader()
        destination.write_text(json.dumps(dict(blocked=not allowed, qt_loaded='PySide6' in sys.modules)))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        validate(destination, sys.argv[3:])
