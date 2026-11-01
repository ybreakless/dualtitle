@echo off
setlocal EnableDelayedExpansion
title DualTitle Install (Start Menu searchable)
echo ==============================================================================
echo             DUALTITLE v5 - INSTALL ^& REGISTER IN WINDOWS SEARCH
echo ==============================================================================
echo.

:: ---------------------------------------------------------------------------
:: 0. Precheck
:: ---------------------------------------------------------------------------
if not exist "%~dp0DualTitle.exe" (
    echo [ERROR] DualTitle.exe not found next to this script.
    echo         Run build_cpp.bat first, then run this installer again.
    goto END
)

:: ---------------------------------------------------------------------------
:: 1. Copy the portable suite to %LocalAppData%\Programs\DualTitle
:: ---------------------------------------------------------------------------
set "DEST=%LocalAppData%\Programs\DualTitle"
echo [Setup] Installing portable suite to: %DEST%

if exist "%DEST%" rmdir /s /q "%DEST%" 2>nul
mkdir "%DEST%" 2>nul

copy /y "%~dp0DualTitle.exe" "%DEST%\" >nul
if exist "%~dp0RestoreSave.exe" copy /y "%~dp0RestoreSave.exe" "%DEST%\" >nul 2>nul
if exist "%~dp0assets"          xcopy /y /i /e "%~dp0assets"          "%DEST%\assets"          >nul
if exist "%~dp0data"            xcopy /y /i /e "%~dp0data"            "%DEST%\data"            >nul
if exist "%~dp0dictionaries"    xcopy /y /i /e "%~dp0dictionaries"    "%DEST%\dictionaries"    >nul
if exist "%~dp0README.md"       copy /y "%~dp0README.md" "%DEST%\" >nul 2>nul

> "%DEST%\DualTitle.bat" echo @echo off
>> "%DEST%\DualTitle.bat" echo start "" "%DEST%\DualTitle.exe"

:: ---------------------------------------------------------------------------
:: 2. Start Menu + Desktop shortcuts (registered in Windows Search)
:: ---------------------------------------------------------------------------
echo [Setup] Creating Start Menu and Desktop shortcuts ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$src='%DEST%\DualTitle.exe';" ^
  "$ico='%DEST%\assets\dualtitle.ico';" ^
  "$smFolder=[Environment]::GetFolderPath('Programs');" ^
  "$sm=$ws.CreateShortcut((Join-Path $smFolder 'DualTitle.lnk'));" ^
  "$sm.TargetPath=$src; $sm.WorkingDirectory='%DEST%'; $sm.IconLocation=$ico;" ^
  "$sm.Description='DualTitle - Universal Dual Subtitle Overlay'; $sm.Save();" ^
  "$dtFolder=[Environment]::GetFolderPath('Desktop');" ^
  "$dt=$ws.CreateShortcut((Join-Path $dtFolder 'DualTitle.lnk'));" ^
  "$dt.TargetPath=$src; $dt.WorkingDirectory='%DEST%'; $dt.IconLocation=$ico;" ^
  "$dt.Save();"

echo.
echo [OK]  Installed to: %DEST%
echo [OK]  "DualTitle" is now searchable - press the Windows key and type: DualTitle
echo [OK]  Start Menu shortcut: %AppData%\Microsoft\Windows\Start Menu\Programs\DualTitle.lnk

:END
echo.
pause
