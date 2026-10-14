@echo off
rem Doppelklick: laufende Oberflaeche beenden, auch wenn ihr Fenster schon zu ist. Neu starten mit "Pappenheimer starten.cmd".
call "%~dp0mtg.cmd" stop
timeout /t 5
