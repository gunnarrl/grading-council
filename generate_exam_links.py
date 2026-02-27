import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID           = os.getenv("ELEVENLABS_AGENT_ID")

TOKEN_TTL_SECONDS = 604800 # 7 days
OUTPUT_CSV = Path(__file__).parent / "exam_links.csv"

# Student roster

STUDENTS = [
    {
        "student_id":      "123456789",
        "student_name":    "Todd",
        "project_details": (
            "250 MWth bare cylindrical UO2 core, H/D=1. "
            "2-group diffusion, k_eff=1.0021, 4.51% U-235 enrichment. "
            "Peak centerline fuel temperature 1,847 °C. "
            "Burnup: 43.2 MWd/kgU at 4.5% and 56.1 MWd/kgU at 5.5%. "
            "Finite-difference scheme, 200 mesh points, convergence at dx=0.5 cm."
        ),
    },
    {
        "student_id":      "934518146",
        "student_name":    "Gunnar",
        "project_details": (
            "250 MWth MOX core, 5.5% fissile Pu fraction, water reflector. "
            "1-group diffusion, k_eff=0.9983 (under-critical — student flagged this). "
            "Peak centerline fuel temperature 2,012 °C (near UO2 melting limit). "
            "Burnup: 51.4 MWd/kgU. "
            "Finite-difference, 150 mesh points, error ~0.8% versus analytic solution."
        ),
    },
]


ELEVENLABS_TOKEN_URL = "https://api.elevenlabs.io/v1/convai/conversation/token"


def get_signed_url(student: dict) -> str:
    """
    Call the ElevenLabs API to obtain a signed, student-specific conversation URL.
    The variables dict maps directly onto the {{placeholders}} in your agent prompt.
    """
    payload = {
        "agent_id": AGENT_ID,
        "ttl":      TOKEN_TTL_SECONDS,
        "conversation_config_override": {
            "agent": {
                "prompt": {
                    "variables": {
                        "student_id":      student["student_id"],
                        "student_name":    student["student_name"],
                        "project_details": student["project_details"],
                    }
                }
            }
        },
    }

    resp = requests.post(
        ELEVENLABS_TOKEN_URL,
        headers={
            "xi-api-key":   ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(
            f"ElevenLabs API error for {student['student_name']}: "
            f"{resp.status_code} — {resp.text}"
        )

    data = resp.json()
    signed_ws_url = data["signed_url"]           # wss://api.elevenlabs.io/v1/convai/conversation?token=...
    token = signed_ws_url.split("token=")[-1]    # extract just the token
    browser_url = f"https://elevenlabs.io/app/talk-to?agent_id={AGENT_ID}&token={token}"
    return browser_url


def main():

    # Validate env vars
    missing = [k for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID") if not os.getenv(k)]
    if missing:
        sys.exit(f"[ERROR] Missing environment variables: {', '.join(missing)} — add them to .env")

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    ).strftime("%Y-%m-%d %H:%M UTC")

    rows = []
    print(f"\nGenerating exam links (expire: {expires_at})\n{'─' * 60}")

    for student in STUDENTS:
        try:
            url = get_signed_url(student)
            rows.append({
                "student_id":   student["student_id"],
                "student_name": student["student_name"],
                "exam_url":     url,
                "expires_at":   expires_at,
            })
            print(f"{student['student_name']} ({student['student_id']})")
            print(f"{url}\n")
        except RuntimeError as exc:
            print(f"FAILED — {exc}\n")

    # Write CSV
    if rows:
        with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["student_id", "student_name", "exam_url", "expires_at"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"{'─' * 60}\nLinks saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
