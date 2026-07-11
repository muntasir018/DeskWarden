"""
DeskWarden - system/ipc.py

"""

import time
import ctypes
import threading
from ctypes import wintypes

from ..core.logging_utils import dlog

_IPC_PIPE_NAME = r"\\.\pipe\DeskWardenIPC"


# ═════════════════════════════════════════════════════════════════════════
# Client side
# ═════════════════════════════════════════════════════════════════════════

def notify_existing_instance(log_prefix: str = "ipc", attempts: int = 10) -> bool:

    try:
        k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        k32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p
        ]
        k32.CreateFileW.restype = ctypes.c_void_p
        invalid = ctypes.c_void_p(-1).value

        for _attempt in range(attempts):
            h = k32.CreateFileW(_IPC_PIPE_NAME, GENERIC_WRITE, 0, None,
                                 OPEN_EXISTING, 0, None)
            if h and h != invalid and h != 0:
                msg = b"OPEN_CONTROL_PANEL"
                written = ctypes.c_ulong(0)
                k32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                           ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
                k32.WriteFile(h, msg, len(msg), ctypes.byref(written), None)

                k32.CloseHandle.argtypes = [ctypes.c_void_p]
                k32.CloseHandle(h)
                dlog("INFO", f"{log_prefix}: OPEN_CONTROL_PANEL signal sent via pipe")
                return True
            time.sleep(0.5)
        else:
            dlog("WARNING", f"{log_prefix}: pipe unavailable after retries. Error: {ctypes.get_last_error()}")
            return False
    except Exception as e:
        dlog("ERROR", f"{log_prefix}: pipe signal error: {e}")
        return False


# ═════════════════════════════════════════════════════════════════════════
# Server side — main instance এর pipe listener
# ═════════════════════════════════════════════════════════════════════════

def _ipc_handle_client(kernel32, _ct, _wt, h_pipe, on_open_control_panel):
    try:
        buf = (_ct.c_char * 512)()
        bytes_read = _wt.DWORD(0)
        ok = kernel32.ReadFile(h_pipe, buf, 512, _ct.byref(bytes_read), None)

        if ok and bytes_read.value > 0:
            msg = buf.raw[:bytes_read.value].decode("utf-8", errors="ignore").strip()
            dlog("INFO", f"IPC pipe: received '{msg}'")
            if msg == "OPEN_CONTROL_PANEL":
                threading.Thread(target=on_open_control_panel, daemon=True,
                                 name="IPCControlPanelOpen").start()
        elif not ok:
            dlog("WARNING", f"IPC pipe: ReadFile failed (error {_ct.get_last_error()})")

        try:
            kernel32.FlushFileBuffers(h_pipe)
        except Exception:
            pass
        kernel32.DisconnectNamedPipe(h_pipe)

    except Exception as e:
        dlog("ERROR", f"IPC pipe client-handler exception: {type(e).__name__}: {e}")
    finally:
        try:
            kernel32.CloseHandle(h_pipe)
        except Exception:
            pass


def start_ipc_pipe_server(on_open_control_panel) -> threading.Thread:


    def _ipc_pipe_server():
        import ctypes as _ct
        from ctypes import wintypes as _wt
        kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)
        advapi32 = _ct.WinDLL("advapi32.dll", use_last_error=True)

        class SECURITY_ATTRIBUTES(_ct.Structure):
            _fields_ = [
                ("nLength", _wt.DWORD),
                ("lpSecurityDescriptor", _ct.c_void_p),
                ("bInheritHandle", _wt.BOOL),
            ]

        sddl = "D:(A;;GA;;;WD)S:(ML;;NW;;;LW)"
        sd_ptr = _ct.c_void_p()

        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            _ct.c_wchar_p, _wt.DWORD, _ct.POINTER(_ct.c_void_p), _ct.POINTER(_wt.DWORD)
        ]

        sa = SECURITY_ATTRIBUTES()
        sa.nLength = _ct.sizeof(SECURITY_ATTRIBUTES)

        if advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, _ct.byref(sd_ptr), None):
            sa.lpSecurityDescriptor = sd_ptr
        else:
            sa.lpSecurityDescriptor = None
            dlog("WARNING", f"IPC pipe: Security descriptor failed (error {_ct.get_last_error()})")

        sa.bInheritHandle = False
        sa_ptr = _ct.byref(sa) if sa.lpSecurityDescriptor else None

        kernel32.CreateNamedPipeW.restype = _ct.c_void_p
        kernel32.ConnectNamedPipe.argtypes = [_ct.c_void_p, _ct.c_void_p]
        kernel32.DisconnectNamedPipe.argtypes = [_ct.c_void_p]
        kernel32.ReadFile.argtypes = [_ct.c_void_p, _ct.c_void_p, _wt.DWORD,
                                       _ct.POINTER(_wt.DWORD), _ct.c_void_p]
        kernel32.CloseHandle.argtypes = [_ct.c_void_p]
        kernel32.FlushFileBuffers.argtypes = [_ct.c_void_p]

        PIPE_ACCESS_INBOUND    = 0x00000001
        PIPE_TYPE_MESSAGE      = 0x00000004
        PIPE_READMODE_MESSAGE  = 0x00000002
        PIPE_WAIT              = 0x00000000
        INVALID_HANDLE_VALUE   = _ct.c_void_p(-1).value
        PIPE_UNLIMITED_INSTANCES = 255

        dlog("INFO", "IPC pipe server: starting (multi-threaded accept loop)")

        while True:
            try:
                h_pipe = kernel32.CreateNamedPipeW(
                    _IPC_PIPE_NAME,
                    PIPE_ACCESS_INBOUND,
                    PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                    PIPE_UNLIMITED_INSTANCES,
                    512, 512, 0, sa_ptr
                )
                if h_pipe == INVALID_HANDLE_VALUE or not h_pipe:
                    dlog("ERROR", f"IPC pipe: CreateNamedPipeW failed (error {_ct.get_last_error()})")
                    time.sleep(2)
                    continue

                connected = kernel32.ConnectNamedPipe(h_pipe, None)
                err = _ct.get_last_error()

                if not connected and err not in (0, 535, 232):
                    kernel32.CloseHandle(h_pipe)
                    continue

                threading.Thread(
                    target=_ipc_handle_client,
                    args=(kernel32, _ct, _wt, h_pipe, on_open_control_panel),
                    daemon=True,
                    name="IPCClientHandler"
                ).start()

            except Exception as e:
                dlog("ERROR", f"IPC pipe server exception: {type(e).__name__}: {e}")
                time.sleep(1)

    thread = threading.Thread(target=_ipc_pipe_server, daemon=True, name="IPCPipeServer")
    thread.start()
    dlog("INFO", "IPC pipe server thread started")
    return thread
