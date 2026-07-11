@echo off
setlocal EnableDelayedExpansion

set "ORIG_QUICKEDIT=1"
for /f "tokens=3" %%a in ('reg query "HKCU\Console" /v QuickEdit 2^>nul ^| findstr QuickEdit') do set "ORIG_QUICKEDIT=%%a"
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1

:: ============================================================
::  DeskWarden Installer v1.0
:: ============================================================

set "HALT=0"
set "HALT_CODE=0"

call :header
call :step_check_admin
if "!HALT!"=="1" goto :end_script

call :step_check_already_installed
if "!HALT!"=="1" goto :end_script

call :step_check_python
if "!HALT!"=="1" goto :end_script

call :step_check_source
if "!HALT!"=="1" goto :end_script

call :step_stop_existing
call :step_install_deps
if "!HALT!"=="1" goto :end_script

call :step_copy_files
if "!HALT!"=="1" goto :end_script

call :step_extract_icon
call :step_shortcuts

call :step_verify_deps
if "!HALT!"=="1" goto :end_script

call :step_autostart
if "!HALT!"=="1" goto :end_script

call :step_launch
call :footer

:end_script
set "EXIT_CODE=0"
if "!HALT!"=="1" set "EXIT_CODE=!HALT_CODE!"

reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d !ORIG_QUICKEDIT! /f >nul 2>&1
endlocal & exit /b %EXIT_CODE%


:: ============================================================
:: SUBROUTINES
:: ============================================================

:header
cls
echo.
echo  ===========================================================
echo   DeskWarden  ^|  Application Locker  ^|  v1.0 Installer
echo  ===========================================================
echo.
echo   This installer will:
echo     [1] Verify system requirements
echo     [2] Install Python (if missing) with progress bar
echo     [3] Install required Python packages (with progress)
echo     [4] Copy files to Program Files
echo     [5] Extract and install application icon
echo     [6] Create desktop and Start Menu shortcuts
echo     [7] Register auto-start on Windows login
echo.
echo  -----------------------------------------------------------
echo.
goto :eof


:step_check_admin
echo  [STEP 1/7]  Checking administrator privileges...
net session >nul 2>&1
if %errorLevel% neq 0 (
    call :error "Administrator privileges required." "Right-click the installer and choose 'Run as administrator'."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)
call :ok "Running with administrator privileges."
goto :eof


:step_check_already_installed
set "INSTALL_DIR=C:\Program Files\DeskWarden"
if not exist "!INSTALL_DIR!\src\DeskWarden.py" goto :eof

echo.
powershell -NoProfile -Command ^
  "Write-Host '  -----------------------------------------------------------' -ForegroundColor Red; " ^
  "Write-Host '   DeskWarden is already installed on this system.' -ForegroundColor Red; " ^
  "Write-Host '  -----------------------------------------------------------' -ForegroundColor Red"
echo.

:ask_reinstall
set "REINSTALL="
set /p "REINSTALL=  Update DeskWarden to the latest version? (y/n): "
echo.

if /i "!REINSTALL!"=="y" goto :reinstall_yes
if /i "!REINSTALL!"=="n" goto :reinstall_no
echo   Please enter y or n only.
echo.
goto :ask_reinstall

:reinstall_no
echo   Update cancelled. DeskWarden is already running.
echo.
echo Press any key to continue . . .
powershell -NoProfile -Command ^
  "$sw = [Diagnostics.Stopwatch]::StartNew();" ^
  "while ($sw.Elapsed.TotalSeconds -lt 4) {" ^
  "  if ([Console]::KeyAvailable) { [Console]::ReadKey($true) | Out-Null; break }" ^
  "  Start-Sleep -Milliseconds 100" ^
  "}" >nul 2>&1
set "HALT=1"
set "HALT_CODE=0"
goto :eof

:reinstall_yes
call :ok "Updating DeskWarden..."
goto :eof


:step_check_python
echo  [STEP 2/7]  Locating Python installation...
set "PYTHON_EXE="
call :find_python

if not "!PYTHON_EXE!"=="" (
    call :ok "Python found: !PYTHON_EXE!"
    goto :eof
)

echo.
echo   Python was not found on this system.
echo   Downloading and installing Python automatically...
echo.
call :install_python

if "!PYTHON_EXE!"=="" (
    call :error "Automatic Python installation failed." "Please install Python manually from https://www.python.org then re-run this installer."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)
call :ok "Python installed: !PYTHON_EXE!"
echo   Letting Windows finish initializing the new Python install...
timeout /t 5 /nobreak >nul
goto :eof


:find_python
set "PYTHON_EXE="

for /f "delims=" %%i in ('where python.exe 2^>nul') do (
    if "!PYTHON_EXE!"=="" set "PYTHON_EXE=%%i"
)
if "!PYTHON_EXE!"=="" goto :eof
"!PYTHON_EXE!" -c "import sys" >nul 2>&1
if %errorLevel% neq 0 set "PYTHON_EXE="
goto :eof


:install_python
where winget >nul 2>&1
if %errorLevel% equ 0 (
    echo   Installing latest Python via winget, please wait...
    winget install --id Python.Python.3 -e --silent --accept-package-agreements --accept-source-agreements
    call :refresh_path
    call :find_python
    if not "!PYTHON_EXE!"=="" goto :eof
)
set "PY_INSTALLER=%TEMP%\python_installer.exe"
del /q "!PY_INSTALLER!" >nul 2>&1
echo   Downloading Python installer...
set "DL_SCRIPT=%~dp0scripts\dw_pydownload.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "!DL_SCRIPT!" -Dest "!PY_INSTALLER!"
if !errorLevel! neq 0 (
    call :warn "Could not download Python." "Check internet connection."
    goto :eof
)
echo   Installing Python silently...
"!PY_INSTALLER!" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
timeout /t 5 /nobreak >nul
del /q "!PY_INSTALLER!" >nul 2>&1
call :refresh_path
call :find_python
goto :eof


:refresh_path
set "SYS_PATH="
set "USR_PATH="
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
set "FALLBACK_PATHS=%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;%ProgramFiles%\Python313;%ProgramFiles%\Python313\Scripts;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"
set "PATH=!SYS_PATH!;!USR_PATH!;!FALLBACK_PATHS!;%PATH%"
goto :eof


:step_check_source
set "SOURCE_SCRIPT=%~dp0src\DeskWarden.py"
if not exist "%SOURCE_SCRIPT%" (
    call :error "src\DeskWarden.py not found in the installer folder." "Make sure all installer files are in the correct folder structure."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)

if not exist "%~dp0src\deskwarden\app.py" (
    call :error "src\deskwarden\ package not found in the installer folder." "Make sure all installer files (including the deskwarden module folder) are in the correct folder structure."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)
call :ok "Source script located."
goto :eof


:step_stop_existing
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul
goto :eof


:step_install_deps
echo  [STEP 3/7]  Installing required packages...
echo.

set "HELPER=%~dp0scripts\dw_pip_helper.py"
if not exist "!HELPER!" (
    call :error "scripts\dw_pip_helper.py not found." "Make sure it is in the scripts folder."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)

"!PYTHON_EXE!" -u "!HELPER!"
set "PIP_RC=!errorLevel!"
if !PIP_RC! neq 0 (
    call :error "Package installation failed." "Check your internet connection and try again."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)

call :ok "Package installation completed."
goto :eof


:step_copy_files
echo  [STEP 4/7]  Installing application files...
set "INSTALL_DIR=C:\Program Files\DeskWarden"
if not exist "!INSTALL_DIR!"        mkdir "!INSTALL_DIR!"
if not exist "!INSTALL_DIR!\assets" mkdir "!INSTALL_DIR!\assets"
if not exist "!INSTALL_DIR!\src"    mkdir "!INSTALL_DIR!\src"


robocopy "%~dp0src" "!INSTALL_DIR!\src" /E /PURGE /NFL /NDL /NJH /NJS /NC /NS /NP >nul
if !errorLevel! geq 8 (
    call :error "Failed to copy files to Program Files." "Check that no security software is blocking the installation."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)

robocopy "%~dp0assets" "!INSTALL_DIR!\assets" /E /PURGE /NFL /NDL /NJH /NJS /NC /NS /NP >nul

:: Copy uninstaller
if exist "%~dp0uninstall_deskwarden.bat" (
    copy /y "%~dp0uninstall_deskwarden.bat" "!INSTALL_DIR!\uninstall.bat" >nul
)

:: Determine pythonw path (no CMD window on launch)
set "LAUNCH_EXE=!PYTHON_EXE!"
if exist "!PYTHON_EXE:python.exe=pythonw.exe!" set "LAUNCH_EXE=!PYTHON_EXE:python.exe=pythonw.exe!"

call :ok "Application files installed."
goto :eof


:step_extract_icon
echo  Installing application icon...
set "ICON_PATH="

if not exist "!INSTALL_DIR!\assets\icon.png" (
    call :warn "icon.png not found in assets folder." "Shortcut will use the default icon."
    goto :eof
)

"!PYTHON_EXE!" -c "from PIL import Image; img=Image.open(r'!INSTALL_DIR!\assets\icon.png').convert('RGBA'); img.save(r'!INSTALL_DIR!\assets\icon.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if %errorLevel% equ 0 (
    call :ok "Application icon installed."
    set "ICON_PATH=!INSTALL_DIR!\assets\icon.ico"
) else (
    call :warn "Could not convert icon." "Shortcut will use the default icon."
)
goto :eof


:step_shortcuts
echo  [STEP 5/7]  Creating shortcuts...
set "DESKTOP_PATH=%PUBLIC%\Desktop\DeskWarden.lnk"
set "STARTMENU_PATH=%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\DeskWarden.lnk"
set "FINAL_SCRIPT=!INSTALL_DIR!\src\DeskWarden.py"


set "VBS_PATH=!INSTALL_DIR!\run_hidden.vbs"
echo Set WshShell = CreateObject("WScript.Shell") > "!VBS_PATH!"
echo WshShell.Run "schtasks /run /tn ""DeskWarden""", 0, False >> "!VBS_PATH!"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$WshShell=New-Object -COM WScript.Shell;" ^
  "$icon=''; if(Test-Path '!ICON_PATH!'){$icon='!ICON_PATH!'};" ^
  "$s=$WshShell.CreateShortcut('!DESKTOP_PATH!');" ^
  "$s.TargetPath='%SystemRoot%\System32\wscript.exe';" ^
  "$s.Arguments='\"!VBS_PATH!\"';" ^
  "$s.WorkingDirectory='!INSTALL_DIR!';" ^
  "if($icon){$s.IconLocation=$icon};" ^
  "$s.WindowStyle=7; $s.Save();" ^
  "$s2=$WshShell.CreateShortcut('!STARTMENU_PATH!');" ^
  "$s2.TargetPath='%SystemRoot%\System32\wscript.exe';" ^
  "$s2.Arguments='\"!VBS_PATH!\"';" ^
  "$s2.WorkingDirectory='!INSTALL_DIR!';" ^
  "if($icon){$s2.IconLocation=$icon};" ^
  "$s2.WindowStyle=7; $s2.Save();" ^
  "Write-Output 'Done.'" >nul 2>&1

if %errorLevel% equ 0 (
    call :ok "Desktop shortcut created for all users."
    call :ok "Start Menu shortcut created for all users."
) else (
    call :warn "Could not create shortcuts." "Create manually from !INSTALL_DIR!\src\DeskWarden.py"
)
goto :eof


:step_verify_deps
echo  Verifying installed packages...
"!PYTHON_EXE!" -c "import psutil, win32api, win32gui, win32con, win32process; from PIL import Image; from PyQt6 import QtWidgets, QtCore, QtGui" >nul 2>&1
if %errorLevel% neq 0 (
    call :error "Package verification failed." "Run manually: !PYTHON_EXE! -m pip install psutil pywin32 pillow PyQt6 PyQt6-Qt6-Svg"
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)
call :ok "All packages verified and working."
goto :eof


:step_autostart
echo  [STEP 6/7]  Registering auto-start on login...
set "FINAL_SCRIPT=!INSTALL_DIR!\src\DeskWarden.py"

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "DeskWarden" /f >nul 2>&1
schtasks /delete /tn "DeskWarden" /f >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$Action=New-ScheduledTaskAction -Execute '!LAUNCH_EXE!' -Argument '\"!FINAL_SCRIPT!\" --open-control-panel';" ^
  "$Trigger=New-ScheduledTaskTrigger -AtLogOn;" ^
  "$Principal=New-ScheduledTaskPrincipal -UserId ('{0}\{1}' -f $env:USERDOMAIN,$env:USERNAME) -RunLevel Highest;" ^
  "$Settings=New-ScheduledTaskSettingsSet -MultipleInstances Parallel -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;" ^
  "Register-ScheduledTask -TaskName 'DeskWarden' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null" >nul 2>&1

if %errorLevel% neq 0 (
    call :error "Auto-start registration failed." "Try running the installer again as administrator."
    pause
    set "HALT=1"
    set "HALT_CODE=1"
    goto :eof
)
call :ok "Auto-start on login registered (elevated, parallel instances allowed)."
goto :eof


:step_launch
echo  [STEP 7/7]  Launching DeskWarden...
start "" "!LAUNCH_EXE!" "!FINAL_SCRIPT!"
call :ok "DeskWarden started."
goto :eof


:footer
echo.
echo  ===========================================================
echo   INSTALLATION COMPLETE
echo  ===========================================================
echo.
echo   DeskWarden is installed and running.
echo   Find the tray icon in the bottom-right corner.
echo.
echo  ===========================================================
echo.
echo Press any key to continue . . .
powershell -NoProfile -Command ^
  "$sw=[Diagnostics.Stopwatch]::StartNew();" ^
  "while($sw.Elapsed.TotalSeconds -lt 4){" ^
  "  if([Console]::KeyAvailable){[Console]::ReadKey($true)|Out-Null;break}" ^
  "  Start-Sleep -Milliseconds 100" ^
  "}" >nul 2>&1
goto :eof


:: ---- Utility Printers ----

:ok
echo     ^> %~1
goto :eof

:warn
echo.
echo   [WARNING]  %~1
if not "%~2"=="" echo              %~2
echo.
goto :eof

:error
echo.
echo   [ERROR]    %~1
if not "%~2"=="" echo              %~2
echo.
goto :eof
