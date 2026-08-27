@echo off
rem === ITS-MVP: Einmalige Einrichtung (venv + Abhaengigkeiten) ===
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo FEHLER: Python wurde nicht gefunden.
    echo Bitte Python von https://www.python.org/downloads/ installieren
    echo und beim Installieren "Add python.exe to PATH" ankreuzen.
    pause
    exit /b 1
)

echo Erstelle virtuelle Umgebung .venv ...
%PY% -m venv .venv
if errorlevel 1 (
    echo FEHLER beim Erstellen der virtuellen Umgebung.
    pause
    exit /b 1
)

echo Installiere Abhaengigkeiten ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt pytest
if errorlevel 1 (
    echo FEHLER bei der Installation der Abhaengigkeiten.
    pause
    exit /b 1
)

echo.
echo Fuehre Tests aus ...
".venv\Scripts\python.exe" -m pytest tests/ -q
echo.
echo === Einrichtung abgeschlossen. Zum Starten start.bat doppelklicken. ===
pause
