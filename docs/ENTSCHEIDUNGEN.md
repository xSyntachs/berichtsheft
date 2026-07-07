# Architekturentscheidungen

Dieses Dokument hält die tragenden Technikentscheidungen der Berichtsheft-Suite fest, jede mit Kontext, verworfenen Alternativen und Begründung. Das Format lehnt sich an Architecture Decision Records an. Für die zentrale Entscheidung, die Interaktion mit der IHK, steht am Ende eine gewichtete Nutzwertanalyse, die die Wahl nachvollziehbar macht.

Alle Entscheidungen sind akzeptiert und im Code umgesetzt, Stand 2026-07-07.

## Übersicht

| Nr | Entscheidung | Gewählt |
|---|---|---|
| 1 | Interaktion mit der IHK-SPA | Playwright (Browser-Automatisierung) |
| 2 | Erkennung der gültigen Session | Auth-Header aus dem Netzwerkverkehr abhören |
| 3 | Datenübertragung | REST-API direkt aufrufen statt DOM scrapen |
| 4 | Kopplung der beiden Werkzeuge | getrennte Skripte, nur über Dateien verbunden |
| 5 | Auslieferung | PyInstaller Onefile, Chromium nachladen statt bündeln |
| 6 | Upload-Durchsatz | Batch aus parallelen POSTs im Seitenkontext |
| 7 | Wiederholbarkeit | Dedup über normalisierten Klartext-Schlüssel |

## 1. Interaktion mit der IHK erfolgt über Playwright

**Kontext.** Das IHK-Berichtsheft ist eine Angular-SPA hinter Keycloak-SSO. Der Login läuft zweistufig, die eigentlichen Daten kommen aus einer JSON-REST-API, die nur mit einem Bearer-Token und vier Organisations-Headern antwortet. Diese Header entstehen erst im laufenden Browser-Kontext.

**Optionen.** Ein reiner HTTP-Client (`requests`) hätte den kompletten Keycloak-Flow samt Token-Refresh selbst nachbauen müssen. Selenium und Playwright automatisieren einen echten Browser, lösen den SSO-Flow also mit. Puppeteer kann das auch, setzt aber einen Node-Stack neben Python voraus.

**Entscheidung.** Playwright.

**Begründung.** Playwright fährt den echten Browser, damit läuft der Keycloak-Flow ohne Nachbau. Entscheidend ist die native Request-Interception, über die sich der Auth-Token direkt aus dem Verkehr abhören lässt (siehe Entscheidung 2). Selenium bietet das nur über Umwege wie selenium-wire, ein reiner HTTP-Client müsste den fragilen SSO-Nachbau tragen, und Puppeteer würde einen zweiten Techstack in ein Python-Projekt zwingen. Die gewichtete Nutzwertanalyse unten stützt die Wahl mit 4,70 von 5 Punkten vor Puppeteer (4,10).

**Konsequenzen.** Das Werkzeug braucht einen Chromium-Browser (siehe Entscheidung 5). Playwrights synchrone API liefert Request-Events nur während eines Playwright-Aufrufs aus, deshalb wartet der Code nie über `time.sleep`, sondern über `_pump`.

## 2. Die gültige Session wird über abgehörte Header erkannt

**Kontext.** Ein Skript braucht ein verlässliches Signal, dass die Anmeldung durch ist und die API nutzbar. Der naheliegende Ort wäre der `sessionStorage`.

**Optionen.** Aus dem `sessionStorage` lesen, nach fester Zeit einfach weitermachen, oder den Netzwerkverkehr beobachten.

**Entscheidung.** Einen Request-Listener registrieren und auf den ersten API-Call mit `Authorization`-Header warten.

**Begründung.** Die SPA befüllt den `sessionStorage` nicht zuverlässig, auf einem frisch geladenen Tab ist er oft leer. Ein festes Warten ist entweder zu kurz und schlägt fehl oder zu lang und bremst. Der erste echte API-Call dagegen beweist, dass Token und Organisations-Header existieren, und liefert sie gleich mit.

**Konsequenzen.** Der Sniffer ist blind, solange kein Playwright-Aufruf läuft. Das erzwingt die `_pump`-Warterei aus Entscheidung 1. Bei einem 401 lädt `refresh_session` die Route neu, die SPA holt einen frischen Token und der Sniffer fängt ihn erneut.

## 3. Daten kommen aus der REST-API, nicht aus dem DOM

**Kontext.** Sobald der Browser angemeldet ist, gibt es zwei Wege an die Wochendaten. Die gerenderte Oberfläche auslesen oder dieselbe API aufrufen, die auch die SPA nutzt.

**Entscheidung.** Die REST-API direkt aufrufen, im Seitenkontext über `page.evaluate`.

**Begründung.** DOM-Scraping bricht bei jeder Layout-Änderung und liefert nur, was gerade sichtbar gerendert ist. Der direkte API-Aufruf liefert die vollständige, strukturierte Antwort und ist gegen Oberflächenänderungen unempfindlich. Der Aufruf läuft im Seitenkontext, damit greifen Cookies und CORS automatisch. Die volle Rohantwort landet in `berichtsheft.json`, damit spätere Felder ohne erneute Abfrage erschließbar sind.

**Konsequenzen.** Das Werkzeug hängt am Format der IHK-API. Ändert die IHK ihr Datenmodell, muss die Parse-Logik nach, betroffen wären vor allem `flatten_entries` und `is_html_entry`.

## 4. Downloader und Uploader bleiben getrennt

**Kontext.** Beide Skripte teilen Logik, etwa das Auflösen der zwei Eintragsformen.

**Entscheidung.** Zwei eigenständige Skripte ohne gemeinsamen Import, verbunden nur über den Export-Ordner.

**Begründung.** Ein früherer geteilter Import ist auf einer fremden Maschine gebrochen, weil das importierte Modul dort nicht auflösbar war. Die Kosten der Trennung sind gering, `flatten_entries` existiert doppelt und ist wenige Zeilen lang. Der Gewinn ist, dass jedes Werkzeug für sich lauffähig und auslieferbar bleibt.

**Konsequenzen.** Geteilte Logik muss an zwei Stellen gepflegt werden. Die Tests decken die Uploader-Fassung ab.

## 5. Auslieferung als Onefile, Chromium wird nachgeladen

**Kontext.** Nachwuchskräfte und Ausbilder haben nicht zwingend Python. Das Werkzeug soll per Doppelklick laufen.

**Optionen.** Als Python-Skript ausliefern (setzt Python voraus), PyInstaller Onefile, PyInstaller Onedir, oder Nuitka. Quer dazu die Frage, ob Chromium mit ins Paket wandert oder beim ersten Start nachgeladen wird.

**Entscheidung.** PyInstaller im Onefile-Modus, Chromium wird beim ersten Start nachgeladen.

**Begründung.** Onefile gibt eine einzige Datei zum Weitergeben, das ist die einfachste Auslieferung. Nuitka baut zwar schnelleren Code, der Startvorteil ist hier belanglos und die Toolchain aufwendiger. Chromium einzubacken würde die Datei rund verzehnfachen und an eine feste Browser-Version binden, deshalb lädt `ensure_chromium` den Browser beim ersten Start in den Benutzer-Cache nach.

**Konsequenzen.** Der erste Start braucht Internet und ein paar Minuten für den rund 150 MB großen Download. Eine unsignierte Onefile-EXE löst unter Windows SmartScreen aus, ein Fehlalarm ohne Virusfund. Dauerhaft sauber ist nur eine Code-Signatur, siehe [README_exe.md](README_exe.md). Linux flaggt nicht. Im Onefile-Modus zeigt `sys.executable` auf die EXE, deshalb fährt `ensure_chromium` den Playwright-Driver direkt und pinnt den Browser-Cache auf einen festen Pfad.

## 6. Upload läuft als Batch paralleler POSTs

**Kontext.** Ein Ausbildungsjahr hat viele Einträge. Jeder einzeln über einen Python-Browser-Roundtrip wäre langsam.

**Entscheidung.** Bis zu acht POSTs werden in einem `page.evaluate` gebündelt und per `Promise.all` parallel abgefeuert.

**Begründung.** Der teure Teil ist der Roundtrip zwischen Python und Browser, nicht der HTTP-Call selbst. Das Bündeln spart diesen Roundtrip pro Eintrag und ist grob achtmal schneller. Ein Rate-Limit war im Test nicht zu beobachten.

**Konsequenzen.** Unter Parallellast kann apprentio einen transienten HTTP 500 werfen. Fehlgeschlagene Einträge wiederholt der Uploader danach einzeln.

## 7. Wiederholbarkeit über einen normalisierten Dedup-Schlüssel

**Kontext.** Der Upload soll beliebig oft laufen dürfen, ohne Duplikate anzulegen. Ein naiver Textvergleich scheitert, weil apprentio die Beschreibung beim Speichern verändert.

**Entscheidung.** Beide Seiten werden über `dedup_key` verglichen, der Tags streift, HTML-Entities auflöst und Whitespace normalisiert.

**Begründung.** apprentio escapt beim Speichern `<`, `>` und `&` und schließt offene Tags. Aus `a -> b` wird `a -&gt; b`, aus `<code>` wird `<code></code>`. Gesendeter Rohtext und gespeicherte Fassung sind also nie zeichengleich. Erst die Normalisierung auf beiden Seiten bringt sie auf denselben Kern, sonst legte jeder Wiederholungslauf jeden Eintrag mit Sonderzeichen erneut an.

**Konsequenzen.** Der Dedup schützt vor Doppelanlage, nicht vor falsch gemappten Wochen. Der Schlüssel ist über einen Test gegen die HTML-Escaping-Falle abgesichert.

## Nutzwertanalyse zu Entscheidung 1

Die Kriterien und Gewichte spiegeln die tatsächlichen Anforderungen des Projekts. Bewertet ist von 1 (schlecht) bis 5 (ideal). Der Nutzwert je Option ist die Summe aus Bewertung mal Gewicht.

| Kriterium | Gewicht | Playwright | Selenium | HTTP-Client | Puppeteer |
|---|---|---|---|---|---|
| SSO- und JS-Fähigkeit (Keycloak plus Angular) | 0,30 | 5 | 5 | 1 | 5 |
| Zugriff auf den Auth-Token (Request-Interception) | 0,25 | 5 | 2 | 3 | 5 |
| Wartbarkeit und API-Ergonomie | 0,15 | 5 | 3 | 2 | 4 |
| Setup-Aufwand für den Endnutzer | 0,15 | 4 | 3 | 5 | 3 |
| Bündelbarkeit mit PyInstaller (Python-Stack) | 0,15 | 4 | 3 | 5 | 2 |
| **Nutzwert** | **1,00** | **4,70** | **3,35** | **2,85** | **4,10** |

Playwright führt deutlich. Der reine HTTP-Client fällt an der SSO-Fähigkeit durch, den Keycloak-Flow samt Token-Refresh selbst zu tragen wäre der fragilste Teil des ganzen Werkzeugs. Puppeteer landet auf Platz zwei, scheitert praktisch aber daran, dass es einen Node-Stack in ein Python-Projekt zöge und die Bündelung mit PyInstaller unterläuft. Selenium kann alles, verliert aber an der umständlichen Request-Interception, die für Entscheidung 2 tragend ist.
