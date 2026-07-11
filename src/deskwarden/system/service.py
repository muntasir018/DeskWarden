"""
DeskWarden - system/service.py

"""

import os
import time
import threading

from ..core.paths import APPDATA_DIR, build_relaunch_cmdline
from ..core.logging_utils import log_crash
from ..core.security import log_security_event


SERVICE_NAME    = "DeskWardenService"
SERVICE_DISPLAY = "DeskWarden – Application Locker"
SERVICE_DESC    = "Monitors and locks configured applications. Managed by DeskWarden."

_running_as_service = False

def _is_admin() -> bool:
    try:
        import ctypes as _ct
        return bool(_ct.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


_TOKEN_QUERY = 0x0008
_TokenElevationType = 18
_TokenLinkedToken = 19
_TokenElevationTypeLimited = 3


def _get_linked_elevated_token(h_token, advapi, _ct, _wt):

    try:
        elevation_type = _wt.DWORD(0)
        ret_len = _wt.DWORD(0)
        ok = advapi.GetTokenInformation(
            h_token, _TokenElevationType,
            _ct.byref(elevation_type), _ct.sizeof(elevation_type),
            _ct.byref(ret_len)
        )
        if not ok or elevation_type.value != _TokenElevationTypeLimited:
           
            return None

        linked_handle = _wt.HANDLE()
        ret_len2 = _wt.DWORD(0)
        ok2 = advapi.GetTokenInformation(
            h_token, _TokenLinkedToken,
            _ct.byref(linked_handle), _ct.sizeof(linked_handle),
            _ct.byref(ret_len2)
        )
        if not ok2 or not linked_handle:
            return None
        return linked_handle
    except Exception:
        return None

def _launch_gui_in_user_session():
    try:
        import ctypes as _ct
        import ctypes.wintypes as _wt

        wtsapi   = _ct.WinDLL("wtsapi32.dll")
        advapi   = _ct.WinDLL("advapi32.dll", use_last_error=True)
        userenv  = _ct.WinDLL("userenv.dll",  use_last_error=True)
        kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)

        WTS_CURRENT_SERVER_HANDLE = None
        session_id = wtsapi.WTSGetActiveConsoleSessionId()
        if session_id == 0xFFFFFFFF:
            log_crash("_launch_gui_in_user_session", Exception("No active console session"))
            return None

        h_token = _wt.HANDLE()
        if not wtsapi.WTSQueryUserToken(session_id, _ct.byref(h_token)):
            log_crash("_launch_gui_in_user_session",
                      Exception(f"WTSQueryUserToken failed: {_ct.get_last_error()}"))
            return None

        h_dup = _wt.HANDLE()
        TOKEN_DUPLICATE     = 0x0002
        TOKEN_QUERY         = 0x0008
        TOKEN_ASSIGN_PRIMARY = 0x0001
        SECURITY_IMPERSONATION = 2
        TokenPrimary = 1
        sa = _ct.c_void_p(None)

    
        h_elevated = _get_linked_elevated_token(h_token, advapi, _ct, _wt)
        h_source = h_elevated if h_elevated else h_token

        if not advapi.DuplicateTokenEx(h_source, TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY,
                                       sa, SECURITY_IMPERSONATION, TokenPrimary,
                                       _ct.byref(h_dup)):
            kernel32.CloseHandle(h_token)
            if h_elevated:
                kernel32.CloseHandle(h_elevated)
            log_crash("_launch_gui_in_user_session",
                      Exception(f"DuplicateTokenEx failed: {_ct.get_last_error()}"))
            return None

        env_block = _ct.c_void_p()
        userenv.CreateEnvironmentBlock(_ct.byref(env_block), h_dup, False)

        cmdline = build_relaunch_cmdline("--gui")

        class STARTUPINFO(_ct.Structure):
            _fields_ = [("cb",              _wt.DWORD),
                        ("lpReserved",      _wt.LPWSTR),
                        ("lpDesktop",       _wt.LPWSTR),
                        ("lpTitle",         _wt.LPWSTR),
                        ("dwX",             _wt.DWORD),
                        ("dwY",             _wt.DWORD),
                        ("dwXSize",         _wt.DWORD),
                        ("dwYSize",         _wt.DWORD),
                        ("dwXCountChars",   _wt.DWORD),
                        ("dwYCountChars",   _wt.DWORD),
                        ("dwFillAttribute", _wt.DWORD),
                        ("dwFlags",         _wt.DWORD),
                        ("wShowWindow",     _wt.WORD),
                        ("cbReserved2",     _wt.WORD),
                        ("lpReserved2",     _ct.c_void_p),
                        ("hStdInput",       _wt.HANDLE),
                        ("hStdOutput",      _wt.HANDLE),
                        ("hStdError",       _wt.HANDLE)]
        class PROCESS_INFORMATION(_ct.Structure):
            _fields_ = [("hProcess",    _wt.HANDLE),
                        ("hThread",     _wt.HANDLE),
                        ("dwProcessId", _wt.DWORD),
                        ("dwThreadId",  _wt.DWORD)]

        si = STARTUPINFO()
        si.cb        = _ct.sizeof(STARTUPINFO)
        si.lpDesktop = "winsta0\\default"
        pi = PROCESS_INFORMATION()

        CREATE_UNICODE_ENVIRONMENT = 0x00000400
        NORMAL_PRIORITY_CLASS      = 0x00000020

        ok = advapi.CreateProcessAsUserW(
            h_dup,
            None,
            cmdline,
            None, None,
            False,
            CREATE_UNICODE_ENVIRONMENT | NORMAL_PRIORITY_CLASS,
            env_block,
            None,
            _ct.byref(si),
            _ct.byref(pi)
        )

        if env_block: userenv.DestroyEnvironmentBlock(env_block)
        kernel32.CloseHandle(h_token)
        if h_elevated:
            kernel32.CloseHandle(h_elevated)
        kernel32.CloseHandle(h_dup)

        if ok:
            kernel32.CloseHandle(pi.hThread)
            return pi.hProcess
        else:
            log_crash("_launch_gui_in_user_session",
                      Exception(f"CreateProcessAsUserW failed: {_ct.get_last_error()}"))
            return None

    except Exception as e:
        log_crash("_launch_gui_in_user_session", e)
        return None

def _monitor_and_restart_gui():
    import ctypes as _ct
    kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)
    WAIT_OBJECT_0  = 0x00000000
    WAIT_TIMEOUT   = 0x00000102
    INFINITE       = 0xFFFFFFFF

    h_proc = None

    while _running_as_service:
        marker = os.path.join(APPDATA_DIR, "clean_exit.marker")
        if os.path.exists(marker):
            try:
                os.unlink(marker)
            except Exception:
                pass
            os._exit(0)

        if h_proc is None:
            time.sleep(2)
            h_proc = _launch_gui_in_user_session()
            if h_proc is None:
                time.sleep(5)
                continue
            log_security_event("service_event", "GUI helper launched",
                               f"handle={h_proc}")

        result = kernel32.WaitForSingleObject(h_proc, 3000)
        if result == WAIT_OBJECT_0:
            exit_code = _ct.wintypes.DWORD()
            kernel32.GetExitCodeProcess(h_proc, _ct.byref(exit_code))
            kernel32.CloseHandle(h_proc)
            h_proc = None
            log_security_event("service_event", "GUI helper exited",
                               f"exit_code={exit_code.value}")

    if h_proc:
        kernel32.TerminateProcess(h_proc, 0)
        kernel32.CloseHandle(h_proc)

try:
    import win32serviceutil, win32service, win32event, servicemanager

    class DeskWardenWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_        = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_  = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            global _running_as_service
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            _running_as_service = False
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            global _running_as_service
            _running_as_service = True
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, "")
            )
            gui_thread = threading.Thread(target=_monitor_and_restart_gui,
                                          daemon=True, name="GuiWatchdog")
            gui_thread.start()
            win32event.WaitForSingleObject(self._stop_event,
                                           win32event.INFINITE)

    _SERVICE_AVAILABLE = True

except ImportError:
    _SERVICE_AVAILABLE = False
    DeskWardenWindowsService = None

