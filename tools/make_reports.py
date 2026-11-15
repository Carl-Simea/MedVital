#!/usr/bin/env python3
"""Write the four sample pre-flight reports (reports/*.txt and *.pdf) from hub/settings.py CREW.

    python tools/make_reports.py        (PDF output needs `pip install reportlab`; .txt needs nothing)

The astronauts are fictional and every value is simulated. The .txt uses the labels the 3D body
dashboard's report reader understands (body-dashboard/public/intake.mjs), so uploading a report at
sign-up fills the form.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from medvital.hub.settings import CREW, REPORTS  # noqa: E402

SECTIONS = [
    ("Vital signs", [("Resting heart rate", "resting_hr", "bpm"), ("Blood pressure", "bp", "mmHg"),
                     ("SpO2", "spo2", "%"), ("Respiratory rate", "resp.rate", "/min"),
                     ("Body temperature", "temp.c", "°C")]),
    ("Laboratory", [("Blood glucose", "glucose.mgdl", "mg/dL"), ("Hemoglobin", "hemoglobin.gdl", "g/dL"),
                    ("Vitamin D", "vitd.ngml", "ng/mL"), ("24-hour urine volume", "urine.volumeL", "L"),
                    ("Urinary calcium", "urine.calciumMgDay", "mg/day")]),
    ("Cognition and sleep", [("Mean reaction time", "pvt.meanRtMs", "ms"), ("PVT lapses", "pvt.lapses", ""),
                             ("Sleep duration", "sleep.hours", "hours")]),
    ("Musculoskeletal", [("Back pain score", "back.pain", "/10"),
                         ("Hip bone density change", "_zero", "% (reference DXA scan)"),
                         ("Strength change", "_zero", "% (reference test)")]),
    ("Radiation", [("Career radiation dose", "prior_career_msv", "mSv")]),
]


def value(c, key):
    if key == "_zero":
        return "0"
    if key == "bp":
        return f"{c.baseline['bp.sys']:g}/{c.baseline['bp.dia']:g}"
    if key in ("resting_hr", "spo2", "prior_career_msv"):
        return f"{getattr(c, key):g}"
    return f"{c.baseline[key]:g}"


def text(c) -> str:
    lines = [
        "MEDVITAL PRE-FLIGHT MEDICAL REPORT",
        "SIMULATED: fictional astronaut for the NASA Space Apps 2026 demo. Not a real person, not medical data.",
        "",
        f"Astronaut ID: {c.astronaut_id}",
        f"Name: {c.name}",
        f"Role: {c.role}",
        f"Age: {c.age} years",
        f"Sex: {'female' if c.sex == 'f' else 'male'}",
        f"Height: {c.height_cm:g} cm",
        f"Weight: {c.weight_kg:g} kg",
        "Exam: 30 days before launch (L-30)",
    ]
    for title, rows in SECTIONS:
        lines += ["", title]
        lines += [f"{label}: {value(c, key)} {unit}".rstrip() for label, key, unit in rows]
    lines += ["", "These pre-flight values are this astronaut's baseline. MedVital compares every in-flight",
              "reading with them, not with population averages."]
    return "\n".join(lines) + "\n"


def pdf(path: Path, body: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    cv = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    y = h - 60
    for i, line in enumerate(body.splitlines()):
        if i == 0:
            cv.setFont("Helvetica-Bold", 15)
        elif i == 1:
            cv.setFont("Helvetica-Oblique", 9)
        elif line and ":" not in line:
            cv.setFont("Helvetica-Bold", 11)
            y -= 4
        else:
            cv.setFont("Helvetica", 11)
        cv.drawString(60, y, line)
        y -= 17 if i == 0 else 15
    cv.save()


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    for c in CREW:
        body = text(c)
        (REPORTS / f"{c.report}.txt").write_text(body, encoding="utf-8")
        try:
            pdf(REPORTS / f"{c.report}.pdf", body)
        except ImportError:
            print("reportlab not installed: wrote .txt only")
        print("wrote", c.report)


if __name__ == "__main__":
    main()
