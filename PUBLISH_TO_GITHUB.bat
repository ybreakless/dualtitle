@echo off
chcp 65001 >nul
title DualTitle — 1-Click GitHub & GitHub Pages Publisher
cls
echo ==============================================================================
echo         DUALTITLE — 1-CLICK GITHUB REPOSITORY ^& PAGES PUBLISHER
echo ==============================================================================
echo.
echo This wizard initializes Git in this folder, commits DualTitle.exe, the C++17
echo source code, and the GitHub Pages website (docs/index.html), and pushes them
echo directly to your GitHub repository.
echo.

where git >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Git is not installed or not in PATH. Install Git from https://git-scm.com/
    echo     or upload this folder directly via the GitHub web interface.
    pause
    goto END
)

set /p REPO_URL="Paste your GitHub Repository URL (e.g. https://github.com/yourname/dualtitle.git): "
if "%REPO_URL%"=="" (
    echo [!] No repository URL entered. Cancelled.
    pause
    goto END
)

git init
git branch -M main
git add .
git commit -m "Release DualTitle v4.1 (.exe Launcher, Anti-Cheat-Safe Overlay HUD, Save Restore & GitHub Pages)"
git remote remove origin >nul 2>nul
git remote add origin %REPO_URL%
git push -u origin main --force

echo.
echo ==============================================================================
echo [SUCCESS] Pushed to GitHub!
echo To activate your live website:
echo   1. Open your repository on GitHub -> Settings -> Pages
echo   2. Under "Build and deployment", select "GitHub Actions" (or "Deploy from a branch" -> main -> /docs)
echo ==============================================================================
pause
:END
