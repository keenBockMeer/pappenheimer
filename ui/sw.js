// Service Worker ohne eigene Logik (Phase 27): Samsung Internet bietet „App installieren“ nur an, wenn die Seite einen hat. Er speichert
// nichts zwischen und beantwortet nichts selbst, jede Anfrage geht wie bisher ans Netz.
// Das ist Absicht (PLAN E32): Ein Service Worker, der Dateien zwischenspeichert, brächte nach einem Update alten Code und nützt nichts, weil jede
// Ansicht den Server braucht. Schnell laden geht über den ETag und gzip des Servers (server.py, Phase 48); dort gilt nach einem Update sofort der neue Code.
self.addEventListener('fetch', () => {});
