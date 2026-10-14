@echo off
title Pappenheimer
rem Doppelklick: Oberflaeche (neu) starten und Browser oeffnen. Laeuft schon eine, wird sie vorher beendet (neuer Code, freier Port).
rem Legt beim ersten Mal die Verknuepfung "Pappenheimer" mit Kartensymbol auf Desktop und Startmenue an (mtg verknuepfung).
rem Fenster offen lassen, Schliessen beendet die Seite. Beenden geht auch mit "Pappenheimer beenden.cmd".
call "%~dp0mtg.cmd" verknuepfung
call "%~dp0mtg.cmd" stop
call "%~dp0mtg.cmd" ui %*
pause
