# Pappenheimer auf dem eigenen Server (PLAN E13). Python nur mit der Standardbibliothek, keine Pakete. Dazu ein Programm: Tesseract liest
# beim Scannen den Namen der Karte (Phase 35, PLAN E21; rund 105 MB mit seinen Bibliotheken, das englische Modell genügt auch für deutsche Namen).
# Dazu gpg (Phase 42, PLAN E30): Die App verschlüsselt die Kopie der Sicherung im zweiten Ordner damit, wenn eine Schlüsseldatei da ist
# (MTG_AUSSEN_SCHLUESSEL). Ein eigenes Programm wie Tesseract, ohne Schlüsseldatei wird es nicht benutzt. gpg-agent gehört dazu: Ohne ihn
# schreibt gpg 2.4 die verschlüsselte Datei zwar, endet aber mit einem Fehler, und die App kopiert dann nichts (am Server gemessen, 2026-10-13).
# Anleitung: README, Abschnitt „Auf dem eigenen Server“.
FROM python:3.13-slim
# Verknüpft das Image in der Registry von GitHub mit dem Repository (dessen Sichtbarkeit und Rechte gelten dann auch für das Paket); die Adresse wie version.REPO
LABEL org.opencontainers.image.source="https://github.com/keenBockMeer/pappenheimer" org.opencontainers.image.title="Pappenheimer" org.opencontainers.image.licenses="MIT"
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr gpg gpg-agent && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN useradd --uid 1000 --create-home mtg && mkdir -p /app/data && chown mtg /app/data
COPY --chown=mtg mtg.py server.py sources.py deckbuild.py konten.py suche.py llm.py katalog.py version.py ./
COPY --chown=mtg LICENSE LIZENZEN.md ./
COPY --chown=mtg ui ./ui
# Die Beispielsammlung (Phase 47, PLAN E33): zwei Kartenlisten mit Kennungen und Namen, keine Kartendaten; die holt der Import bei Scryfall.
COPY --chown=mtg beispiel ./beispiel
USER mtg
ENV PYTHONUNBUFFERED=1 MTG_DB=/app/data/mtg.db
VOLUME /app/data
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/favicon.svg', timeout=4)"]
# ohne Hauptkonto startet der Server im Modus „Einrichtung“ (Phase 43, PLAN E28): Er antwortet nur auf die Einrichtungsseite, der Code dafür
# steht im Protokoll (docker compose logs mtg). Wie bisher geht auch: docker compose run --rm mtg konto add NAME --haupt
ENTRYPOINT ["python", "mtg.py"]
CMD ["ui", "--host", "0.0.0.0", "--no-open"]
