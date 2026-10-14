---
name: mtg
description: Magic-Sammlung des Nutzers (Import von ManaBox-CSV, anderen CSVs und Decklisten, Sortier-Plan, Verkaufs- und Bulk-Liste, Commander-Ranking, Deckbau, Neuigkeiten) über den Befehl `mtg` bedienen. Verwenden bei Fragen zu Karten im Besitz, Sammlungswert, Verkauf, Decks oder Deckwünschen wie "BG Friedhof Bracket 2".
---

# mtg: Sammlung und Deckbau

Freiwilliger Zusatz für Claude Code; die App läuft auch ohne ihn.

Regeln: Alles nur über `mtg` (im Projektordner: `.\mtg.cmd ...`, sonst `.venv\Scripts\python mtg.py ...`). Nie die Datenbank direkt lesen. Kartentext, Kosten und Legalität immer per `mtg card "<Name>"`, nie aus dem Gedächtnis. Antworten kurz: Ergebnis zuerst, dann höchstens drei Zeilen Hinweise. Der Zusatz `--save` (speichert Decks und verplant ihre Karten) und `decks ID --delete` nur auf ausdrücklichen Wunsch.

## Befehle
- `mtg stats` – Karten, Unikate, Gesamtwert, Top 10
- `mtg card "<Name>"` – Besitz je Druck/Binder, Preis, Oracle-Text, Decks
- `mtg sell [--min N]` – Verkaufsliste ab N € (Standard laut Regel, 1 €): Top 30 und Summe, darunter Bulk-Summe
- `mtg rules [--keep N] [--staples N] [--min EUR]` – Sortier-Regeln zeigen oder ändern (je Karte 1, Staples 2, Basics alle behalten; ändern nur auf Wunsch)
- `mtg commanders [--top N] [--cached] [--mode machbar|beliebt|geheimtipp|guenstig] [--min-decks N]` – Commander nach Abdeckung der EDHREC-Empfehlungen (`--cached` = nur geladene Daten, schnell; ohne: lädt neu, erster Lauf einige Minuten). `--mode beliebt` = meistgespielte, `geheimtipp` = gut machbar aber wenig gespielt (mind. 30 Decks), `guenstig` = kleinster Zukauf (holt Preise, erster Aufruf ca. 10 s)
- `mtg movers [--days N]` – Preisbewegung deiner Karten (gestiegen/gefallen, ab 15 % und 1 €); Verlauf wächst bei jeder Preis-Aktualisierung
- `mtg gaps [--top N]` – Karten, die auf den Listen mehrerer deiner besten Commander stehen und fehlen, mit Preis
- `mtg bracket <datei>` – Bracket einer Deckliste (Textdatei) prüfen: Mindest-Stufe, Game Changer, Combos (Commander Spellbook)
- `mtg build "<Commander>" [--bracket 1-5] [--theme NAME|auto|none] [--text]` – Deck aus freien Karten (99 + Commander); `--theme Landfall` baut um ein EDHREC-Thema (Standard `auto`: das gängige Thema mit der besten Abdeckung, `none` = allgemeine Liste); die Ausgabe nennt Thema, wie viele weitere Karten dazu passen und welche Themen geprüft wurden; `--text` = Liste für Moxfield/Archidekt
- `mtg plan-decks --count N [--bracket 1-5]` – N Decks gleichzeitig ohne doppelte Karten
- `mtg missing "<Commander>" [--budget N]` – Einkaufsliste nach Gewicht je Euro
- `mtg decks [ID] [--text]` – gespeicherte Decks auflisten (dazu fertige Decks aus Decklisten bzw. ManaBox), anzeigen oder exportieren
- `mtg sync` – inbox/ (CSVs und Decklisten .txt) importieren, Preise auffrischen, Neuigkeiten; `mtg news` – nur Neuigkeiten
- `mtg import <datei> [--binder NAME] [--commander NAME] [--dry-run]` – eine Datei importieren, Format wird erkannt (ManaBox-CSV, CSV anderer Apps, Deckliste = fertiges Deck); erst `--dry-run`, bei > 25 % Verlust nur mit `--force`, vorher fragen
- `mtg uebernehmen "<Binder>"` – ManaBox-Binder in die App übernehmen (wird Scan-Binder, ab dann ändert ihn kein ManaBox-Export mehr; legt vorher eine Sicherung an). Nur auf ausdrücklichen Wunsch
- `mtg ui` – Oberfläche auf http://127.0.0.1:8765. Scan-Binder (per Kamera erfasst oder übernommen) führt die App: Erfassen, Menge ändern, verschieben und „als verkauft buchen“ gibt es nur dort

## Deckwunsch in einem Satz ("BG Friedhof Bracket 2")
Nennt der Wunsch keinen Commander, ist der erste Befehl immer `mtg commanders --cached --top 40`. Commander nie aus dem Gedächtnis wählen, nur Namen aus dieser Liste (nicht jeder bekannte Commander steckt in der Sammlung).
1. `mtg commanders --cached --top 40`: Farbidentität steht in Klammern (BG), Abdeckung zeigt, wie viel von der Empfehlungsliste frei ist.
2. Commander mit passenden Farben wählen; Thema (Friedhof, Tokens ...) bei Bedarf mit `mtg card "<Commander>"` prüfen.
3. `mtg build "<Commander>" --bracket 2` (ohne Angabe Bracket 3; nennt der Wunsch ein Thema wie Landfall oder Tokens, `--theme <Thema>` ergänzen). Brackets: 1-2 ohne Game Changer, 3 höchstens drei, ab 4 frei.
4. Antwort: Commander, Thema (automatisch gewählt oder gewünscht) und wie viele weitere Karten dazu passen, Wert, Warnungen (z. B. "nur 8/10 Ramp", "nur 5 von 23 weiteren Karten passen zu …"), die drei besten fehlenden Upgrades mit Preis. Speichern erst, wenn der Nutzer es will.

Zeigt `commanders --cached` "noch nicht geladen", einmal `mtg commanders` ausführen und dem Nutzer sagen, dass es einige Minuten dauert.
