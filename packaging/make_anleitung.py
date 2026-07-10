"""Erzeugt die Endnutzer-Anleitungen setup/Anleitung.pdf (Azubi) und
setup/Anleitung-Ausbilder.pdf (Prüferseite), beide reportlab.
Layout nach Louis' Vorlage (Word-Optik): Serifenschrift, blaue Überschriften,
blaue Hinweis-Boxen, gelbe Achtung-Box, graue Code-Blöcke.
Nach Textänderungen neu laufen lassen: python packaging/make_anleitung.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (ListFlowable, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer)

SETUP = Path(__file__).resolve().parent.parent / "setup"

BLUE = colors.HexColor("#2E74B5")
NOTE_BG = colors.HexColor("#EAF3FB")
NOTE_BORDER = colors.HexColor("#9CC3E5")
WARN_BG = colors.HexColor("#FDF6E3")
WARN_BORDER = colors.HexColor("#E8A33D")
WARN_TEXT = colors.HexColor("#9C6500")
CODE_BG = colors.HexColor("#EFEFEF")

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Normal"], fontName="Times-Roman",
                    fontSize=24, leading=28, spaceAfter=2)
sub = ParagraphStyle("sub", parent=styles["Normal"], fontName="Times-Italic",
                     fontSize=10, textColor=colors.HexColor("#595959"),
                     spaceAfter=12)
h2 = ParagraphStyle("h2", parent=styles["Normal"], fontName="Times-Roman",
                    fontSize=15, leading=18, textColor=BLUE,
                    spaceBefore=14, spaceAfter=6)
body = ParagraphStyle("body", parent=styles["Normal"], fontName="Times-Roman",
                      fontSize=10.5, leading=14, spaceAfter=5)
lead = ParagraphStyle("lead", parent=body, fontName="Times-Bold", spaceBefore=6,
                      spaceAfter=3)
item = ParagraphStyle("item", parent=body, spaceAfter=2)
note = ParagraphStyle("note", parent=body, textColor=BLUE, backColor=NOTE_BG,
                      borderColor=NOTE_BORDER, borderWidth=0.8,
                      borderPadding=6, spaceBefore=6, spaceAfter=8)
warn = ParagraphStyle("warn", parent=body, textColor=WARN_TEXT,
                      backColor=WARN_BG, borderColor=WARN_BORDER,
                      borderWidth=1.2, borderPadding=7, leading=15,
                      spaceBefore=8, spaceAfter=8)
code = ParagraphStyle("code", parent=styles["Code"], fontSize=9.5, leading=13,
                      backColor=CODE_BG, borderPadding=6, leftIndent=0,
                      spaceBefore=4, spaceAfter=8)

def P(text, style=body):
    return Paragraph(text, style)

def UL(*items):
    return ListFlowable([P(i, item) for i in items], bulletType="bullet",
                        start="•", leftIndent=16, bulletFontSize=10,
                        spaceAfter=6)

azubi = [
    P("Berichtsheft-Suite", h1),
    P("Dein IHK-Berichtsheft automatisch nach apprentio bringen", sub),
    P("Die Berichtsheft-Suite liest dein Berichtsheft aus, entweder direkt "
      "von der IHK-Seite oder aus einer Word-Datei, und trägt die Einträge "
      "automatisch wochenweise in apprentio ein. Du sparst dir das manuelle "
      "Abtippen. Einreichen beim Prüfer bleibt ein bewusster, separater "
      "Schritt, den du selbst bestätigst."),

    P("1. Programm installieren", h2),
    P("Lade download.bat und download.sh herunter."),
    P("Windows", lead),
    UL("Doppelklicke download.bat.",
       "Wenn Windows nachfragt, bestätige mit Ausführen."),
    P("Mac und Linux", lead),
    P("Öffne ein Terminal und führe diese drei Befehle aus."),
    Preformatted("cd Downloads\nchmod +x download.sh\n./download.sh", code),
    P("Wähle die Version <b>Normal</b>, dafür einfach Enter drücken (die "
      "<i>Demo</i> ist nur zum Testen)."),
    P("Das Programm installiert sich in den Ordner Berichtsheft-Suite in "
      "deinem Benutzerordner und öffnet sich danach von selbst. Beim ersten "
      "Start lädt es einmalig einen Browser nach, das dauert ein paar "
      "Minuten."),

    P("2. Berichtsheft holen", h2),
    P("Weg A, von der IHK-Seite", lead),
    P("Führst du dein Heft online bei der IHK."),
    UL("Im Programm den Punkt <b>download</b> wählen.",
       "IHK-E-Mail eingeben.",
       "IHK-Passwort eingeben (die Eingabe bleibt unsichtbar).",
       "Stadt deiner IHK eingeben.",
       "Warten, bis sich der Browser öffnet und alles einsammelt, nichts "
       "anklicken."),
    P("Dein Passwort wird nirgends gespeichert.", note),
    P("Weg B, aus einer Word-Datei", lead),
    P("Führst du dein Heft in Word."),
    UL("Die Word-Datei in den Ordner Berichtsheft-Suite legen (den hat "
       "Schritt 1 angelegt).",
       "Im Programm den Punkt <b>word</b> wählen."),
    P("Die Datei muss so aufgebaut sein.", lead),
    UL("Jede Woche beginnt mit einer Zeile mit dem Wort Ausbildungswoche und "
       "dem Zeitraum.",
       "Darunter kommt jede Tätigkeit in eine eigene Zeile."),
    Preformatted("Erste Ausbildungswoche (04.08.-10.08.2025)\n"
                 "Arbeitsplatz eingerichtet und Team kennengelernt\n"
                 "Grundlagen der Firmenprodukte gelernt\n"
                 "Berufsschule Lernfeld 1, Netzwerke und Hardware\n"
                 "\n"
                 "Zweite Ausbildungswoche (11.08.-17.08.2025)\n"
                 "Erste kleine Aufgaben im Kundenprojekt\n"
                 "Berufsschule Lernfeld 2, Programmierung", code),
    P("Zeilen, die mit <i>Berufsschule</i> oder <i>Lernfeld</i> beginnen, "
      "landen automatisch bei der Schule, alle anderen beim Betrieb."),
    P("Stunden musst du nicht angeben, es werden pauschal 8 Stunden pro Tag "
      "eingetragen.", note),

    P("3. In apprentio eintragen", h2),
    UL("Im Programm den Punkt <b>upload</b> wählen.",
       "Beim ersten Mal <b>communardo</b> eingeben (für "
       "communardo.apprentio.de), das merkt sich das Programm.",
       "E-Mail und Passwort deines eigenen apprentio-Zugangs eingeben.",
       "Das Programm trägt alle Tätigkeiten in den richtigen Wochen ein und "
       "fragt am Ende, ob es die Wochen beim Prüfer einreichen soll."),
    P("<b>Achtung, Einreichen ist endgültig.</b><br/>"
      "Eine eingereichte Woche kann nur dein Prüfer wieder öffnen.<br/>"
      "Willst du erst in apprentio nachsehen, antworte mit nein und lass das "
      "Programm später einfach nochmal laufen.<br/>"
      "Wiederholen ist immer sicher, was schon eingetragen ist, wird "
      "übersprungen.", warn),

    P("4. Wenn etwas nicht klappt", h2),
    P("Die IHK-Anmeldung hängt.", lead),
    P("Programm schließen, neu öffnen, E-Mail und Passwort prüfen."),
    Spacer(1, 2),
    P("Am Ende steht „X Wochen ohne apprentio-Report“.", lead),
    P("Dein Ausbildungsbeginn ist in apprentio später eingetragen als bei der "
      "IHK. Sag deinem Ausbilder Bescheid, er kann den Zeitraum anpassen."),
    Spacer(1, 2),
    P("Dein Ausbilder sieht die Einträge nicht.", lead),
    P("Solange du nicht eingereicht hast, sind die Wochen Entwürfe. Sichtbar "
      "werden sie für ihn erst nach dem Einreichen."),
]

ausbilder = [
    P("Berichtsheft-Suite", h1),
    P("Was Ausbilder und Prüfer wissen müssen", sub),
    P("Die Azubis übertragen ihr IHK-Berichtsheft (oder ihr Word-Heft) mit "
      "der Berichtsheft-Suite automatisch nach apprentio und reichen die "
      "Wochen dort bei dir ein. Am Prüfen ändert sich nichts, du arbeitest "
      "ganz normal in apprentio. Diese Seite erklärt, was das Programm tut "
      "und was du einmalig kontrollieren solltest."),

    P("1. Was das Programm macht", h2),
    UL("Liest das Berichtsheft des Azubis aus, wahlweise vom IHK-Portal oder "
       "aus einer Word-Datei.",
       "Trägt jede Tätigkeit als Tätigkeitsnachweis in der passenden "
       "apprentio-Woche ein, mit Datum, Zeitaufwand, Anwesenheit und "
       "Ausbildungsort.",
       "Verknüpft Lernziele, wo die IHK-Qualifikation zum apprentio-Lehrplan "
       "passt, sonst steht der Qualifikationsname im Eintragstext.",
       "Fragt den Azubi am Ende, ob die Wochen bei dir als Prüfer "
       "eingereicht werden sollen. Einreichen passiert nie ungefragt.",
       "Schreibt nur in das Konto des angemeldeten Azubis und legt bei "
       "wiederholten Läufen nichts doppelt an."),
    P("Das Programm speichert keine Passwörter. Es meldet sich mit dem "
      "eigenen apprentio-Zugang des Azubis an.", note),

    P("2. Was du einmalig kontrollieren solltest", h2),
    UL("Der Ausbildungszeitraum in apprentio muss mit dem bei der IHK "
       "übereinstimmen. Beginnt er in apprentio später, fehlen dort die "
       "frühen Wochen und der Azubi sieht die Meldung „X Wochen ohne "
       "apprentio-Report“. Dann den Zeitraum anpassen und den Azubi das "
       "Programm erneut laufen lassen.",
       "Der Azubi braucht einen eigenen apprentio-Zugang, der das "
       "Berichtsheft sehen darf."),

    P("3. Prüfen und annehmen", h2),
    UL("Eingereichte Wochen erscheinen wie gewohnt in apprentio, du nimmst "
       "sie an oder lehnst sie ab.",
       "Solange der Azubi nicht eingereicht hat, siehst du nichts. Die "
       "Wochen sind bis dahin Entwürfe.",
       "Lehnst du eine Woche ab, kann der Azubi sie korrigieren. Beim "
       "nächsten Lauf reicht das Programm abgelehnte Wochen automatisch "
       "erneut ein."),
    P("<b>Achtung, Ablehnen ist der einzige Weg, eine eingereichte Woche "
      "wieder zu öffnen.</b><br/>"
      "Einreichen ist endgültig, weder der Azubi noch das Programm können "
      "eine eingereichte Woche zurückziehen.", warn),

    P("4. Gut zu wissen", h2),
    P("Stunden.", lead),
    P("Liefert das Quell-Heft keine echten Zeiten (typisch beim Word-Heft), "
      "trägt das Programm pauschal 8 Stunden pro Tag ein, verteilt auf die "
      "Einträge des Tages."),
    Spacer(1, 2),
    P("Texte.", lead),
    P("Die Einträge kommen unverändert aus dem IHK-Heft, inklusive Listen "
      "und Absätzen."),
    Spacer(1, 2),
    P("Wiederholte Läufe.", lead),
    P("Der Azubi kann das Programm beliebig oft laufen lassen. Vorhandene "
      "Einträge werden erkannt und übersprungen, es entstehen keine "
      "Duplikate."),
]

for fname, title, story in [
    ("Anleitung.pdf", "Berichtsheft-Suite Anleitung", azubi),
    ("Anleitung-Ausbilder.pdf", "Berichtsheft-Suite Anleitung für Ausbilder", ausbilder),
]:
    out = str(SETUP / fname)
    SimpleDocTemplate(out, pagesize=A4, leftMargin=22*mm, rightMargin=22*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title=title).build(story)
    print("geschrieben:", out)
