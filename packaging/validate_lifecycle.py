"""Real Windows platform: show maximized, close and wait for OS process exit."""
import json
import os
from pathlib import Path
import subprocess
import sys


def validate(command, report):
    report = Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    modes = {}
    for mode in ('dialogs', 'updates'):
        target = report.with_name(report.stem+'-'+mode+'.json')
        target.unlink(missing_ok=True)
        result = subprocess.run([*command, '--close-probe', mode, str(target)],
            env={**os.environ, 'QT_QPA_PLATFORM': 'windows'},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW)
        data = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        assert result.returncode == 0 and data.get('passed'), (mode, result.returncode, data, result.stderr[-2000:])
        assert data['platform'] == 'windows', data
        modes[mode] = data
    report.write_text(json.dumps({'passed': True, 'real_windows_lifecycle': modes}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    validate(sys.argv[2:], sys.argv[1])
