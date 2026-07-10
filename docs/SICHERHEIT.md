# Sicherheit und Datenschutz

Das Werkzeug verarbeitet echte Zugangsdaten, holt personenbezogene Daten aus einem Portal und schreibt in ein Produktivsystem. Dieses Dokument benennt, welche Daten das sind, wo sie liegen, welche Risiken bestehen und wie das Werkzeug damit umgeht.

## Welche Daten das Werkzeug anfasst

| Daten | Herkunft | Sensibilität |
|---|---|---|
| IHK-Zugangsdaten (E-Mail, Passwort) | Eingabe beim Start | hoch, Anmeldedaten |
| apprentio-Zugangsdaten (E-Mail, Passwort) | Eingabe beim Start | hoch, Anmeldedaten |
| Berichtsheft-Inhalte (Tätigkeiten, Daten, Qualifikationen) | IHK-Portal | personenbezogen |
| Bearer-Token und Session-Cookies | im laufenden Browser | hoch, aber flüchtig |
| Tenant und E-Mail | `berichtsheft_*.config.json` | niedrig bis mittel |

## Wo die Daten liegen

Das **Passwort** wird beim Start abgefragt und bleibt im Arbeitsspeicher des Prozesses. Es wird standardmäßig nicht auf die Platte geschrieben. `ask_credentials` speichert nur die E-Mail in der Config und weist im Klartext darauf hin, dass das Passwort bewusst außen vor bleibt.

Wer den Komfort will, kann ein Passwort manuell als Feld `password` in die `berichtsheft_*.config.json` eintragen. Dann steht es dort im Klartext. Das ist ein bewusster Kompromiss zugunsten der Bedienbarkeit und die einzige Stelle, an der ein Passwort persistent wird.

Die **Berichtsheft-Inhalte** landen als PDF und JSON in einem Export-Ordner neben dem Programm. Diese Daten sind personenbezogen, sie beschreiben die Ausbildung einer konkreten Person über Jahre.

**Token und Cookies** existieren nur im Browser-Kontext des laufenden Prozesses. Jeder Lauf startet mit einem frischen Browser, es wird keine Browser-Session auf Platte gehalten.

## Risiken und wie sie behandelt werden

| Risiko | Behandlung im Werkzeug | Was der Nutzer zusätzlich tun muss |
|---|---|---|
| Klartext-Passwort in der Config | Passwort wird standardmäßig nicht gespeichert, nur E-Mail. `.gitignore` schließt alle `*.config.json` aus | Feld `password` nur setzen, wenn der Rechner vertrauenswürdig ist, Datei niemals teilen |
| Personenbezogene Daten im Export | liegen ausschließlich lokal, `.gitignore` schließt `Berichtsheft_Export/` aus | Ordner nach Gebrauch löschen oder geschützt ablegen, nicht in ein Repository, nicht in eine Cloud ohne Not |
| Endgültiges Einreichen im Produktivsystem | Sicherheitsabfrage vor dem Einreichen, nein lässt die Wochen als Entwurf stehen | vor dem ersten echten Lauf mit einem Testkonto oder wenigen Wochen prüfen |
| Doppelte oder falsch gemappte Einträge | Dedup über normalisierten Schlüssel verhindert Doppelanlage | falsche Wochenzuordnung fängt der Dedup nicht ab, Ergebnis stichprobenartig prüfen |
| Account-Sperre durch Fehllogins | der IHK-Login begrenzt die Versuche, damit ein Tippfehler nicht in eine Sperre läuft | korrekte Zugangsdaten eingeben |

## Empfehlungen für die Weitergabe

Wer das Werkzeug oder das Projekt weitergibt, beachtet Folgendes.

Die Dateien `berichtsheft_*.config.json` und der Ordner `Berichtsheft_Export/` gehören nicht mit in die Weitergabe. Beide stehen im `.gitignore`, ein Repository nimmt sie also nicht auf. Bei einer manuellen Kopie muss man selbst darauf achten.

Auf einem gemeinsam genutzten Rechner sollte kein Passwort in der Config stehen. Der Standardweg über die versteckte Passworteingabe hält das Passwort nur im Speicher des Laufs.

Die unsignierte EXE löst unter Windows SmartScreen aus. Das ist ein Reputationshinweis, kein Virusfund. Dauerhaft verschwindet er nur mit einer Code-Signatur, der Weg dorthin steht in [README_exe.md](README_exe.md).

## Rechtlicher Rahmen

Das Werkzeug meldet sich regulär mit den Zugangsdaten des Nutzers an und ruft dieselbe REST-API auf, die auch die offizielle Oberfläche nutzt. Es umgeht keinen Zugriffsschutz und verschafft sich keine Rechte, die der angemeldete Account nicht ohnehin hat. Sinnvoll ist der Einsatz nur für das eigene Berichtsheft mit den eigenen Zugangsdaten.

Zwei Punkte bleiben in der Verantwortung des Nutzers. Automatisierter Zugriff kann den Nutzungsbedingungen von IHK-Portal oder apprentio widersprechen, das ist vor einem produktiven Einsatz zu prüfen. Und wer die Berichtsheft-Daten anderer Personen verarbeitet, etwa in der Ausbilderrolle, unterliegt den üblichen Pflichten zum Umgang mit personenbezogenen Daten.
