@echo off
rem mtg: mit der venv, sonst mit dem mitgelieferten Python (ZIP aus deploy/paket.py), sonst mit dem installierten Python (der Kern braucht nur die Standardbibliothek)
set "MTG_PY=%~dp0.venv\Scripts\python.exe"
if exist "%MTG_PY%" goto run
set "MTG_PY=%~dp0python\python.exe"
if exist "%MTG_PY%" goto run
set "MTG_PY=py"
where py >nul 2>nul && goto run
set "MTG_PY=python"
where python >nul 2>nul && goto run
echo Python fehlt. Bitte von https://www.python.org/downloads/ installieren, beim Setup "Add python.exe to PATH" anhaken.
exit /b 9009
:run
"%MTG_PY%" "%~dp0mtg.py" %*
