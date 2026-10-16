@echo off
title Pappenheimer
rem Doppelklick: Pappenheimer (neu) starten, in einem eigenen Fenster (Edge oder Chrome im App-Modus). Laeuft schon eins, wird es vorher beendet (neuer Code, freier Port).
rem Legt beim ersten Mal die Verknuepfung "Pappenheimer" mit Kartensymbol auf Desktop und Startmenue an (mtg verknuepfung).
rem Dieses schwarze Fenster schliesst sich gleich wieder; das Fenster von Pappenheimer schliessen beendet es. Ohne Edge und Chrome oeffnet sich der Browser, dann dieses Fenster offen lassen.
call "%~dp0mtg.cmd" verknuepfung
call "%~dp0mtg.cmd" stop
call "%~dp0mtg.cmd" ui --fenster %*
if errorlevel 1 pause
