import base64
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID           = os.getenv("ELEVENLABS_AGENT_ID")
TOKEN_TTL_SECONDS  = 604800  # 7 days
OUTPUT_CSV         = Path(__file__).parent / "exam_links.csv"
STUDENTS_JSON      = Path(__file__).parent / "students.json"
TOKEN_URL          = "https://api.elevenlabs.io/v1/convai/conversation/get_signed_url"


def get_signed_url(student: dict) -> str:
    resp = requests.get(
        TOKEN_URL,
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        params={"agent_id": AGENT_ID},
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} — {resp.text}")
        
    ws_url = resp.json()["signed_url"]
    token = ws_url.split("conversation_signature=")[-1]
    
    # encode variables to pass through url
    variables = {
        "student_id":      student["student_id"],
        "student_name":    student["student_name"],
        "project_details": student["project_details"],
    }
    vars_b64 = base64.b64encode(json.dumps(variables).encode("utf-8")).decode("utf-8")
    
    return f"https://elevenlabs.io/app/talk-to?agent_id={AGENT_ID}&token={token}&vars={vars_b64}"


def main():
    missing = [k for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID") if not os.getenv(k)]
    if missing:
        sys.exit(f"[ERROR] Missing env vars: {', '.join(missing)}")
    if not STUDENTS_JSON.exists():
        sys.exit(f"[ERROR] {STUDENTS_JSON} not found — run summarize_projects.py first")

    students = json.loads(STUDENTS_JSON.read_text(encoding="utf-8"))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M UTC")
    rows = []

    for s in students:
        try:
            url = get_signed_url(s)
            rows.append({"student_id": s["student_id"], "student_name": s["student_name"],
                         "exam_url": url, "expires_at": expires_at})
            print(f"{s['student_name']} ({s['student_id']}): {url}")
        except RuntimeError as exc:
            print(f"FAILED {s['student_name']}: {exc}")

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["student_id", "student_name", "exam_url", "expires_at"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} link(s) to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
