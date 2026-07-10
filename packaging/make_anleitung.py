"""Erzeugt die Endnutzer-Anleitung setup/Anleitung.pdf (reportlab).
Nach Textänderungen einfach neu laufen lassen: python packaging/make_anleitung.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (ListFlowable, Paragraph, Preformatted,
                                SimpleDocTemplate)

OUT = str(Path(__file__).resolve().parent.parent / "setup" / "Anleitung.pdf")

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, spaceAfter=2)
sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10.5,
                     textColor=colors.HexColor("#555555"), spaceAfter=10)
h2 = ParagraphStyle("h2", parent=styles["Heading1"], fontSize=13.5,
                    spaceBefore=14, spaceAfter=4)
body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10.5,
                      leading=15, spaceAfter=6)
item = ParagraphStyle("item", parent=body, spaceAfter=3)
code = ParagraphStyle("code", parent=styles["Code"], fontSize=9.5, leading=13,
                      backColor=colors.HexColor("#f2f2f2"), borderPadding=6,
                      leftIndent=6, spaceBefore=2, spaceAfter=8)

def P(text, style=body):
    return Paragraph(text, style)

def UL(*items):
    return ListFlowable([P(i, item) for i in items], bulletType="bullet",
                        start="•", leftIndent=14, bulletFontSize=10,
                        spaceAfter=6)

story = [
    P("Berichtsheft-Suite", h1),
    P("Dein IHK-Berichtsheft automatisch nach apprentio bringen", sub),

    P("1. Programm installieren", h2),
    UL("Lade <b>download.bat</b> und <b>download.sh</b> herunter.",
       "<b>Windows.</b> Doppelklicke <b>download.bat</b>. Wenn Windows "
       "nachfragt, bestätige mit Ausführen.",
       "<b>Mac und Linux.</b> Öffne ein Terminal und führe diese drei Befehle "
       "aus."),
    Preformatted("cd Downloads\nchmod +x download.sh\n./download.sh", code),
    UL("Wähle die Version Normal, dafür einfach Enter drücken (die Demo ist "
       "nur zum Testen).",
       "Das Programm installiert sich in den Ordner <b>Berichtsheft-Suite</b> "
       "in deinem Benutzerordner und öffnet sich danach von selbst.",
       "Beim ersten Start lädt es einmalig einen Browser nach, das dauert ein "
       "paar Minuten."),

    P("2. Berichtsheft holen", h2),
    P("<b>Weg A, von der IHK-Seite.</b> Wenn du dein Heft online bei der IHK "
      "führst."),
    UL("Im Programm den Punkt <b>download</b> wählen.",
       "IHK-E-Mail, IHK-Passwort (die Eingabe bleibt unsichtbar) und die "
       "Stadt deiner IHK eingeben.",
       "Es öffnet sich ein Browser, der alles von allein einsammelt. Nur "
       "warten, nichts anklicken.",
       "Dein Passwort wird nirgends gespeichert."),
    P("<b>Weg B, aus einer Word-Datei.</b> Wenn du dein Heft in Word führst."),
    UL("Die Word-Datei in den Ordner Berichtsheft-Suite legen (den hat "
       "Schritt 1 angelegt).",
       "Im Programm den Punkt <b>word</b> wählen.",
       "Die Datei muss so aussehen. Jede Woche beginnt mit einer Zeile, in "
       "der das Wort Ausbildungswoche und der Zeitraum stehen, darunter kommt "
       "jede Tätigkeit in eine eigene Zeile."),
    Preformatted("Erste Ausbildungswoche (04.08.–10.08.2025)\n"
                 "Arbeitsplatz eingerichtet und Team kennengelernt\n"
                 "Grundlagen der Firmenprodukte gelernt\n"
                 "Berufsschule Lernfeld 1, Netzwerke und Hardware\n"
                 "\n"
                 "Zweite Ausbildungswoche (11.08.–17.08.2025)\n"
                 "Erste kleine Aufgaben im Kundenprojekt\n"
                 "Berufsschule Lernfeld 2, Programmierung", code),
    UL("Zeilen, die mit Berufsschule oder Lernfeld beginnen, landen "
       "automatisch bei der Schule, alle anderen beim Betrieb.",
       "Stunden musst du nicht angeben, es werden 8 pro Tag eingetragen."),

    P("3. In apprentio eintragen", h2),
    UL("Im Programm den Punkt <b>upload</b> wählen.",
       "Beim ersten Mal fragt es nach der apprentio-Adresse. Gib "
       "<b>communardo</b> ein (für communardo.apprentio.de), das merkt sich "
       "das Programm.",
       "Mit E-Mail und Passwort deines eigenen apprentio-Zugangs anmelden.",
       "Das Programm trägt alle Tätigkeiten in den richtigen Wochen ein und "
       "fragt am Ende, ob es die Wochen beim Prüfer einreichen soll."),
    P("<b>Wichtig, bevor du mit ja antwortest.</b> Einreichen ist endgültig, "
      "eine eingereichte Woche kann nur dein Prüfer wieder öffnen. Willst du "
      "erst in apprentio nachsehen, antworte mit nein und lass das Programm "
      "später einfach nochmal laufen. Wiederholen ist immer sicher, was schon "
      "eingetragen ist, wird übersprungen."),

    P("4. Wenn etwas nicht klappt", h2),
    P("<b>Die IHK-Anmeldung hängt.</b> Programm schließen, neu öffnen, E-Mail "
      "und Passwort prüfen."),
    P("<b>Am Ende steht „X Wochen ohne apprentio-Report“.</b> Dein "
      "Ausbildungsbeginn ist in apprentio später eingetragen als bei der IHK. "
      "Sag deinem Ausbilder Bescheid, er kann den Zeitraum anpassen."),
    P("<b>Dein Ausbilder sieht die Einträge nicht.</b> Solange du nicht "
      "eingereicht hast, sind die Wochen Entwürfe. Sichtbar werden sie für ihn "
      "erst nach dem Einreichen."),
]

SimpleDocTemplate(OUT, pagesize=A4, leftMargin=22*mm, rightMargin=22*mm,
                  topMargin=18*mm, bottomMargin=18*mm,
                  title="Berichtsheft-Suite Anleitung").build(story)
print("geschrieben:", OUT)
