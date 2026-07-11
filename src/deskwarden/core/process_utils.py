"""
DeskWarden - core/process_utils.py

"""

import os
import ctypes
import threading
import winreg
import subprocess

import psutil
import win32gui
import win32con
import win32process

from .paths import build_relaunch_args
from .logging_utils import dlog

# ═════════════════════════════════════════════════════════════════════════
# Process Suspend / Resume
# ═════════════════════════════════════════════════════════════════════════

_ntdll = ctypes.WinDLL("ntdll.dll")
_kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

_NtSuspendProcess = _ntdll.NtSuspendProcess
_NtResumeProcess  = _ntdll.NtResumeProcess
_NtSuspendProcess.restype = ctypes.c_long
_NtResumeProcess.restype  = ctypes.c_long

PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_TERMINATE      = 0x0001


def _open_process(pid: int, access: int):
    handle = _kernel32.OpenProcess(access, False, pid)
    return handle if handle else None


def suspend_process(pid: int) -> bool:
    handle = _open_process(pid, PROCESS_SUSPEND_RESUME)
    if not handle:
        dlog("WARNING", f"suspend_process: OpenProcess failed for PID {pid}")
        return False
    try:
        status = _NtSuspendProcess(handle)
        if status != 0:
            dlog("WARNING", f"suspend_process: NtSuspendProcess returned {status} for PID {pid}")
        return status == 0
    except Exception as e:
        dlog("ERROR", f"suspend_process exception PID {pid}: {e}")
        return False
    finally:
        _kernel32.CloseHandle(handle)


def resume_process(pid: int) -> bool:
    handle = _open_process(pid, PROCESS_SUSPEND_RESUME)
    if not handle:
        dlog("WARNING", f"resume_process: OpenProcess failed for PID {pid}")
        return False
    try:
        status = _NtResumeProcess(handle)
        if status != 0:
            dlog("WARNING", f"resume_process: NtResumeProcess returned {status} for PID {pid}")
        return status == 0
    except Exception as e:
        dlog("ERROR", f"resume_process exception PID {pid}: {e}")
        return False
    finally:
        _kernel32.CloseHandle(handle)


# ═════════════════════════════════════════════════════════════════════════
# Windows startup (elevated logon Scheduled Task)
# ═════════════════════════════════════════════════════════════════════════


_AUTOSTART_TASK_NAME = "DeskWarden"


def _remove_legacy_run_key():

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "DeskWarden")
        except Exception:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass


def set_autostart(enable):
    _remove_legacy_run_key()
    try:
        args = build_relaunch_args("--open-control-panel")
        exe = args[0]
        rest = " ".join(f'"{a}"' if not a.startswith("--") else a for a in args[1:])

        def _ps_quote(s: str) -> str:
            return "'" + s.replace("'", "''") + "'"

        trigger_line = "$Trigger=New-ScheduledTaskTrigger -AtLogOn;" if enable else ""
        trigger_arg  = "-Trigger $Trigger " if enable else ""

        ps_script = (
            f"$Action=New-ScheduledTaskAction -Execute {_ps_quote(exe)} "
            f"-Argument {_ps_quote(rest)};"
            f"{trigger_line}"
            "$Principal=New-ScheduledTaskPrincipal "
            "-UserId ('{0}\\{1}' -f $env:USERDOMAIN,$env:USERNAME) -RunLevel Highest;"
            "$Settings=New-ScheduledTaskSettingsSet -MultipleInstances Parallel "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;"
            f"Register-ScheduledTask -TaskName {_ps_quote(_AUTOSTART_TASK_NAME)} "
            f"-Action $Action {trigger_arg}-Principal $Principal "
            "-Settings $Settings -Force | Out-Null"
        )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if result.returncode == 0:
            if enable:
                dlog("INFO", "set_autostart: Windows startup enabled "
                             "(elevated logon task, parallel instances allowed)")
            else:
                dlog("INFO", "set_autostart: Windows startup disabled "
                             "(logon trigger removed, task kept for shortcut/manual run)")
        else:
            dlog("ERROR", f"set_autostart: Register-ScheduledTask failed "
                           f"(code {result.returncode}): {result.stderr.strip()}")
    except Exception as e:
        dlog("ERROR", f"set_autostart: failed: {e}")


# ═════════════════════════════════════════════════════════════════════════
# Hide / restore all windows of a process (tree-aware)
# ═════════════════════════════════════════════════════════════════════════

def _get_process_tree_pids(root_pid: int) -> set:
    import psutil as _ps
    import os as _os

    pids = set()
    try:
        proc = _ps.Process(root_pid)
        exe_name = _os.path.basename(proc.exe()).lower()

        true_root = proc
        try:
            parent = proc.parent()
            while parent is not None:
                try:
                    parent_exe = _os.path.basename(parent.exe()).lower()
                except (_ps.NoSuchProcess, _ps.AccessDenied):
                    break
                if parent_exe == exe_name:
                    true_root = parent
                    parent = parent.parent()
                else:
                    break
        except (_ps.NoSuchProcess, _ps.AccessDenied):
            pass

        pids.add(true_root.pid)
        try:
            for child in true_root.children(recursive=True):
                pids.add(child.pid)
        except (_ps.NoSuchProcess, _ps.AccessDenied):
            pass

    except Exception:
        pids.add(root_pid)

    return pids


_hidden_hwnds: set = set()
_hidden_lock = threading.Lock()


def _hwnd_in_pids(hwnd, pids):
    try:
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        return wpid in pids
    except Exception:
        return False


def hide_process_windows(pid):
    target_pids = _get_process_tree_pids(pid)
    newly_hidden = []

    def callback(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid not in target_pids:
                return
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            if win32gui.IsWindowVisible(hwnd) or (style & win32con.WS_VISIBLE):
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                newly_hidden.append(hwnd)
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)

    with _hidden_lock:
        _hidden_hwnds.update(newly_hidden)


def restore_process_windows(pid):
    target_pids = _get_process_tree_pids(pid)

    with _hidden_lock:
        to_restore = [h for h in list(_hidden_hwnds)
                      if _hwnd_in_pids(h, target_pids)]
        for h in to_restore:
            _hidden_hwnds.discard(h)

    restored = False
    for hwnd in to_restore:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            if not restored:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                restored = True
        except Exception:
            pass
