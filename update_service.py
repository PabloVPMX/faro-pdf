"""Public GitHub releases, bounded downloads and installed-edition updates.

HTTPS and GitHub asset digests authenticate the download source and integrity.
They do not turn an unsigned Windows executable into an Authenticode-signed one.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit

REPOSITORY = 'PabloVPMX/faro-pdf'
API = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=30'
HOME = f'https://github.com/{REPOSITORY}'
MAX_PACKAGE = 512*1024*1024


class UpdateError(Exception):
    pass


class UpdateCancelled(UpdateError):
    pass


def version_tuple(value):
    match = re.fullmatch(r'v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})', str(value))
    if not match:
        raise UpdateError('La versión publicada no tiene un formato compatible.')
    return tuple(map(int, match.groups()))


def canonical_version(value):
    return '.'.join(map(str, version_tuple(value)))


def asset_url(version, name):
    return f'{HOME}/releases/download/v{canonical_version(version)}/{name}'


def valid_digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def checked_https(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.hostname not in {
                'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
                'objects.githubusercontent.com'}):
        raise UpdateError('La descarga no procede de un servidor HTTPS permitido de GitHub.')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Transport:
    def __init__(self, version):
        self.opener = urllib.request.build_opener(SafeRedirect())
        self.headers = {'User-Agent': f'FaroPDF/{canonical_version(version)}',
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28'}

    def open(self, url):
        request = urllib.request.Request(checked_https(url), headers=self.headers)
        return self.opener.open(request, timeout=15)

    def read(self, url, limit=2*1024*1024):
        with self.open(url) as response:
            data = response.read(limit+1)
        if len(data) > limit:
            raise UpdateError('La información de la versión supera el tamaño permitido.')
        return data


@dataclass(frozen=True)
class Candidate:
    version: str
    sha256: str
    size: int
    unsigned: bool

    @property
    def filename(self):
        return f'FaroPDF-{self.version}-Instalar.exe'

    @property
    def url(self):
        return asset_url(self.version, self.filename)

    @property
    def notes_url(self):
        return f'{HOME}/releases/tag/v{self.version}'


def check_cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise UpdateCancelled('Comprobación cancelada.')


def asset_digest(asset):
    digest = asset.get('digest', '')
    if not isinstance(digest, str) or not digest.startswith('sha256:') or not valid_digest(digest[7:]):
        raise UpdateError('GitHub no proporciona una suma SHA-256 válida para este archivo.')
    return digest[7:]


def find_update(current, transport=None, cancel=None):
    transport = transport or Transport(current)
    check_cancelled(cancel)
    releases = json.loads(transport.read(API, 4*1024*1024))
    if not isinstance(releases, list):
        raise UpdateError('GitHub no devolvió una lista de versiones válida.')
    newer = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') or not release.get('published_at'):
            continue
        try:
            version = canonical_version(release['tag_name'])
        except (UpdateError, KeyError):
            continue
        # Numeric public pre-releases are the current Faro distribution channel.
        # Tags such as alpha/rc and ordinary, unpublished Git tags are excluded.
        if release['tag_name'] != 'v'+version or version_tuple(version) <= version_tuple(current):
            continue
        newer.append((version_tuple(version), version, release))
    if not newer:
        return None
    _, version, release = max(newer, key=lambda item: item[0])
    assets = release.get('assets', [])
    installer_name = f'FaroPDF-{version}-Instalar.exe'
    selected = {}
    for name in (installer_name, 'verification.json'):
        matching = [a for a in assets if a.get('name') == name and a.get('state') == 'uploaded']
        if len(matching) != 1:
            raise UpdateError('La versión todavía no tiene todos sus archivos verificados.')
        asset = matching[0]
        if asset.get('browser_download_url') != asset_url(version, name):
            raise UpdateError('El enlace de descarga no corresponde al repositorio oficial.')
        selected[name] = asset
    check_cancelled(cancel)
    manifest_bytes = transport.read(asset_url(version, 'verification.json'))
    if hashlib.sha256(manifest_bytes).hexdigest() != asset_digest(selected['verification.json']):
        raise UpdateError('La información de verificación no coincide con la publicada por GitHub.')
    report = json.loads(manifest_bytes)
    if (report.get('version') != version or report.get('private_documents_included') is not False
            or report.get('portable_integrity_verified') is not True
            or not isinstance(report.get('unsigned'), bool)
            or not all(report.get('checks', {}).get(name, {}).get('passed') is True
                       for name in ('source', 'frozen', 'native', 'installer'))):
        raise UpdateError('Esta versión no tiene una validación completa de código, ejecutable e instalador.')
    artifacts = [a for a in report.get('artifacts', []) if a.get('file') == installer_name]
    if len(artifacts) != 1:
        raise UpdateError('No se encontró el instalador en el informe de verificación.')
    artifact = artifacts[0]
    size = artifact.get('bytes')
    digest = artifact.get('sha256')
    if (type(size) is not int or not 2 < size <= MAX_PACKAGE
            or selected[installer_name].get('size') != size
            or not valid_digest(digest) or asset_digest(selected[installer_name]) != digest):
        raise UpdateError('El tamaño o la suma del instalador no coincide con GitHub.')
    return Candidate(version, digest, size, report['unsigned'])


def package_path(root, candidate):
    root = Path(root).resolve()
    version = canonical_version(candidate.version)
    if candidate.version != version:
        raise UpdateError('La versión del instalador no es válida.')
    target = root/version/candidate.filename
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise UpdateError('La carpeta de actualización no es válida.')
    return target


def verify_package(path, candidate):
    path = Path(path)
    if path.stat().st_size != candidate.size:
        raise UpdateError('El instalador descargado está incompleto.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise UpdateError('El archivo descargado no es un ejecutable de Windows.')
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != candidate.sha256:
        raise UpdateError('El instalador no coincide con su suma SHA-256. No se ejecutó.')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.faro-update-', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf8') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stage_update(candidate, root, transport=None, cancel=None, progress=None):
    transport = transport or Transport(candidate.version)
    target = package_path(root, candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    check_cancelled(cancel)
    already_valid = False
    if target.exists():
        try:
            verify_package(target, candidate)
            already_valid = True
        except UpdateError:
            pass
    if not already_valid:
        descriptor, temporary = tempfile.mkstemp(prefix='.download-', suffix='.part', dir=target.parent)
        count = 0
        try:
            with os.fdopen(descriptor, 'wb') as output, transport.open(candidate.url) as response:
                while True:
                    check_cancelled(cancel)
                    chunk = response.read(256*1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > candidate.size:
                        raise UpdateError('La descarga supera el tamaño publicado.')
                    output.write(chunk)
                    if progress:
                        progress(count, candidate.size)
            verify_package(temporary, candidate)
            check_cancelled(cancel)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    atomic_json(Path(root)/'staged.json', {'candidate': asdict(candidate)})
    return target


def load_staged(root, current):
    try:
        data = json.loads((Path(root)/'staged.json').read_text(encoding='utf8'))
        candidate = Candidate(**data['candidate'])
        if (candidate.version != canonical_version(candidate.version)
                or version_tuple(candidate.version) <= version_tuple(current)
                or not valid_digest(candidate.sha256) or type(candidate.size) is not int
                or not 2 < candidate.size <= MAX_PACKAGE or type(candidate.unsigned) is not bool):
            return None
        target = package_path(root, candidate)
        if target.is_symlink() or not target.resolve().is_relative_to(Path(root).resolve()):
            return None
        if not target.is_file():
            return None
        return candidate
    except (OSError, ValueError, TypeError, KeyError, UpdateError):
        return None


def installed_directory(executable=None):
    if sys.platform != 'win32':
        return None
    import winreg
    executable = Path(executable or sys.executable).resolve()
    try:
        key_name = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{FC19C06D-689C-4C3F-ACAA-11E80B6EE439}_is1'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            location = Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve()
        if (str(location).casefold() == str(executable.parent).casefold()
                and (location/'unins000.exe').is_file() and executable.name.lower() == 'faropdf.exe'):
            return location
    except (OSError, ValueError):
        pass
    return None


def other_instances(executable=None):
    """Conservatively defer if another process uses the same installed binary."""
    if sys.platform != 'win32':
        return True
    from ctypes import wintypes as W
    executable = str(Path(executable or sys.executable).resolve()).casefold()
    class ProcessEntry(C.Structure):
        _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                    ('th32DefaultHeapID', C.c_size_t), ('th32ModuleID', W.DWORD),
                    ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                    ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR*260)]
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [W.HANDLE, C.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = kernel.Process32NextW.restype = W.BOOL
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, C.c_void_p(-1).value):
        return True
    try:
        entry = ProcessEntry(); entry.dwSize = C.sizeof(entry)
        exists = kernel.Process32FirstW(snapshot, C.byref(entry))
        while exists:
            if entry.th32ProcessID != os.getpid() and entry.szExeFile.casefold() == Path(executable).name:
                handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not handle:
                    return True
                try:
                    buffer = C.create_unicode_buffer(32768); size = W.DWORD(len(buffer))
                    if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, C.byref(size)):
                        return True
                    if str(Path(buffer.value).resolve()).casefold() == executable:
                        return True
                finally:
                    kernel.CloseHandle(handle)
            exists = kernel.Process32NextW(snapshot, C.byref(entry))
        return False
    finally:
        kernel.CloseHandle(snapshot)


def launch_installer(candidate, root, executable=None, reopen=False, launch=None):
    executable = Path(executable or sys.executable).resolve()
    location = installed_directory(executable)
    if location is None:
        raise UpdateError('La versión portátil no se instala automáticamente. Usa la descarga de GitHub.')
    if other_instances(executable):
        return False
    installer = package_path(root, candidate)
    verify_package(installer, candidate)
    arguments = [str(installer), '/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                 '/CURRENTUSER', '/NOCLOSEAPPLICATIONS', '/NOICONS', '/DIR='+str(location),
                 '/LOG='+str(Path(root).resolve()/'install.log')]
    if reopen:
        arguments.append('/FAROREOPEN=1')
    options = {'cwd': str(installer.parent)}
    if sys.platform == 'win32':
        options['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options['startupinfo'] = startup
    (launch or subprocess.Popen)(arguments, **options)
    return True
