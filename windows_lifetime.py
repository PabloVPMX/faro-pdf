"""Windows process guards, deliberately independent of Qt and PDF libraries."""
import ctypes as C
import os
from pathlib import Path
import sys

READER_MUTEX = r'Local\FaroPDF.Reader'
UPDATE_MUTEX = r'Local\FaroPDF.Update'
_reader = None


def kernel():
    from ctypes import wintypes as W
    api = C.WinDLL('kernel32', use_last_error=True)
    api.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
    api.CreateMutexW.restype = W.HANDLE
    api.OpenMutexW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
    api.OpenMutexW.restype = W.HANDLE
    api.CloseHandle.argtypes = [W.HANDLE]
    api.CloseHandle.restype = W.BOOL
    return api


def exists(name):
    api = kernel()
    handle = api.OpenMutexW(0x100000, False, name)
    if handle:
        api.CloseHandle(handle)
        return True
    # Access denied must never be interpreted as permission to overwrite.
    return C.get_last_error() != 2


def update_guard():
    api = kernel()
    handle = api.CreateMutexW(None, False, UPDATE_MUTEX)
    error = C.get_last_error()
    if not handle:
        raise OSError(error, 'No se pudo reservar la actualización de Faro.')
    if error == 183:
        api.CloseHandle(handle)
        return None
    return handle


def updates_root():
    return Path(os.environ['LOCALAPPDATA'])/'Faro PDF'/'updates'


def enter_reader():
    """Called before importing Qt; an update never waits on a hidden dialog.

    Windows closes the reader marker when the OS process actually exits,
    including Python/Qt teardown, rather than when its last widget disappears.
    """
    global _reader
    if sys.platform != 'win32':
        return True
    # Register before checking the gate so the installer also sees a launch
    # racing with its reservation. No process is ever terminated by this code.
    _reader = kernel().CreateMutexW(None, False, READER_MUTEX)
    if not _reader:
        raise C.WinError(C.get_last_error())
    if not exists(UPDATE_MUTEX):
        return True
    # Preserve a request to open a PDF during an update, without loading Qt or
    # keeping installed DLLs locked behind a message box.
    import json
    import uuid
    try:
        pending = updates_root()/'pending-open'
        pending.mkdir(parents=True, exist_ok=True)
        files = [str(Path(arg).resolve()) for arg in sys.argv[1:]
                 if not arg.startswith('-') and Path(arg).is_file() and Path(arg).suffix.lower() == '.pdf']
        (pending/(uuid.uuid4().hex+'.json')).write_text(json.dumps({'files': files}), encoding='utf-8')
    except OSError:
        pass
    return False
