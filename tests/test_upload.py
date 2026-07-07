"""Tests für die browserfreie Kernlogik von berichtsheft_upload.

Getestet wird alles, was ohne Playwright läuft. Der Playwright-Import steckt in
main(), deshalb ist das Modul ohne Browser importierbar. Läuft mit pytest oder
direkt: python tests/test_upload.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import berichtsheft_upload as U


def test_minutes():
    assert U.minutes("PT3H30M") == 210
    assert U.minutes("PT8H") == 480
    assert U.minutes("PT45M") == 45
    assert U.minutes("PT1H2M3S") == 62      # Sekunden zählen nicht
    assert U.minutes("PT0S") == 0
    assert U.minutes("") == 0
    assert U.minutes(None) == 0
    assert U.minutes("kaputt") == 0


def test_norm():
    assert U.norm("  Hallo   Welt  ") == "hallo welt"
    assert U.norm(None) == ""


def test_normalize_tenant():
    assert U.normalize_tenant("xsyntachs") == "https://xsyntachs.apprentio.de"
    assert U.normalize_tenant("  xsyntachs/ ") == "https://xsyntachs.apprentio.de"
    assert U.normalize_tenant("firma.de") == "https://firma.de"
    assert U.normalize_tenant("https://x.apprentio.de") == "https://x.apprentio.de"
    assert U.normalize_tenant("") == ""


def test_dedup_key_html_gegen_klartext():
    # apprentio escapt beim Speichern, Rohtext und gespeicherte Fassung müssen
    # trotzdem auf denselben Schlüssel fallen.
    assert U.dedup_key("a -> b") == U.dedup_key("a -&gt; b")
    assert U.dedup_key("<code>x</code>") == U.dedup_key("x")
    assert U.dedup_key("<p>Hallo   Welt</p>") == "hallo welt"


def test_clean_description():
    assert U.clean_description('<img src="x.png">Text') == "Text"
    assert U.clean_description("<script>böse()</script>ok") == "ok"
    assert U.clean_description("davor data:image/png;base64,AAAA danach").strip() \
        == "davor  danach".strip()
    lang = "x" * 60_000
    gekuerzt = U.clean_description(lang)
    assert len(gekuerzt) < 60_000 and gekuerzt.endswith("[gekürzt]")


def test_flatten_entries():
    assert U.flatten_entries({"text": "x"}) == [{"text": "x"}]
    b, s = {"text": "b"}, {"text": "s"}
    assert U.flatten_entries({"betrieb": b, "schule": s}) == [b, s]
    assert U.flatten_entries({"betrieb": b, "schule": None}) == [b]
    assert U.flatten_entries("kein dict") == []
    assert U.flatten_entries({}) == [{}]


def test_apply_default_hours():
    jobs = [
        {"report_id": 1, "date": "2024-01-01", "minutes": 0},
        {"report_id": 1, "date": "2024-01-01", "minutes": 0},
        {"report_id": 1, "date": "2024-01-02", "minutes": 120},
    ]
    U.apply_default_hours(jobs, 480)
    assert jobs[0]["minutes"] == 240 and jobs[1]["minutes"] == 240   # Tag ohne Dauer aufgefüllt
    assert jobs[2]["minutes"] == 120                                 # Tag mit Dauer bleibt


def test_apply_default_hours_ungerade_summe_stimmt():
    jobs = [{"report_id": 1, "date": "2024-01-01", "minutes": 0} for _ in range(3)]
    U.apply_default_hours(jobs, 500)
    assert sum(j["minutes"] for j in jobs) == 500


def test_apply_default_hours_faithful_ist_noop():
    jobs = [{"report_id": 1, "date": "2024-01-01", "minutes": 0}]
    U.apply_default_hours(jobs, 0)
    assert jobs[0]["minutes"] == 0


def test_iter_entries_tageseintraege():
    week = {"tagesBerichte": [
        {"datum": "2024-01-01", "anwesenheit": "ANWESEND", "ort": "BETRIEB", "eintraege": [
            {"text": "Aufgabe A", "dauer": "PT4H", "ort": None,
             "qualifikationen": [{"berufsbildPositionId": 11}]},
            {"text": "   ", "dauer": "PT1H"},   # leer, fällt raus
        ]},
    ]}
    assert list(U.iter_entries(week)) == [
        ("2024-01-01", "ANWESEND", "BETRIEB", "Aufgabe A", "PT4H", [11]),
    ]


def test_iter_entries_wochenheft_auf_werktage():
    week = {
        "tagesBerichte": [
            {"datum": "2024-01-01", "anwesenheit": "ANWESEND"},   # Montag
            {"datum": "2024-01-02", "anwesenheit": "ANWESEND"},   # Dienstag
            {"datum": "2024-01-06", "anwesenheit": "ANWESEND"},   # Samstag, raus
        ],
        "wochenEintrag": {"text": "Woche X", "dauer": "PT0S", "ort": "BETRIEB"},
    }
    daten = [row[0] for row in U.iter_entries(week)]
    assert daten == ["2024-01-01", "2024-01-02"]


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
