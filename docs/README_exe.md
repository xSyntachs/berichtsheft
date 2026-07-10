# Berichtsheft-Suite als ausführbare Datei

Ein Programm für alles. Kein Python, keine Installation. Doppelklick genügt.

Es gibt je Plattform zwei Bauarten. Der Release ist der normale Auslieferungsstand mit Download und Upload. Der Demo hat zusätzlich den Reset, ein Testwerkzeug das alle Einträge löscht, und ist nur zum Ausprobieren gedacht.

- Windows Release `berichtsheft.exe`
- Windows Demo `berichtsheft-demo.exe`
- Linux Release `berichtsheft-linux`
- Linux Demo `berichtsheft-linux-demo`
- macOS Release `berichtsheft-macos`
- macOS Demo `berichtsheft-macos-demo`

## Benutzen

Doppelklick (oder Start im Terminal) öffnet ein Menü.

```
Was möchtest du tun?
  [1] download   IHK-Heft als PDFs und JSON herunterladen
  [2] upload     Export nach apprentio hochladen und einreichen
```

Der Demo-Build zeigt zusätzlich `[3] reset`.

Wer den Menüpunkt direkt starten will, ruft im Terminal auf. Download und Upload kennen keine Flags, alles Weitere fragt das Programm interaktiv ab.

```
berichtsheft.exe download
berichtsheft.exe upload
berichtsheft.exe reset --ja
```

Linux und macOS gleich, nur `./berichtsheft-linux` oder `./berichtsheft-macos` statt `berichtsheft.exe`. Vorher einmalig ausführbar machen.

```
chmod +x berichtsheft-linux
./berichtsheft-linux
```

Ein Binary läuft nur auf der Plattform, für die es gebaut wurde. Das Linux-Binary ist ELF und startet auf einem Mac mit `zsh: exec format error`. Auf dem Mac gehört `berichtsheft-macos`, gebaut mit `build.sh` auf einem Mac. Mehr dazu unter "Neu bauen".

## Erster Start

Beim ersten Lauf lädt das Programm den Chromium-Browser einmalig selbst nach (rund 150 MB, braucht Internet, dauert ein paar Minuten). Danach ist er im Benutzer-Cache und der Start geht sofort. Die Konfiguration und der Export-Ordner `Berichtsheft_Export` landen neben der ausführbaren Datei.

## Windows-Warnung "unbekannter Herausgeber"

Auf fremden Rechnern erscheint beim ersten Start oft ein blauer Kasten, "Der Computer wurde durch Windows geschützt". Das ist Windows SmartScreen, nicht der Virenscanner. Es ist kein Virusfund, sondern nur ein Reputationshinweis, weil die Datei unsigniert und dem System unbekannt ist. Jede unsignierte EXE bekommt das, egal wie sauber sie ist.

Sofort ausführen, ein Klick. Im blauen Kasten auf "Weitere Informationen" klicken, dann erscheint der Knopf "Trotzdem ausführen". Danach merkt sich Windows die Datei und fragt nicht wieder.

Falls zusätzlich der Virenscanner meckert (seltener), Rechtsklick auf die EXE, Eigenschaften, unten "Zulassen" anhaken, oder die Datei im Defender als Ausnahme eintragen.

Ganz ohne Warnung, also ohne den blauen Kasten überhaupt, geht es nur mit einer Code-Signatur. Die EXE wird dabei mit einem Zertifikat der Firma signiert, dann vertraut SmartScreen ihr. Communardo hat so ein Zertifikat vermutlich schon. Ist eine `.pfx`-Datei plus Passwort vorhanden, signiert man in einem Schritt.

```
signtool sign /f firma.pfx /p PASSWORT /tr http://timestamp.sectigo.com /td sha256 /fd sha256 dist\berichtsheft.exe
```

Mit einem EV-Zertifikat (Hardware-Token) verschwindet der Hinweis sofort, mit einem normalen OV-Zertifikat baut sich das Vertrauen über die ersten Downloads auf. Für ein rein internes Werkzeug ist der einfachste Weg, die IT trägt die EXE oder das Firmenzertifikat einmalig als Ausnahme ein. Linux kennt das Problem nicht, dort läuft das Binary ohne Warnung. macOS hat eine eigene Sperre, dazu der nächste Abschnitt.

## macOS-Sperre "kann nicht geöffnet werden"

macOS blockiert unsignierte Programme aus dem Internet mit Gatekeeper, vergleichbar zu SmartScreen. Beim ersten Start kommt "berichtsheft-macos kann nicht geöffnet werden, da der Entwickler nicht verifiziert werden kann". Kein Virusfund, nur die fehlende Signatur.

Einmalig freigeben, dann startet es normal. Im Finder Rechtsklick (oder Ctrl-Klick) auf die Datei, "Öffnen", im Dialog nochmal "Öffnen". Oder im Terminal das Quarantäne-Attribut entfernen.

```
xattr -d com.apple.quarantine berichtsheft-macos
chmod +x berichtsheft-macos
./berichtsheft-macos
```

Ganz ohne Sperre geht es nur mit einer Apple-Entwickler-Signatur plus Notarisierung. Für ein internes Werkzeug reicht die einmalige Freigabe.

## Neu bauen

Voraussetzung Python 3 auf Windows, für das Linux-Binary zusätzlich ein laufendes Docker Desktop.

```
pwsh -File packaging/build.ps1
```

Das Skript baut alle vier Dateien nach `dist\`, Release und Demo je für Windows und, falls Docker läuft, für Linux. Ob Reset im Menü auftaucht, steuert die Datei `src/_buildcfg.py`, die der Build je Variante auf `DEMO = False` oder `True` setzt und danach wieder entfernt. Aus dem Quellcode gestartet gilt Entwicklung, dort ist der Reset sichtbar. Der Chromium-Browser wird bewusst nicht mit eingebacken, sonst wäre die Datei zehnmal so groß und an eine Browser-Version gebunden. Stattdessen lädt das Programm ihn beim ersten Start passend nach.

Auf Linux oder macOS baut `build.sh` die nativen Binaries, Release und Demo, für genau die Plattform auf der es läuft.

```
bash packaging/build.sh
```

PyInstaller kann nicht für eine fremde Plattform bauen, ein Mac-Binary muss also auf einem Mac entstehen und ein Linux-Binary auf Linux. Auf dem Mac heißt das Ergebnis `berichtsheft-macos`, auf Linux `berichtsheft-linux`. Voraussetzung ist Python 3, auf Linux zusätzlich `binutils`.
