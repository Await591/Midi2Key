"""Small Win32 helpers for integrity-level (UIPI) diagnostics and elevation.

Windows blocks a lower-integrity process from injecting input into a
higher-integrity window (User Interface Privilege Isolation).  Games launched
as administrator therefore silently ignore our SendInput events; these helpers
let the app detect and explain that.
"""

import ctypes
import sys
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25

INTEGRITY_LOW = 0x1000
INTEGRITY_MEDIUM = 0x2000
INTEGRITY_HIGH = 0x3000
INTEGRITY_SYSTEM = 0x4000

SW_SHOWNORMAL = 1

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL

_advapi32.OpenProcessToken.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
)
_advapi32.OpenProcessToken.restype = wintypes.BOOL
_advapi32.GetTokenInformation.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
_advapi32.GetTokenInformation.restype = wintypes.BOOL

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD

_shell32.ShellExecuteW.argtypes = (
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_int,
)
_shell32.ShellExecuteW.restype = ctypes.c_void_p


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


def _integrity_from_token(token):
    buf = ctypes.create_string_buffer(256)
    size = wintypes.DWORD()
    ok = _advapi32.GetTokenInformation(
        token,
        TOKEN_INTEGRITY_LEVEL,
        buf,
        len(buf),
        ctypes.byref(size),
    )
    if not ok:
        return None
    label = ctypes.cast(buf, ctypes.POINTER(_SID_AND_ATTRIBUTES)).contents
    if not label.Sid:
        return None
    sid = ctypes.cast(label.Sid, ctypes.POINTER(ctypes.c_ubyte))
    sub_authority_count = sid[1]
    dwords = ctypes.cast(label.Sid, ctypes.POINTER(ctypes.c_uint32))
    return int(dwords[2 + sub_authority_count - 1])


def integrity_of_handle(process_handle):
    """Return the integrity RID of an open process handle, or None."""
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(process_handle, TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        return _integrity_from_token(token)
    finally:
        _kernel32.CloseHandle(token)


def integrity_of_process(pid):
    """Return the integrity RID of a process id, or None if unreadable."""
    handle = _kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if not handle:
        return None
    try:
        return integrity_of_handle(handle)
    finally:
        _kernel32.CloseHandle(handle)


def current_integrity():
    """Return the integrity RID of the current process."""
    return integrity_of_handle(_kernel32.GetCurrentProcess())


def foreground_process_id():
    """Return the process id owning the foreground window, or None."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


def foreground_integrity():
    """Return the integrity RID of the foreground window's process."""
    pid = foreground_process_id()
    if pid is None:
        return None
    return integrity_of_process(pid)


def is_elevated():
    """True when the current process runs at high integrity (administrator)."""
    rid = current_integrity()
    return rid is not None and rid >= INTEGRITY_HIGH


def integrity_label(rid):
    if rid is None:
        return "未知"
    if rid >= INTEGRITY_SYSTEM:
        return "系统"
    if rid >= INTEGRITY_HIGH:
        return "管理员"
    if rid >= INTEGRITY_MEDIUM:
        return "普通"
    return "受限"


def relaunch_as_admin(params=None):
    """Relaunch this program elevated.  Returns True if UAC was accepted.

    A frozen build runs ``sys.executable`` directly; a script build needs the
    script path passed as the first argument.
    """
    executable = sys.executable
    if params is None:
        args = " ".join('"%s"' % a for a in sys.argv[1:])
        if getattr(sys, "frozen", False):
            params = args
        else:
            params = " ".join(['"%s"' % sys.argv[0], args]).strip()
    result = _shell32.ShellExecuteW(None, "runas", executable, params, None, SW_SHOWNORMAL)
    return bool(result) and int(result) > 32
