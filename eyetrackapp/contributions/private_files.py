"""Owner-only files, including Windows exports into broadly readable folders.

The matching helper is shared with the ETVR-Dataset-Sync CLI. On Windows, chmod
alone does not restrict read access. Apply a protected DACL to the open file
handle before writing any capability, rather than trusting its parent folder.
"""

import os
from pathlib import Path


def owner_sid():
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise OSError("Cannot secure private receipt")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise OSError("Cannot identify private receipt owner")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        string = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(string)):
            raise OSError("Cannot identify private receipt owner")
        try:
            return string.value
        finally:
            kernel.LocalFree(string)
    finally:
        kernel.CloseHandle(token)


def restrict_access(path, *, directory=False, fd=None):
    path = Path(path)
    if os.name != "nt":
        if fd is not None:
            os.fchmod(fd, 0o700 if directory else 0o600)
        else:
            path.chmod(0o700 if directory else 0o600)
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.ReOpenFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    kernel.ReOpenFile.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.SetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    flags = "OICI" if directory else ""
    sddl = f"D:P(A;{flags};FA;;;{owner_sid()})(A;{flags};FA;;;SY)"
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
        raise OSError("Cannot construct private receipt permissions")
    try:
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        if not advapi.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
        ):
            raise OSError("Cannot construct private receipt permissions")
        security = 0x80000004  # Protected DACL: do not inherit broadly readable permissions.
        if fd is not None:
            # CRT write handles do not include WRITE_DAC. Reopen the same file,
            # not its pathname, so a shared-folder rename cannot redirect this ACL.
            handle = kernel.ReOpenFile(wintypes.HANDLE(msvcrt.get_osfhandle(fd)), 0x60000, 7, 0)
            if handle in (None, ctypes.c_void_p(-1).value):
                raise OSError("Cannot secure private receipt handle")
            try:
                error = advapi.SetSecurityInfo(handle, 1, security, None, None, dacl, None)
            finally:
                kernel.CloseHandle(handle)
        else:
            error = advapi.SetNamedSecurityInfoW(str(path), 1, security, None, None, dacl, None)
        if error:
            raise OSError(error, "Cannot restrict access to private receipt")
    finally:
        kernel.LocalFree(descriptor)
