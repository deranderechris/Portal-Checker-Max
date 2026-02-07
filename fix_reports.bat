@echo off
title IPTV Portal Checker - Auto HTML Fix
color 0a

echo ============================================
echo   AUTO-FIX: Fehlende .html Endungen reparieren
echo ============================================
echo.

set BASE=ausgabe

if not exist "%BASE%" (
    echo Ordner "ausgabe" wurde nicht gefunden.
    echo Bitte im Hauptordner des Checkers ausfuehren.
    pause
    exit /b
)

setlocal enabledelayedexpansion
set COUNT=0

for /r "%BASE%" %%F in (*) do (
    rem Datei hat KEINE Endung?
    echo %%~xF | findstr /r "^$" >nul
    if not errorlevel 1 (
        echo Fix: %%F  ^>  %%F.html
        ren "%%F" "%%~nxF.html"
        set /a COUNT+=1
    )

    rem Datei hat eine Endung, aber nicht .html?
    if /i not "%%~xF"==".html" (
        if not "%%~xF"=="" (
            echo Fix: %%F  ^>  %%F.html
            ren "%%F" "%%~nxF.html"
            set /a COUNT+=1
        )
    )
)

echo.
echo Fertig. !COUNT! Dateien repariert.
echo.
pause
