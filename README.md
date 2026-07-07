# Berichtsheft-Suite

Migriert das digitale IHK-Berichtsheft (Fachinformatiker Anwendungsentwicklung, IHK Hannover) automatisiert nach apprentio. Kein manuelles Abtippen, kein Copy-Paste durch die Wochenansicht.

Das Werkzeug lädt jede Ausbildungswoche als PDF plus strukturierte JSON aus dem IHK-Portal herunter und pflegt jeden Eintrag als Tätigkeitsnachweis in apprentio ein, an der richtigen Kalenderwoche, mit Datum, Zeitaufwand, Anwesenheit, Ausbildungsort und verknüpftem Lernziel. Der Lauf ist wiederholbar, Duplikate werden erkannt.

## Schnellstart

```bash
pip install -r requirements.txt
playwright install chromium

python src/berichtsheft_download.py    # IHK  -> PDFs + berichtsheft.json
python src/berichtsheft_upload.py      # JSON -> apprentio, danach Auto-Einreichen
```

Oder ein Menü für alles.

```bash
python src/berichtsheft.py
```

Das Menü führt per Auswahl durch jeden Schritt, auch den Import aus einer Word-Datei (Menüpunkt `word`, ohne Login und ohne Browser).

## Architektur auf einen Blick

```
   IHK-Portal                     lokaler Export                 apprentio
   (Angular-SPA,                  (eine PDF + eine                (Laravel-App,
    Keycloak-SSO)                  JSON pro Woche)                 REST /api/v1)
        |                               |                              |
        |   berichtsheft_download.py    |    berichtsheft_upload.py    |
        |  ---------------------------> |  --------------------------> |
        |   REST lesen, Header          |   Tätigkeiten anlegen,       |
        |   abhören, PDF rendern        |   Lernziele verknüpfen,      |
        |                               |   Wochen einreichen          |
```

Zwei eigenständige Skripte, verbunden nur über den Export-Ordner. Der Downloader spricht die IHK-REST-API direkt an und hört den Auth-Token aus dem Netzwerkverkehr ab, statt das DOM zu scrapen. Der Uploader schreibt über die apprentio-REST-API mit Cookie-Session. Details in [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Bestandteile

| Datei | Rolle |
|---|---|
| `src/berichtsheft.py` | Launcher mit Menü, verteilt auf die Werkzeuge |
| `src/berichtsheft_download.py` | IHK zu PDF plus `berichtsheft.json` |
| `src/berichtsheft_upload.py` | Export nach apprentio, Auto-Einreichen |
| `src/berichtsheft_reset.py` | löscht apprentio-Tätigkeiten (nur Demo-Build, Testwerkzeug) |
| `src/berichtsheft_review.py` | Ausbilder-Sicht, Wochen annehmen/ablehnen (nur Demo-Build) |
| `packaging/build.ps1` | baut vier EXE/Binaries (Windows und Linux, je Release und Demo) |

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) | Systemüberblick, Datenfluss, Datenmodell, Build |
| [docs/ENTSCHEIDUNGEN.md](docs/ENTSCHEIDUNGEN.md) | Architekturentscheidungen mit Begründung und Nutzwertanalyse |
| [docs/SICHERHEIT.md](docs/SICHERHEIT.md) | Datenschutz, Umgang mit Zugangsdaten, Rechtliches |
| [docs/README_download.md](docs/README_download.md) | Bedienung und Innenleben des Downloaders |
| [docs/README_upload.md](docs/README_upload.md) | Bedienung und Innenleben des Uploaders |
| [docs/README_exe.md](docs/README_exe.md) | Nutzung der gebauten EXE, Windows-Warnung, Neubau |

## Sicherheit

Das Werkzeug verarbeitet echte Zugangsdaten und schreibt in ein Produktivsystem. Ein optional in `berichtsheft_*.config.json` hinterlegtes Passwort steht dort im Klartext. Diese Dateien und der Export-Ordner gehören nicht in fremde Hände und nicht in ein Repository. Das mitgelieferte `.gitignore` schließt beide aus. Volles Konzept in [docs/SICHERHEIT.md](docs/SICHERHEIT.md).

## Tests

Die browserfreie Kernlogik des Uploaders ist ohne Playwright testbar.

```bash
python tests/test_upload.py
```

## Stand

Version 1.0.0. Gegen den Tenant `xsyntachs` mit einem Test-Azubi bewiesen wurden der Self-Submit, ein voller Upload-Lauf samt Dedup, das Nachladen von Chromium im gefrorenen Build und alle Menüs. Der Chromium-Browser wird nicht mitgeliefert, sondern beim ersten Start nachgeladen (rund 150 MB in den Benutzer-Cache).
