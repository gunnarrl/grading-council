import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-3-flash-preview"
ROSTER_CSV     = Path(__file__).parent / "roster.csv"
PDF_DIR        = Path(__file__).parent
OUTPUT_JSON    = Path(__file__).parent / "students.json"

SUMMARY_PROMPT = """\
You are an assistant helping a nuclear engineering professor prepare personalised \
oral exam questions. You have been given a student group's final project report \
for NSE 351 – Introduction to Nuclear Reactor Engineering.

The project asks each group to design a 250 MWth homogeneous cylindrical SMR core \
covering: one-group criticality, two-group diffusion, numerical methods, \
thermal-hydraulics, fuel cycle, and economics.

Extract the following information EXACTLY as the students reported it (use their \
numbers, not the assignment defaults). If a value is missing or not computed, \
write "not reported".

Return ONLY a JSON object — no markdown, no prose:

{
  "core_geometry": "<active height, H/D ratio, critical radius, material buckling Bm²>",
  "neutronics": "<one-group k_inf, two-group k_eff, fast-to-thermal flux ratio; note any discrepancy between one- and two-group results>",
  "numerical_methods": "<discretisation scheme, number of mesh points, convergence criterion, numerical error vs analytic solution>",
  "thermal_hydraulics": "<volumetric power density, peak fuel centerline temperature, coolant outlet temperature, margin to melting, margin to boiling>",
  "fuel_cycle": "<enrichment case(s), burnup target, computed cycle length(s), qualitative reactivity swing comment>",
  "economics": "<fuel cost per MWh for each enrichment case, dominant cost driver, which case the group recommends and why>",
  "student_identified_limitations": "<key simplifications the students acknowledged, e.g. homogenisation, no reflector, no Doppler, no 3D peaking>",
  "notable_findings": "<anything unusual, surprising, or particularly well-reasoned that an examiner should probe>"
}
"""

SECTION_LABELS = {
    "core_geometry":               "Core Geometry",
    "neutronics":                  "Neutronics",
    "numerical_methods":           "Numerical Methods",
    "thermal_hydraulics":          "Thermal-Hydraulics",
    "fuel_cycle":                  "Fuel Cycle",
    "economics":                   "Economics",
    "student_identified_limitations": "Student-Identified Limitations",
    "notable_findings":            "Notable Findings",
}


def upload_pdf(client, pdf_path: Path) -> types.File:
    uploaded = client.files.upload(file=pdf_path, config=types.UploadFileConfig(mime_type="application/pdf"))
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state.name != "ACTIVE":
        raise RuntimeError(f"Upload failed: {uploaded.state.name}")
    return uploaded


def summarise_pdf(client, uploaded_file: types.File) -> dict:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_uri(file_uri=uploaded_file.uri, mime_type="application/pdf"), SUMMARY_PROMPT],
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()[1:]
        raw = "\n".join(lines[:-1] if lines[-1].strip().startswith("```") else lines)
    return json.loads(raw)


def to_project_details(summary: dict) -> str:
    return "  ".join(
        f"{label}: {summary[key]}."
        for key, label in SECTION_LABELS.items()
        if summary.get(key)
    )


def main():
    if not GEMINI_API_KEY:
        sys.exit("[ERROR] GEMINI_API_KEY not set in .env")
    if not ROSTER_CSV.exists():
        sys.exit(f"[ERROR] {ROSTER_CSV} not found")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Load roster grouped by group_id
    groups: dict[str, list[dict]] = {}
    with ROSTER_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = row["group_id"].strip()
            student = {k: row[k].strip() for k in ("student_id", "student_name", "pdf_filename")}
            groups.setdefault(gid, []).append(student)

    # Summarise each unique PDF once
    pdf_summaries: dict[str, dict] = {}
    seen: set[str] = set()

    for students in groups.values():
        fname = students[0]["pdf_filename"]
        
        if fname in seen:
            continue
            
        seen.add(fname)
        pdf_path = PDF_DIR / fname
        
        uploaded = upload_pdf(client, pdf_path)
        pdf_summaries[fname] = summarise_pdf(client, uploaded)
        print(f"Summarised project {fname}")

    # Build one entry per student
    output = []
    for gid, students in groups.items():
        raw = pdf_summaries.get(students[0]["pdf_filename"], {})
        details = to_project_details(raw) if raw else "Summary not available."
        for s in students:
            output.append({
                "student_id":      s["student_id"],
                "student_name":    s["student_name"],
                "group_id":        gid,
                "project_details": details,
                "_raw_summary":    raw,
            })
            print(f"Summarised student {s['student_name']} ({s['student_id']})")

    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved {len(output)} student(s) to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
