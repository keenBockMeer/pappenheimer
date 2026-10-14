"""Name, Version und Adresse des Projekts an einer Stelle (PLAN E22, E24). Ohne Importe, damit jedes Modul sie lesen kann, auch sources.py."""

NAME = "Pappenheimer"
VERSION = "0.9.0"  # SemVer; 1.0.0 folgt nach den ersten Rückmeldungen von außen
# Adresse des Repositorys: User-Agent, Dockerfile (Etikett), README; das Image in der Registry von GitHub heißt danach (deploy/release.py: image).
REPO = "https://github.com/keenBockMeer/pappenheimer"
USER_AGENT = f"pappenheimer/{VERSION} (+{REPO})"  # Scryfall verlangt Name und aktuelle Version der Anwendung

# Hinweis der Fan Content Policy von Wizards im Wortlaut der Policy (company.wizards.com/en/legal/fancontentpolicy, abgerufen 2026-10-12).
# Steht im Fuß (ui/index.html), in der Hilfe und in der README; Test: test_fuss_hinweis_lizenz_und_name.
HINWEIS = ("Pappenheimer is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. "
           "Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.")
