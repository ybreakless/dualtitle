@echo off
setlocal EnableDelayedExpansion
title DualTitle Native Build (MSVC)
echo ==============================================================================
echo            BUILDING DUALTITLE v5 ("Aurora") NATIVE WINDOWS APPLICATION
echo ==============================================================================
echo.

cd /d "%~dp0"

:: ---------------------------------------------------------------------------
:: 1. Locate Visual Studio 2022 (BuildTools or full IDE) via vswhere, load MSVC
:: ---------------------------------------------------------------------------
where cl >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    if exist "!VSWHERE!" (
        for /f "usebackq delims=" %%i in (`"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
            echo [Setup] Importing MSVC environment from: %%i
            call "%%i\VC\Auxiliary\Build\vcvars64.bat" >nul 2>nul
        )
    )
)

:: ---------------------------------------------------------------------------
:: 2. Compile the native C++17 GUI (MSVC preferred, MinGW-w64 fallback)
:: ---------------------------------------------------------------------------
where cl >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [MSVC] Compiling resources and DualTitle.cpp ...
    rc /nologo /fo "src\DualTitle.res" "src\DualTitle.rc"
    if errorlevel 1 (
        echo [WARN] rc.exe failed - building without embedded icon/version resources.
    )
    cl /nologo /std:c++17 /O2 /EHsc /utf-8 ^
       /Fe:"%~dp0DualTitle.exe" ^
       "%~dp0src\DualTitle.cpp" "%~dp0src\DualTitle.res" ^
       user32.lib gdi32.lib shell32.lib comdlg32.lib gdiplus.lib uxtheme.lib winmm.lib
    goto POSTBUILD
)

where g++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [MinGW-w64] Compiling DualTitle.cpp with g++ ...
    windres "src\DualTitle.rc" -O coff -o "src\DualTitle.res"
    g++ -std=c++17 -O2 -DUNICODE -D_UNICODE "%~dp0src\DualTitle.cpp" "%~dp0src\DualTitle.res" ^
        -o "%~dp0DualTitle.exe" ^
        -luser32 -lgdi32 -lshell32 -lcomdlg32 -lgdiplus -luxtheme -lwinmm
    goto POSTBUILD
)

echo [ERROR] No C++ compiler found. Install VS 2022 Build Tools (C++ workload) or MinGW-w64.
echo         Falling back to the Python launcher ...
python "%~dp0universal_dualsub.py" --gui
goto END

:: ---------------------------------------------------------------------------
:: 3. Post-build: verify the binary + mirror it into the docs\downloads folder
:: ---------------------------------------------------------------------------
:POSTBUILD
echo.
if not exist "%~dp0DualTitle.exe" (
    echo [ERROR] Build failed - DualTitle.exe was not produced.
    goto END
)
echo [SUCCESS] Built DualTitle.exe ^(native PE32+ GUI, x64^).

echo [SELF-TEST] Running DualTitle.exe --self-test ...
"%~dp0DualTitle.exe" --self-test
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Self-test reported failures - review output above.
    goto END
)

if exist "%~dp0docs\downloads" (
    copy /y "%~dp0DualTitle.exe" "%~dp0docs\downloads\DualTitle.exe" >nul
    echo [Mirror] Updated docs\downloads\DualTitle.exe
)

echo.
echo Done. Launch "DualTitle.exe" or run install_dualtitle.bat to make it
echo searchable from the Windows Start Menu.

:END
pause
