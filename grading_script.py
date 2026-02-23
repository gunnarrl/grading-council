import json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
import openai
import google.generativeai as genai
from dotenv import load_dotenv

from grading_prompts import RUBRIC, ROUND1_SYSTEM, ROUND1_USER, ROUND2_SYSTEM, ROUND2_USER, CHAIR_SYSTEM, CHAIR_USER

# Model names — update if API identifiers change
CLAUDE_MODEL = "claude-sonnet-4-6"
GPT_MODEL    = "gpt-5.2-2025-12-11"
GEMINI_MODEL = "gemini-3.1-pro-preview"

WEIGHTS = {
    "conceptual_understanding":  0.30,
    "neutronics_mastery":        0.20,
    "coupled_physics_reasoning": 0.20,
    "quantitative_agility":      0.15,
    "engineering_judgment":      0.15,
}


def load_keys():
    load_dotenv(Path(__file__).parent / ".env")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        if not os.getenv(key) or os.getenv(key).startswith("your_"):
            sys.exit(f"[ERROR] Missing API key: {key} — fill in .env")


def parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def weighted_total(scores: dict) -> float:
    total, denom = 0.0, 0.0
    for cat, w in WEIGHTS.items():
        s = scores.get(cat)
        if s is not None:
            total += s * w
            denom += w
    return round(total / denom * 100, 1) if denom < 1.0 else round(total, 1)


# --- API callers ---

def call_claude(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=4096,
        system=system, messages=[{"role": "user", "content": user}]
    )
    return msg.content[0].text


def call_gpt(system: str, user: str) -> str:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    r = client.chat.completions.create(
        model=GPT_MODEL, max_tokens=4096,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return r.choices[0].message.content


def call_gemini(system: str, user: str) -> str:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(model_name=GEMINI_MODEL, system_instruction=system)
    return model.generate_content(
        user, generation_config=genai.types.GenerationConfig(max_output_tokens=4096)
    ).text


CALLERS = {"claude": call_claude, "gpt": call_gpt, "gemini": call_gemini}


# --- Grading rounds ---

def round1(transcript: str) -> dict:
    user_prompt = ROUND1_USER.format(rubric=RUBRIC, transcript=transcript)

    def grade(key):
        result = parse_json(CALLERS[key](ROUND1_SYSTEM, user_prompt))
        result["model"], result["round"] = key, 1
        result["weighted_total"] = weighted_total(result.get("scores", {}))
        return key, result

    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for future in as_completed({ex.submit(grade, k): k for k in CALLERS}):
            k, r = future.result()
            results[k] = r
    return results


def round2(transcript: str, r1: dict) -> dict:
    def deliberate(key):
        peers = [p for p in CALLERS if p != key]
        user_prompt = ROUND2_USER.format(
            rubric=RUBRIC, transcript=transcript,
            my_round1=json.dumps(r1.get(key, {}), indent=2),
            peer_a_round1=json.dumps(r1.get(peers[0], {}), indent=2),
            peer_b_round1=json.dumps(r1.get(peers[1], {}), indent=2),
        )
        result = parse_json(CALLERS[key](ROUND2_SYSTEM, user_prompt))
        result["model"], result["round"] = key, 2
        result["weighted_total"] = weighted_total(result.get("scores", {}))
        return key, result

    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for future in as_completed({ex.submit(deliberate, k): k for k in CALLERS}):
            k, r = future.result()
            results[k] = r
    return results


def chair_synthesis(transcript: str, r1: dict, r2: dict) -> dict:
    user_prompt = CHAIR_USER.format(
        rubric=RUBRIC, transcript=transcript,
        claude_r1=json.dumps(r1.get("claude", {}), indent=2),
        claude_r2=json.dumps(r2.get("claude", {}), indent=2),
        gpt_r1=json.dumps(r1.get("gpt", {}), indent=2),
        gpt_r2=json.dumps(r2.get("gpt", {}), indent=2),
        gemini_r1=json.dumps(r1.get("gemini", {}), indent=2),
        gemini_r2=json.dumps(r2.get("gemini", {}), indent=2),
    )
    final = parse_json(call_claude(CHAIR_SYSTEM, user_prompt))
    final["weighted_total"] = weighted_total(final.get("final_scores", {}))
    return final


# --- Main ---

def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: python3 grading_script.py <transcript_file> <student_id>")

    transcript_path = Path(sys.argv[1])
    student_id = sys.argv[2]

    if not transcript_path.exists():
        sys.exit(f"[ERROR] File not found: {transcript_path}")

    transcript = transcript_path.read_text(encoding="utf-8").strip()
    load_keys()

    r1 = round1(transcript)
    r2 = round2(transcript, r1)
    final = chair_synthesis(transcript, r1, r2)

    report = {
        "metadata": {
            "student_id": student_id,
            "transcript_file": str(transcript_path.resolve()),
            "graded_at": datetime.now().isoformat(),
            "models": {"claude": CLAUDE_MODEL, "gpt": GPT_MODEL, "gemini": GEMINI_MODEL},
        },
        "round1": r1,
        "round2": r2,
        "final": final,
    }

    out = Path(f"{student_id}_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to {out}")


if __name__ == "__main__":
    main()
