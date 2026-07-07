"""Tests für die Job-Bau-Logik des Ausbilderwerkzeugs.

build_jobs ist ohne Browser testbar, der Playwright-Import liegt in main. Lauf:
python tests/test_review.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import berichtsheft_review as R


def _rep(state, i):
    return {"id": i, "from": "2025-08-11", "to": "2025-08-17", "type": "WEEKLY",
            "state": state, "reviewer_id": None}


def test_einzelner_quellzustand():
    reports = [_rep("SUBMITTED", 1), _rep("ACCEPTED", 2), _rep("CREATING", 3)]
    jobs = R.build_jobs(reports, ("SUBMITTED",), "ACCEPTED", 99)
    assert [j["id"] for j in jobs] == [1]
    assert jobs[0]["body"]["state"] == "ACCEPTED"
    assert jobs[0]["body"]["reviewer_id"] == 99   # None am Report -> Fallback auf Prüfer


def test_leeren_sammelt_offen_und_angenommen():
    reports = [_rep("SUBMITTED", 1), _rep("ACCEPTED", 2), _rep("DECLINED", 3), _rep("CREATING", 4)]
    jobs = R.build_jobs(reports, ("SUBMITTED", "ACCEPTED"), "DECLINED", 5)
    assert sorted(j["id"] for j in jobs) == [1, 2]
    assert all(j["body"]["state"] == "DECLINED" for j in jobs)


def test_vorhandener_pruefer_bleibt():
    r = _rep("ACCEPTED", 7)
    r["reviewer_id"] = 42
    jobs = R.build_jobs([r], ("ACCEPTED",), "DECLINED", 5)
    assert jobs[0]["body"]["reviewer_id"] == 42   # am Report gesetzter Prüfer schlägt Fallback


def test_leeren_ist_in_actions():
    srcs, dst, _ = R.ACTIONS["leeren"]
    assert set(srcs) == {"SUBMITTED", "ACCEPTED"} and dst == "DECLINED"


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
