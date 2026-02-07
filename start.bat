@echo off
title IPTV Portal Checker PRO MAX
color 0a

echo Starte IPTV Portal Checker PRO MAX...
echo.

REM Prüfen, ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo Python wurde nicht gefunden.
    echo Bitte installiere Python 3.10 oder neuer.
    pause
    exit /b
)

REM Selenium + WebDriver Manager installieren
pip install selenium webdriver-manager requests --quiet

REM Projekt starten
python checker.py

echo.
echo Fertig.
pause
