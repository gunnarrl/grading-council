import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID           = os.getenv("ELEVENLABS_AGENT_ID")
STUDENTS_JSON      = Path(__file__).parent / "students.json"
TRANSCRIPTS_DIR    = Path(__file__).parent / "transcripts"
BASE_URL           = "https://api.elevenlabs.io/v1/convai"


def api_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", headers={"xi-api-key": ELEVENLABS_API_KEY}, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def list_conversations():
    convs, cursor = [], None
    while True:
        params = {"agent_id": AGENT_ID, "page_size": 100}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/conversations", params)
        convs.extend(data.get("conversations", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return [c for c in convs if c.get("status") == "done"]


def format_transcript(turns):
    lines = []
    for t in turns:
        role = "Agent" if t.get("role") == "agent" else "Student"
        msg = t.get("message", "").strip()
        if msg:
            lines.append(f"{role}: {msg}")
    return "\n\n".join(lines)


def extract_student_id(turns, known_ids):
    for msg in [t.get("message", "") for t in turns if t.get("role") == "user"][:5]:
        for sid in known_ids:
            if sid in msg.replace(" ", "").replace("-", ""):
                return sid
        m = re.search(r"\b\d{9}\b", msg)
        if m and m.group() in known_ids:
            return m.group()
    return None


def main():
    missing = [k for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID") if not os.getenv(k)]
    if missing:
        sys.exit(f"[ERROR] Missing env vars: {', '.join(missing)}")

    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    known_ids = {}
    if STUDENTS_JSON.exists():
        known_ids = {r["student_id"]: r["student_name"]
                     for r in json.loads(STUDENTS_JSON.read_text(encoding="utf-8"))}

    already_saved = {p.stem.split("_transcript")[0] for p in TRANSCRIPTS_DIR.glob("*_transcript.txt")}

    for conv in list_conversations():
        turns = api_get(f"/conversations/{conv['conversation_id']}").get("transcript", [])
        student_id = extract_student_id(turns, set(known_ids))
        if not student_id:
            continue
        if student_id in already_saved:
            print(f"Skipped {known_ids.get(student_id, student_id)} ({student_id}) — already saved")
            continue
        out = TRANSCRIPTS_DIR / f"{student_id}_transcript.txt"
        out.write_text(format_transcript(turns), encoding="utf-8")
        print(f"Saved transcript: {known_ids.get(student_id, student_id)} ({student_id})")


if __name__ == "__main__":
    main()
