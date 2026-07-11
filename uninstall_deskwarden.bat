@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  DeskWarden Uninstaller v1.0
:: ============================================================

set "ABORT=0"
set "ALREADY_DONE=0"
set "SILENT_CLOSE=0"
set "INSTALL_DIR=C:\Program Files\DeskWarden"
set "APPDATA_DIR=%APPDATA%\DeskWarden"
set "FLAG_FILE=%APPDATA%\DeskWarden\installed.flag"

call :header
call :step_check_admin
if "!ABORT!"=="1" goto :abort

call :step_check_install
if "!ALREADY_DONE!"=="1" goto :clean_exit
if "!ABORT!"=="1" goto :abort

call :step_stop_app
call :step_remove_scheduler
call :step_remove_shortcuts
call :step_remove_files
call :step_remove_appdata
call :footer

endlocal
exit /b 0

:abort
echo.
if "!SILENT_CLOSE!"=="1" (
    endlocal
    exit /b 1
)
call :auto_close
endlocal
exit /b 1

:clean_exit
echo.
call :auto_close
endlocal
exit /b 0


:: ============================================================
:: SUBROUTINES
:: ============================================================

:header
cls
echo.
echo  ===========================================================
echo   DeskWarden  ^|  Application Locker  ^|  v1.0 Uninstaller
echo  ===========================================================
echo.
echo   This uninstaller will:
echo     [1] Check installation status
echo     [2] Stop DeskWarden if running
echo     [3] Remove Task Scheduler entry
echo     [4] Remove Desktop and Start Menu shortcuts
echo     [5] Delete all installed files
echo     [6] Remove app data and settings
echo.
echo  -----------------------------------------------------------
echo.
goto :eof


:step_check_admin
echo  [STEP 1/6]  Checking administrator privileges...
net session >nul 2>&1
if %errorLevel% neq 0 (
    call :error "Administrator privileges required." "Right-click the uninstaller and choose 'Run as administrator'."
    set "ABORT=1"
    goto :eof
)
call :ok "Running with administrator privileges."
goto :eof


:step_check_install

echo  [STEP 2/6]  Checking installation status...

if exist "!INSTALL_DIR!" (
    call :ok "DeskWarden installation found."
    goto :eof
)


echo.
echo  -----------------------------------------------------------
echo [91m  DeskWarden is already uninstalled.[0m

if exist "!APPDATA_DIR!" (
    
    echo [91m  Some settings and data are still remaining on this computer.[0m
    echo  -----------------------------------------------------------
    echo.
    echo     [1]  Remove remaining data and exit
    echo     [2]  Exit
    echo.
    set "CHOICE="
    set /p "CHOICE=  Enter your choice (1 or 2): "
    echo.

    if "!CHOICE!"=="1" (
        rd /s /q "!APPDATA_DIR!" >nul 2>&1
        echo  -----------------------------------------------------------
        call :ok "Remaining data removed successfully."
        echo  -----------------------------------------------------------
    ) else (
        echo  -----------------------------------------------------------
        call :ok "Exiting without removing data."
        echo  -----------------------------------------------------------
    )
) else (
    
    echo   No data found on this computer.
    echo  -----------------------------------------------------------
)

set "ALREADY_DONE=1"
goto :eof


:step_stop_app
echo  [STEP 3/6]  Stopping DeskWarden...

for %%E in (pythonw.exe python.exe) do (
    for /f "tokens=*" %%a in ('wmic process where "name='%%E'" get ProcessId^,CommandLine /format:csv 2^>nul ^| findstr /i "DeskWarden"') do (
        for /f "tokens=3 delims=," %%b in ("%%a") do (
            taskkill /PID %%b /F >nul 2>&1
        )
    )
)
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
call :ok "DeskWarden stopped."
goto :eof


:step_remove_scheduler
echo  [STEP 4/6]  Removing auto-start entries...

schtasks /delete /tn "DeskWarden" /f >nul 2>&1
call :ok "Task Scheduler entry removed."

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "DeskWarden" /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "DeskWarden" /f >nul 2>&1
call :ok "Registry entries removed."

net stop DeskWardenService >nul 2>&1
sc delete DeskWardenService >nul 2>&1
goto :eof


:step_remove_shortcuts
echo  [STEP 5/6]  Removing shortcuts...

set "DESKTOP_LNK=%PUBLIC%\Desktop\DeskWarden.lnk"
if exist "!DESKTOP_LNK!" (
    del /f /q "!DESKTOP_LNK!" >nul 2>&1
    call :ok "Desktop shortcut removed."
) else (
    call :ok "Desktop shortcut already removed."
)

set "STARTMENU_LNK=%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\DeskWarden.lnk"
if exist "!STARTMENU_LNK!" (
    del /f /q "!STARTMENU_LNK!" >nul 2>&1
    call :ok "Start Menu shortcut removed."
) else (
    call :ok "Start Menu shortcut already removed."
)
goto :eof


:step_remove_files
echo  [STEP 6/6]  Deleting installed files...

if exist "!INSTALL_DIR!" (
    rd /s /q "!INSTALL_DIR!" >nul 2>&1
    if exist "!INSTALL_DIR!" (
        call :warn "Could not delete some files." "Try restarting and running uninstaller again."
    ) else (
        call :ok "All installed files deleted."
    )
) else (
    call :ok "Install folder already removed."
)
goto :eof


:step_remove_appdata
echo.
echo  -----------------------------------------------------------
set /p "KEEPDATA=  Keep settings and locked app list? (y/n): "
echo  -----------------------------------------------------------
echo.

if /i "!KEEPDATA!"=="n" (
    if exist "!APPDATA_DIR!" (
        rd /s /q "!APPDATA_DIR!" >nul 2>&1
        call :ok "All settings and data removed."
    ) else (
        call :ok "No app data found."
    )
) else (
    call :ok "Settings kept."
)
goto :eof


:footer
echo.
echo  ===========================================================
echo   UNINSTALLATION COMPLETE
echo  ===========================================================
echo.
echo   DeskWarden has been completely removed from your system.
echo.
echo  ===========================================================
echo.
call :auto_close
goto :eof


:: ---- Utility Printers ----

:auto_close
echo Press any key to continue . . .
timeout /t 4 >nul
goto :eof

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
