# Lizenzen Dritter und Datenquellen

Pappenheimer selbst steht unter der MIT-Lizenz (Datei `LICENSE`). Dieses Dokument nennt, was Dritte beisteuern und woher die Daten kommen.

## Im Repository

| Was | Wofür | Lizenz | Wo |
|---|---|---|---|
| Geist (Schrift) | Oberfläche | SIL Open Font License 1.1 | `ui/fonts/OFL.txt` |
| Phosphor Icons | Symbole in der Oberfläche | MIT | `ui/icons-LICENSE.txt` |
| Beispielsammlung | Zum Ausprobieren: eine Kartenliste und eine Deckliste mit Kartennamen, Editionen, Nummern und Scryfall-Kennungen, dazu erfundene Kaufpreise; keine Kartendaten (keine Texte, Preise oder Bilder), die holt die App bei Scryfall | MIT wie die App; die Kartennamen gehören Wizards of the Coast (Hinweis unten) | `beispiel/` |

## Beigelegte Programme

| Was | Wo | Lizenz |
|---|---|---|
| Tesseract OCR (liest beim Scannen den Namen der Karte) | im Docker-Image, als Paket `tesseract-ocr` aus Debian | Apache License 2.0 |
| GnuPG (verschlüsselt die Kopie der Sicherung im zweiten Ordner, nur mit Schlüsseldatei) | im Docker-Image, als Pakete `gpg` und `gpg-agent` aus Debian; auf dem Server ohne Docker das des Systems | GNU General Public License 3 oder neuer |
| Python (Laufzeit) | im Docker-Image (`python:3.13-slim`) und in der Windows-ZIP (eingebettetes Python von python.org) | Python Software Foundation License |

Der Kern der App braucht nur die Python-Standardbibliothek; es werden keine weiteren Python-Pakete mitgeliefert. Tesseract, GnuPG und ihre Bibliotheken behalten ihre eigenen Lizenzen, die im Image unter `/usr/share/doc/` liegen.

## Datenquellen

Die App liefert keine Kartendaten aus. Jede Installation ruft sie selbst ab, soweit der Betreiber das zulässt.

| Quelle | Wofür | Bedingungen | Schalter |
|---|---|---|---|
| Scryfall | Kartendaten, Bilder, Preise, Katalog aller Drucke | scryfall.com/docs/api | keiner (ohne Scryfall kein Import) |
| Cardmarket | Preisliste (Trend, ab, Schnitt) | Für die öffentliche Preisliste fand die Durchsicht vom 2026-10-12 keine Bedingungen; die Seite zur Schnittstelle (help.cardmarket.com/en/cardmarket-api) nennt nur die geschlossene Schnittstelle | an |
| EDHREC | Empfehlungen, Themen, Salt | edhrec.com/terms: keine offizielle Schnittstelle, automatische Anfragen und das Kopieren der Inhalte sind laut Bedingungen (Stand 2026-10-12) untersagt | in neuen Installationen aus |
| Commander Spellbook | Combos, Bracket-Schätzung | Für die Schnittstelle fand die Durchsicht vom 2026-10-12 keine Nutzungsbedingungen (der Quelltext des Servers steht unter der MIT-Lizenz) | an |

Die Bedingungen der Quellen gelten für den, der die Abrufe auslöst, also für den Betreiber der Installation. Deshalb hat jede Quelle außer Scryfall einen Schalter für die ganze Installation (Seite „Quellen“ in der App, oder die Umgebungsvariable `MTG_QUELLEN`); die Seite nennt je Quelle, was hingeschickt wird (nur Kartennamen und Kennungen) und wie oft.

## Magic: The Gathering

Pappenheimer is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Die App benutzt weder Logos noch Marken noch Manasymbole von Wizards; die Symbole sind eigene Zeichnungen aus Phosphor-Icons. Das Proxy-Blatt (Druckansicht) ist nicht durch die Fan Content Policy gedeckt, die Proxys ausdrücklich ausnimmt; der Aufdruck „Playtest“ bleibt Pflicht.
