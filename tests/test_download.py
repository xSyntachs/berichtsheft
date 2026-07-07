"""Tests für den Word-Import des Downloaders.

Die Datums- und Verteillogik ist ohne Word-Datei und ohne Browser testbar,
python-docx und playwright werden erst zur Laufzeit lazy importiert. Lauf:
python tests/test_download.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import berichtsheft_download as D


def test_week_monday_montag_start():
    assert D.week_monday("zweite Ausbildungswoche (11.08.–17.08.2025)") == date(2025, 8, 11)


def test_week_monday_freitag_start_faellt_auf_montag():
    # 01.08.2025 ist ein Freitag, der Wochen-Montag ist der 28.07.2025
    assert D.week_monday("erste Ausbildungswoche (01.08.–08.08.2025)") == date(2025, 7, 28)


def test_week_monday_jahreswechsel():
    # Startjahr fehlt in der Klammer und liegt vor dem Endjahr
    assert D.week_monday("Zweiundzwanzigste Ausbildungswoche (29.12.2025–04.01.2026)") == date(2025, 12, 29)


def test_week_monday_kein_header():
    assert D.week_monday("29.09. - 05.10") is None
    assert D.week_monday("Meeting – Daily Collaboration Operations") is None


def test_docx_week_montag_zuerst_und_reihum():
    w = D._docx_week(date(2025, 8, 11), list("abcdef"))   # 6 Tätigkeiten auf 5 Tage
    tage = w["tagesBerichte"]
    assert tage[0]["datum"] == "2025-08-11"               # Montag steht vorn (Report-Zuordnung)
    assert len(tage) == 5
    assert len(tage[0]["eintraege"]) == 2                 # Rest landet beim Montag
    assert sum(len(t["eintraege"]) for t in tage) == 6


def test_docx_week_ort_nach_stichwort():
    w = D._docx_week(date(2025, 9, 29), ["Lernfeld 5: UML", "Meeting – Team"])
    orte = {e["ort"] for t in w["tagesBerichte"] for e in t["eintraege"]}
    assert orte == {"BERUFSSCHULE", "BETRIEB"}


def _run():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    fails = []
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            fails.append(name)
            print("FAIL", name, e)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} bestanden")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())
