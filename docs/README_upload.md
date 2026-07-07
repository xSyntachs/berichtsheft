# berichtsheft_upload.py

Nimmt einen Export-Ordner von `berichtsheft_download.py` und pflegt jeden Eintrag als Tätigkeitsnachweis in apprentio ein, an der richtigen Kalenderwoche. Läuft komplett über die apprentio-REST-API, kein Klicken durch die Wochenansicht.

## Was es macht

Beim Start fragt es E-Mail und Passwort ab, meldet sich am apprentio-Tenant an und liest die `berichtsheft.json` aus dem neuesten Export-Ordner (oder einem per `--ordner` genannten). Dann legt es pro IHK-Eintrag eine echte apprentio-Tätigkeit an, mit Datum, Zeitaufwand, Text, Anwesenheit, Ausbildungsort und, wo möglich, dem verknüpften Lernziel. Die passende Woche findet es automatisch, apprentio hat je Woche einen Report, dessen Startdatum aufs Eintragsdatum gemappt wird.

Der Lauf ist beliebig wiederholbar. Vorhandene Einträge (gleiches Datum plus gleicher Text) werden übersprungen, es entstehen keine Duplikate.

## Setup

Einmalig, Python 3.

```
pip install playwright
playwright install chromium
```

## Nutzung

Erst herunterladen, dann hochladen.

```
python src/berichtsheft_download.py            # IHK -> PDFs + JSON
python src/berichtsheft_upload.py              # JSON -> apprentio
```

Nach dem Upload reicht das Tool die befüllten Wochen automatisch ein (Status `SUBMITTED`). Davor kommt eine Sicherheitsabfrage, weil Einreichen endgültig ist. Nur der Prüfer kann eine eingereichte Woche per Ablehnen wieder öffnen.

Optionen.

```
python src/berichtsheft_upload.py --kein-einreichen                       # nur hochladen, nicht einreichen
python src/berichtsheft_upload.py --ja                                    # ohne Sicherheitsabfrage einreichen
python src/berichtsheft_upload.py --pruefer "Rumke"                       # Prüfer eingrenzen, falls mehrere möglich
python src/berichtsheft_upload.py --ordner "C:\...\Berichtsheft_2026-07-03_12-00-00"
python src/berichtsheft_upload.py --tenant https://deinetenant.apprentio.de
```

Den Tenant fragt das Tool beim ersten Lauf ab (Subdomain wie `xsyntachs` genügt) und merkt ihn in `berichtsheft_upload.config.json`, per `--tenant` überschreibbar. Melde dich mit dem Account an, dem das Berichtsheft gehören soll. Ein Admin-Account funktioniert auch, die Einträge landen im Report des Azubis, sauberer ist der Azubi-Account selbst.

## Wie es funktioniert

apprentio ist eine Laravel-App mit einer REST-API unter `/api/v1`. Die Session läuft über Cookies, schreibende Aufrufe brauchen den `X-XSRF-TOKEN` aus dem `XSRF-TOKEN`-Cookie. Beides erledigt `api` über einen Fetch im Seitenkontext, dort greifen Cookies automatisch.

### Reports sind die Wochen

`GET /api/v1/reporting/reports?page_size=1000` liefert alle Wochen. Jeder Report hat `from` (Montag) und `to` (Sonntag) plus eine `id`. `load_reports` baut daraus eine Map von `from`-Datum auf Report-ID. Weil die Downloader-PDFs und die JSON-Wochen über das Montagsdatum indiziert sind, passt das Mapping direkt.

### Tätigkeiten anlegen

Je Eintrag ein `POST /api/v1/reporting/activities`. Pflichtfelder sind `description`, `minutes_used`, `date_accomplished`, `report_id`. Optional `presence` und `location`, beides Enums.

Die Enum-Werte, live gegen die API ermittelt.

- `presence`: `PRESENT`, `ABSENT`, `HOLIDAY` (Urlaub), `PUBLIC_HOLIDAY` (Feiertag)
- `location`: `COMPANY` (Ausbildungsstätte), `SCHOOL`

Die Maps `PRESENCE` und `LOCATION` oben in der Datei übersetzen die IHK-Werte (`ANWESEND`, `BETRIEB`, ...) dorthin.

Das `description`-Feld akzeptiert HTML und speichert es unverändert, der Rich-Text-Editor in apprentio rendert es. Freitext-Einträge aus der IHK behalten so ihre Formatierung (Listen, Absätze, Fett).

### Lernziele verknüpfen

Nach dem Anlegen, wenn Qualifikationen dranhängen, ein `POST /api/v1/reporting/activities/{id}/curriculum-entries` mit `{"curriculum_entry_ids": [...]}`. Die IDs kommen aus `load_curriculum`, das `GET /api/v1/qualification/curriculum-entries` lädt und die apprentio-Lernziele per normalisiertem Titel auf die IHK-Qualifikationen mappt. Findet sich kein Titel-Match, wandert der IHK-Qualifikationsname als `[Qualifikation: ...]` in den Text, damit nichts verloren geht.

### Einreichen

Nach dem Upload läuft `submit_reports` über alle Wochen im Status `CREATING` mit mindestens einer Tätigkeit. Je Woche fragt es die möglichen Prüfer ab (`GET /api/v1/users-location-independent-simple?f[possible_reviewers_for_report]={report_id}`) und setzt die Woche per `PATCH /api/v1/reporting/reports/{id}` mit `state: SUBMITTED` und `reviewer_id`. Bei genau einem möglichen Prüfer wird der automatisch gewählt, sonst grenzt `--pruefer <Name>` ein. `SUBMITTED` ist serverseitig eine Einbahnstraße, ein direktes Zurück-PATCH auf `CREATING` wird ignoriert, nur der Prüfer öffnet die Woche per Ablehnen wieder.

### Geschwindigkeit

Statt jede Tätigkeit einzeln über einen Python-Browser-Roundtrip anzulegen, bündelt `BATCH_JS` bis zu `BATCH_SIZE` POSTs in einem `page.evaluate` und feuert sie parallel per `Promise.all`. Das ist grob achtmal schneller. Ein Rate-Limit war im Test nicht zu beobachten.

## Datenmodell

Der Uploader teilt die Eintragslogik mit dem Downloader. Ein IHK-Eintrag ist entweder flach (`text` direkt) oder ein Wrapper mit `betrieb` und `schule`, die den echten Eintrag halten (Freitext-Hefte). `flatten_entries` macht beides flach. `iter_entries` liefert je Eintrag ein Tupel `(datum, anwesenheit, ort, text, dauer_iso, quali_ids)` und lässt leere Einträge weg. Details zu den zwei Eintragsformen stehen im README des Downloaders.

## Fehlersuche

**`Reports nicht lesbar (HTTP 403)`.** Der angemeldete Account hat kein Berichtsheft-Recht, oder das Modul ist für den Tenant nicht aktiv. Mit einem Account anmelden, der die Tätigkeitsnachweise sieht.

**Wochen fehlen am Ende ("X Wochen ohne apprentio-Report").** Für diese Montage gibt es in apprentio keinen Report, meist weil sie vor dem in apprentio hinterlegten Ausbildungsbeginn liegen. Die Ausbildungszeiträume in IHK und apprentio müssen sich decken.

**Einträge tauchen im Report nicht auf.** Neu angelegte Wochen stehen auf Status `CREATING` ("Erstellend"). Für den Admin-Blick gibt es dann keine Detailansicht, als Azubi unter `/report` sind alle Tätigkeiten sichtbar. Sichtbar und abnehmbar für den Ausbilder werden sie erst nach dem Einreichen (Status `SUBMITTED`).

## Weiterentwickeln

- **Wieder-Öffnen.** Eingereichte Wochen (`SUBMITTED`) lassen sich per API nicht zurücksetzen, das läuft nur über den Prüfer-Ablehnen-Flow in der Oberfläche. Ein Skript, das diesen Review-Endpoint bedient und so hängende Testläufe wieder öffnet, wäre der nächste Ausbau.
- **PDF anhängen.** apprentio-Tätigkeiten haben ein `attachment`. Der Upload-Endpoint dafür ist noch nicht verdrahtet, falls die Wochen-PDF zusätzlich hängen soll, muss der als Multipart-POST ergänzt werden.
- **Anderer Beruf, anderer Lehrplan.** Das Titel-Matching in `load_curriculum` ist rein textbasiert. Bei abweichenden Bezeichnungen zwischen IHK und apprentio matcht weniger, dann greift der `[Qualifikation: ...]`-Fallback. Ein ID- oder Katalog-Mapping wäre robuster.
- **Verifikation.** `minutes`, `norm`, `flatten_entries` und `iter_entries` sind ohne Browser testbar, der Playwright-Import liegt in `main`. Gegen echte Wochen-JSON testen.

## Grenzen

Das Tool schreibt in ein Produktivsystem. Vor dem ersten echten Lauf mit einem Testkonto oder wenigen Wochen prüfen, ob Format und Zuordnung stimmen. Die Dedup-Prüfung schützt vor Doppelanlage, nicht vor falsch gemappten Wochen. Löschen geht nur einzeln über `DELETE /api/v1/reporting/activities/{id}` oder die apprentio-Oberfläche.
