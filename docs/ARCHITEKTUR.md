# Architektur

Wie die Berichtsheft-Suite aufgebaut ist und warum sie so zerfällt, wie sie zerfällt. Dieses Dokument erklärt das System. Für die Bedienung der einzelnen Werkzeuge sind die jeweiligen READMEs zuständig, für die Begründung der Technikwahl das Dokument [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md).

## Systemkontext

Zwei fremde Systeme stehen am Anfang und am Ende, dazwischen liegt der lokale Rechner.

Die Quelle ist das digitale IHK-Berichtsheft auf `bildung.service.ihk.de`, eine Angular-Single-Page-Application mit JSON-REST-Backend und Keycloak-Single-Sign-on über `login.gfi.ihk.de`. Das Ziel ist apprentio, eine Laravel-Anwendung mit REST-API unter `/api/v1` und Cookie-Session. Beide Systeme sind produktiv und werden nicht verändert, das Werkzeug liest aus dem einen und schreibt in das andere.

Der lokale Rechner hält nur den Zwischenstand, einen Export-Ordner pro Lauf.

## Datenfluss

```
  ┌───────────────────┐        ┌──────────────────────┐        ┌───────────────────┐
  │   IHK-Portal      │        │   Export-Ordner       │        │    apprentio      │
  │                   │        │                       │        │                   │
  │  REST + Keycloak  │        │  berichtsheft.json    │        │  REST /api/v1     │
  └─────────┬─────────┘        │  KW31.pdf ... KWnn.pdf│        └─────────▲─────────┘
            │                  └──────────▲────────────┘                  │
            │                             │                               │
            │  berichtsheft_download.py   │      berichtsheft_upload.py   │
            └─────────────────────────────┘───────────────────────────────┘
              1. Login, Token abhören          1. Login, Reports laden
              2. Wochen per REST ziehen         2. Einträge mappen, Dedup
              3. JSON + PDF schreiben           3. Batch-Upload, Einreichen
```

Der Export-Ordner ist die einzige Kopplung. Downloader und Uploader teilen keinen Code und keinen Zustand, sie kennen nur das Dateiformat. Das ist Absicht, ein früherer Cross-Import ist auf einer fremden Maschine gebrochen, siehe [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md).

Die Wochen sind über das Montagsdatum indiziert, sowohl in den PDF-Dateinamen als auch als Schlüssel in der JSON. Dadurch mappt der Uploader jede Woche ohne Zusatzlogik auf den passenden apprentio-Report, dessen `from`-Feld ebenfalls der Montag ist.

## Komponenten

| Komponente | Verantwortung | Kernfunktionen |
|---|---|---|
| `src/berichtsheft.py` | Launcher, Menü, verteilt an ein Werkzeug, blendet den Reset je nach Build ein | `select`, `main` |
| `src/berichtsheft_download.py` | IHK-Login und Wochen ziehen oder Word-Import (Menüpunkt `word`), JSON und PDF schreiben | `wait_for_login`, `collect_weeks`, `import_docx`, `import_docx_interactive` |
| `src/berichtsheft_upload.py` | apprentio-Login, Einträge anlegen, Lernziele verknüpfen, einreichen | `iter_entries`, `apply_default_hours`, `submit_reports` |
| `src/berichtsheft_reset.py` | apprentio-Tätigkeiten löschen, parallel in Batches (Testwerkzeug) | `main` |
| `src/berichtsheft_review.py` | Ausbilder-Sicht, Wochen annehmen, ablehnen, Annahme zurücknehmen (Testwerkzeug) | `main` |

Reset und Review sind reine Testwerkzeuge und stecken nur im Demo-Build. Der Release-Build blendet sie aus, gesteuert über die Konstante `DEMO`.

## Zwei Authentifizierungsmodelle

Die schwierigste Stelle des Systems ist die Anmeldung, und sie ist an den beiden Enden grundverschieden.

### IHK, Token aus dem Netzwerkverkehr abhören

Die IHK-SPA schreibt den angemeldeten Benutzer und die gewählte Organisation nicht zuverlässig in den `sessionStorage`, auf einem frisch geladenen Tab ist der oft leer. Ein Skript, das dort nachliest, findet nichts Verlässliches.

Stattdessen registriert `make_sniffer` einen Request-Listener auf dem Browser-Kontext. Sobald die SPA einen echten API-Call mit `Authorization`-Header absetzt, fängt der Sniffer den Bearer-Token und die vier Organisations-Header ab. Erst wenn diese Header vorliegen, gilt die Session als nutzbar. Die anschließenden Wochen-Abfragen laufen im Seitenkontext über `page.evaluate`, dort greifen Cookies und CORS automatisch.

Eine Falle steckt in Playwrights synchroner API. Request-Events werden nur während eines Playwright-Aufrufs ausgeliefert. Ein blankes `time.sleep` lässt sie verhungern und der Sniffer bleibt blind. Deshalb wartet der Downloader über `_pump`, das intern `wait_for_timeout` aufruft, niemals über `time.sleep`.

### apprentio, Cookie-Session mit XSRF-Token

apprentio ist bequemer. Die Session läuft über Cookies, schreibende Aufrufe brauchen zusätzlich den `X-XSRF-TOKEN`, der aus dem `XSRF-TOKEN`-Cookie stammt. Beides erledigt die Funktion `api` über einen `fetch` im Seitenkontext. Der Login-Zustand wird über `GET /api/v1/users/me` geprüft.

## Datenmodell

Die IHK liefert je Woche `tagesBerichte` (sieben Tage) und optional einen `wochenEintrag`. Ein einzelner Eintrag hat zwei mögliche Formen, und beide kommen in echten Konten vor.

Ein **Stichpunkt-Eintrag** (`typus == "StichpunktEintragDto"`) trägt Klartext im Feld `text`. Ein **Freitext-Eintrag** (`typus == "FreitextEintragDto"`) trägt HTML im selben Feld. Führt eine Nachwuchskraft das Heft komplett als Freitext, steckt der Text zusätzlich verschachtelt unter einem Wrapper mit den Zweigen `betrieb` und `schule`.

`flatten_entries` löst beide Formen auf und liefert immer die konkreten Einträge. Diese Funktion existiert in Downloader und Uploader getrennt, weil die Skripte keinen gemeinsamen Code teilen, ihr Verhalten ist identisch. `is_html_entry` entscheidet im Downloader über die Darstellung, mit einer Tag-Regex als Rückfall, damit ein `<>` im Klartext nicht fälschlich als HTML zerbricht.

Beim Upload sorgt ein normalisierter Vergleichsschlüssel für den Dedup. apprentio speichert die Beschreibung als HTML, escapt `<`, `>` und `&` und schließt offene Tags. Gesendeter Rohtext und gespeicherte Fassung sind also nie zeichengleich. `dedup_key` streift Tags, löst HTML-Entities auf und normalisiert Whitespace, damit beide Seiten auf denselben Kern fallen und ein Wiederholungslauf keinen Eintrag doppelt anlegt.

## Zeiterfassung

Freitext-Einträge liefern oft `PT0S` als Dauer. Der Uploader füllt Tage ohne echte Stunden über `apply_default_hours` auf acht Stunden auf, verteilt auf die Einträge des Tages. Ein reines Wochenheft, dessen Text nur im `wochenEintrag` steht, verteilt `iter_entries` auf die anwesenden Werktage, weil apprentio tagesbasiert arbeitet. Der Schalter `--stunden 0` lässt die echten Werte unangetastet.

## Reviewer-Zustandsmaschine

Ein apprentio-Report durchläuft Zustände, alle über denselben PATCH mit wechselndem `state`. Gültig sind `CREATING`, `SUBMITTED`, `ACCEPTED` und `DECLINED`. Der Uploader bewegt eine Woche von `CREATING` nach `SUBMITTED`. Das Ausbilder-Werkzeug bedient die Prüferseite, `SUBMITTED` nach `ACCEPTED` (annehmen), `SUBMITTED` nach `DECLINED` (ablehnen), `ACCEPTED` nach `DECLINED` (Annahme zurücknehmen) und `DECLINED` nach `SUBMITTED` (erneut vorlegen).

```
   CREATING ──submit──> SUBMITTED ──accept──> ACCEPTED
                          │  ▲                    │
                        decline│reopen          decline
                          ▼  │                    │
                        DECLINED <────────────────┘
```

Kein Zustand führt zurück nach `CREATING`. Ein Vorwärts-only-Sprung dorthin quittiert der Server mit HTTP 200, ohne den Zustand zu ändern. Deshalb lassen sich Einträge einer bereits eingereichten oder angenommenen Woche nicht mehr löschen.

## Build und Auslieferung

Die Skripte laufen direkt unter Python 3. Für die Auslieferung an Rechner ohne Python baut `packaging/build.ps1` vier gefrorene Artefakte über PyInstaller, Windows und Linux, je als Release ohne Testwerkzeuge und als Demo mit.

Drei Eigenheiten prägen den Build.

Der **Demo-Schalter** kommt aus einer Datei `src/_buildcfg.py`, die der Build je Variante mit `DEMO = False` oder `DEMO = True` schreibt und danach wieder entfernt. Aus dem Quellcode gestartet fehlt die Datei, dann gilt Entwicklung und `DEMO` ist `True`, der Reset also sichtbar.

Der **Chromium-Browser** wird bewusst nicht eingebacken. Das hielte die Datei klein und löste sie von einer festen Browser-Version. Beim ersten Start lädt `ensure_chromium` den Browser passend nach. Im gefrorenen Onefile-Modus ist `sys.executable` die EXE statt Python, deshalb fährt die Funktion den Playwright-Driver direkt und pinnt den Browser-Cache auf einen festen Pfad, sonst läge er im flüchtigen Temp-Entpackordner.

Das **Linux-Binary** entsteht nur über Docker (`python:3.13` plus `binutils`), weil PyInstaller nicht cross-kompiliert und jede Plattform ihr eigenes Binary braucht. Läuft kein Docker, überspringt der Build den Linux-Teil und meldet das.
