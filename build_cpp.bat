@echo off
chcp 65001 >nul
title DualTitle C++17 & Rust Native Compiler
echo ==============================================================================
echo        BUILDING DUALTITLE NATIVE WINDOWS APPLICATION (C++17 / RUST)
echo ==============================================================================
echo.

where cl >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [MSVC Detected] Compiling src\DualTitle.cpp with cl.exe...
    rc /fo "%~dp0src\DualTitle.res" "%~dp0src\DualTitle.rc" >nul 2>nul
    cl /std:c++17 /O2 /EHsc /Fe:"%~dp0DualTitle_Native.exe" "%~dp0src\DualTitle.cpp" user32.lib gdi32.lib shell32.lib comdlg32.lib
    goto DONE
)

where g++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [MinGW-w64 Detected] Compiling src\DualTitle.cpp with g++.exe...
    windres "%~dp0src\DualTitle.rc" -O coff -o "%~dp0src\DualTitle.res" >nul 2>nul
    g++ -std=c++17 -O2 "%~dp0src\DualTitle.cpp" -o "%~dp0DualTitle_Native.exe" -luser32 -lgdi32 -lshell32 -lcomdlg32 -lgdiplus
    goto DONE
)

where cargo >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [Rust Cargo Detected] Building DualTitle with cargo...
    cargo build --release --manifest-path "%~dp0Cargo.toml"
)

echo [Notice] Launching DualTitle Dark Control Panel GUI...
python "%~dp0universal_dualsub.py" --gui
goto END

:DONE
echo.
if exist "%~dp0DualTitle_Native.exe" (
    echo [SUCCESS] Built DualTitle_Native.exe! Launching now...
    "%~dp0DualTitle_Native.exe" --gui
)
:END
pause
