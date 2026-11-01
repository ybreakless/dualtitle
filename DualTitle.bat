@echo off
chcp 65001 >nul
title DualTitle — Universal Anti-Cheat-Safe Dual Subtitles & Save Controller
cls

:: 1. If Native C++17 executable is already built, launch it directly!
if exist "%~dp0DualTitle_Native.exe" (
    start "" "%~dp0DualTitle_Native.exe" --gui
    goto END
)

:: 2. Auto-compile C++17 Native executable if MSVC (cl.exe) or MinGW (g++.exe) is available
where cl >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    rc /fo "%~dp0src\DualTitle.res" "%~dp0src\DualTitle.rc" >nul 2>nul
    cl /nologo /std:c++17 /O2 /EHsc /Fe:"%~dp0DualTitle_Native.exe" "%~dp0src\DualTitle.cpp" user32.lib gdi32.lib shell32.lib comdlg32.lib >nul 2>nul
    if exist "%~dp0DualTitle_Native.exe" (
        start "" "%~dp0DualTitle_Native.exe" --gui
        goto END
    )
)

where g++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    windres "%~dp0src\DualTitle.rc" -O coff -o "%~dp0src\DualTitle.res" >nul 2>nul
    g++ -std=c++17 -O2 -mwindows "%~dp0src\DualTitle.cpp" -o "%~dp0DualTitle_Native.exe" -luser32 -lgdi32 -lshell32 -lcomdlg32 >nul 2>nul
    if exist "%~dp0DualTitle_Native.exe" (
        start "" "%~dp0DualTitle_Native.exe" --gui
        goto END
    )
)

:: 3. Launch via built-in Win32 GUI runtime (with Game Picker, Speed HUD & Restore Save)
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%~dp0universal_dualsub.py" --gui
) else (
    python "%~dp0universal_dualsub.py" --gui
)

:END
