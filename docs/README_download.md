# berichtsheft_download.py

Zieht das komplette digitale IHK-Berichtsheft von meineihk.service.ihk.de und legt pro Kalenderwoche eine PDF plus eine JSON mit allen Rohdaten ab. Kein manuelles Klicken, kein Copy-Paste aus der Wochenansicht.

## Was es macht

Beim Start fragt es E-Mail, Passwort und deinen IHK-Standort ab. Danach öffnet sich ein Chromium-Fenster, das Skript loggt sich selbst ein (Cookie-Banner, IHK-Auswahl, zweistufiger Keycloak-Login) und holt jede Woche vom Ausbildungsbeginn bis heute. Am Ende liegen im Ausgabeordner

- `berichtsheft.json`, alle Wochen strukturiert plus Stammdaten und Qualifikationen
- `2023-07-31_KW31.pdf` und so weiter, eine lesbare PDF je Woche, chronologisch sortierbar benannt

Alles landet in einem Timestamp-Unterordner wie `Berichtsheft_Export/Berichtsheft_2026-07-03_14-22-05/`.

## Setup

Einmalig, Python 3 vorausgesetzt.

```
pip install playwright
playwright install chromium
```

Auf Linux zusätzlich die Systembibliotheken und Schriften, sonst rendert Chromium leere PDFs.

```
python -m playwright install --with-deps chromium
```

## Nutzung

```
python src/berichtsheft_download.py                      # kompletter Ausbildungszeitraum
python src/berichtsheft_download.py --ab 2024-08-01       # erst ab diesem Montag
python src/berichtsheft_download.py --out D:\Export        # anderer Ausgabeordner
```

Nach dem Start drei Eingaben (E-Mail, Passwort mit Wiederholung, PLZ oder Ort deiner IHK), den Rest macht das Skript. Das Passwort steht nur im Speicher, nichts wird auf Platte gesichert, jeder Lauf startet mit frischem Browser.

## Aus einem Word-Berichtsheft importieren

Wer das Heft in Word führt statt im IHK-Portal, startet das Menü und wählt den Punkt `word`.

```
python src/berichtsheft.py
```

Das Tool sucht die `.docx` selbst neben dem Programm, lässt bei mehreren Treffern per Nummer wählen und baut dieselbe `berichtsheft.json` wie der IHK-Download, ohne Login und ohne Browser. Danach übernimmt der Menüpunkt `upload` den Rest.

Erwartet wird je Woche ein Absatz in der Form `Zweite Ausbildungswoche (11.08.–17.08.2025)` und darunter je Tätigkeit ein eigener Absatz. Weil die docx keine Tage und keine Stunden kennt, verteilt der Import die Tätigkeiten einer Woche reihum auf Montag bis Freitag. Die Stunden füllt der Uploader auf, acht pro Tag. Den Ausbildungsort rät der Import aus dem Zeilenanfang, `Berufsschule` oder `Lernfeld` wird Schule, alles andere Betrieb.

Es entstehen keine PDFs, nur die JSON. Der Import braucht `python-docx`, das der Downloader bei Bedarf selbst nachlädt.

## Wie es funktioniert

Das Berichtsheft ist eine Angular-SPA, die eine JSON-REST-API auf `bildung.service.ihk.de` anspricht. Das Skript scrapt nicht das DOM, es ruft dieselbe API direkt auf. Der Ablauf in vier Schritten.

### 1. Login über einen frischen Browser

`wait_for_login` lädt die Berichtsheft-URL, räumt die Portal-Dialoge ab und füllt das Keycloak-Formular. Der IHK-Login läuft in zwei Stufen. Seite eins nimmt nur die E-Mail und einen "Weiter"-Button, das Passwortfeld erscheint erst auf Seite zwei. `_fill_keycloak_page` behandelt beide Stufen einzeln und begrenzt die Versuche, damit ein Tippfehler nicht in eine Account-Sperre klickt.

### 2. Auth-Header abhören statt aus dem sessionStorage lesen

Das ist der Kern und die wichtigste Lektion. Die SPA schreibt `currentUser` und die gewählte Organisation nicht zuverlässig in den `sessionStorage`, auf einem frisch geladenen Tab ist der oft komplett leer. Verlass dich also nie darauf.

Stattdessen registriert `make_sniffer` einen Playwright-Request-Listener. Sobald die SPA einen echten API-Call an `bildung.service.ihk.de` mit `Authorization`-Header macht, fängt der Sniffer den Bearer-Token und die Org-Header (`x-organisation-nummer-lang`, `x-ihk-nummer`, `x-ex-abb`, `x-bereich-intern-extern`) ab. Diese Header sind das einzige verlässliche Signal, dass die Session wirklich nutzbar ist. Erst wenn sie da sind, gilt der Login als fertig.

Eine Falle bei Playwrights Sync-API. Request-Events werden nur während eines Playwright-Aufrufs ausgeliefert. Ein blankes `time.sleep` lässt sie verhungern, der Sniffer bleibt blind. Deshalb wartet der Code über `_pump` (das ruft `wait_for_timeout` auf), niemals über `time.sleep`.

### 3. Wochen ziehen

`collect_weeks` läuft Montag für Montag durch den Zeitraum und ruft pro Woche `GET /berichtsheft/erstellen-api/v1/berichtswoche?datum=<Montag>` mit den abgehörten Headern auf. Der Fetch läuft im Seitenkontext (`page.evaluate`), so greifen Cookies und CORS automatisch. Bei einem 401 lädt `refresh_session` die Route neu, die SPA holt einen frischen Token und der Sniffer fängt ihn erneut. Leere Wochen liefern einen leeren Body und fallen raus.

Den Ausbildungszeitraum liefert `get_meta` aus den Stammdaten, ersatzweise aus dem Anwender-Endpoint. Das IHK-Backend wirft direkt nach dem Login gern einen 500er, darum probiert `get_meta` bis zu sechs Mal mit Pause.

### 4. PDF rendern

Aus jeder Woche baut `week_document` ein HTML-Fragment, das eine separate headless-Chromium-Instanz über `page.pdf()` zu PDF druckt. Die zweite Instanz ist nötig, weil `page.pdf()` nur im headless-Modus läuft, der Login-Browser aber sichtbar ist.

## Datenmodell, die Eigenheiten die dich beißen werden

Die berichtswoche-API liefert je Woche `tagesBerichte` (7 Tage) und optional `wochenEintrag`. Ein einzelner Eintrag kann zwei völlig verschiedene Formen haben, und beide kommen in echten Konten vor.

**Stichpunkt-Eintrag.** `typus == "StichpunktEintragDto"`, das Feld `text` ist Klartext. Kann harmlose spitze Klammern enthalten wie `Meeting Louis <> Hanna`, deshalb wird solcher Text HTML-escaped, nicht als Markup interpretiert.

**Freitext-Eintrag.** `typus == "FreitextEintragDto"`, das Feld `text` ist HTML (`<div><ul><li>...`). Manche Azubis führen ihr Heft komplett so, dann steckt der Text zusätzlich verschachtelt unter einem Wrapper. Der `wochenEintrag` ist dann kein flacher Eintrag, sondern ein Objekt mit `betrieb` und `schule`, die jeweils den echten Eintrag halten.

`flatten_entries` macht beide Formen flach. Hat ein Objekt `betrieb` oder `schule`, gibt es die Untereinträge zurück, sonst das Objekt selbst. `is_html_entry` entscheidet über `typus`, mit einer Tag-Regex als Fallback, damit ein `<>` im Klartext nicht als HTML zerbricht. HTML wird als echtes Layout gerendert, aktive Inhalte (`<script>`, `<style>`) entfernt `clean_html` vorher.

Wenn also PDFs leer aussehen, obwohl die JSON gefüllt ist, liegt der Text fast sicher in einer Struktur, die `flatten_entries` noch nicht kennt. Dann brauchst du einen echten Beispiel-Eintrag aus der JSON, nicht Raten.

## Fehlersuche

**PDFs sind winzig oder weiß, Kopf rendert aber.** Fehlende Systemschriften unter Linux. Das Skript warnt selbst und nennt den Fix (`playwright install --with-deps chromium` oder `apt install fonts-liberation fontconfig`).

**PDFs zeigen nur Datum und Dauer, kein Text.** Eintragsstruktur, die `flatten_entries` nicht abdeckt. Struktur prüfen mit

```
python -c "import json,glob,os; f=sorted(glob.glob('Berichtsheft_Export/*/berichtsheft.json'),key=os.path.getmtime)[-1]; d=json.load(open(f,encoding='utf-8')); w=[x for x in d['wochen'] if x.get('tagesBerichte')][0]; print(json.dumps(w['tagesBerichte'][0], ensure_ascii=False)[:1500])"
```

**Login hängt oder loggt sich aus.** Fast immer Timing. Prüf, ob irgendein neuer Wartepunkt `time.sleep` statt `_pump` nutzt, das killt den Sniffer. Die `[debug]`-Zeilen in `_fill_keycloak_page` zeigen, welche Felder das Skript auf der SSO-Seite sieht.

**`KeyError: 'ausbildungsverhaeltnis'` oder Zeitraum fehlt.** Der Stammdaten-Call kam mit 500 zurück. `get_meta` wiederholt das schon, bei dauerhaftem Fehler ist das IHK-Backend gerade kaputt, später neu starten.

## Weiterentwickeln

- **Neue Eintragsform.** Nur `flatten_entries` und `is_html_entry` anfassen, der Rest ist datengetrieben.
- **PDF-Layout.** Steckt komplett in der `CSS`-Konstante und `week_document` / `entry_li`. HTML-Fragment, kein externes Templating.
- **Andere Felder mitnehmen.** Die volle API-Antwort liegt roh in `berichtsheft.json`, dort kannst du sehen was noch da ist, ohne die API neu abzufragen.
- **Verifikation.** Die reine Render- und Parse-Logik (`fmt_duration`, `week_document`, `flatten_entries`, `entry_li`) ist ohne Browser testbar, weil der Playwright-Import erst in `main` passiert. Fixtures und Asserts gegen echte Wochen-JSON, nicht gegen erfundene Struktur.

## Grenzen

Der PLZ-Match wählt den ersten Autocomplete-Treffer. Bei mehrdeutigen Orten kann das die falsche IHK treffen. Fürs Ergebnis egal, weil die API-Header am Account hängen, nicht am IHK-Kontext, aber sauberer ist die genaue Stadt der eigenen IHK. Das Skript deckt nur die Auszubildenden-Rolle ab (`rolle=AUSZUBILDENDER`).
