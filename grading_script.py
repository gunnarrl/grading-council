"""
grading_script.py
-----------------
NSE 351 Oral Exam Grading Council

Usage:
    python grading_script.py <transcript_file> [options]

Options:
    --student-id ID        Student ID (optional, for labeling output)
    --output FILE          Write JSON report to FILE (default: stdout)
    --skip-round2          Run Round 1 only (no deliberation), useful for testing
    --verbose              Print round-by-round scores to console as they arrive

Example:
    python grading_script.py example_transcript.txt --student-id 934518146 --output report.json
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import anthropic
import openai
import google.generativeai as genai
from dotenv import load_dotenv


from grading_prompts import (
    RUBRIC,
    ROUND1_SYSTEM,
    ROUND1_USER,
    ROUND2_SYSTEM,
    ROUND2_USER,
    CHAIR_SYSTEM,
    CHAIR_USER,
)

# ---------------------------------------------------------------------------
# Model identifiers — update these if API names change
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-sonnet-4-6"   # user specified: "claude 4.6 sonnet"
GPT_MODEL    = "gpt-5.2-2025-12-11"     # user specified: "GPT 5.2" — update when available
GEMINI_MODEL = "gemini-3.1-pro-preview"      # user specified: "gemini 3.1 pro" — update when available

# Category weights (must sum to 1.0)
WEIGHTS = {
    "conceptual_understanding":   0.30,
    "neutronics_mastery":         0.20,
    "coupled_physics_reasoning":  0.20,
    "quantitative_agility":       0.15,
    "engineering_judgment":       0.15,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    """Load API keys from .env file."""
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
    keys = {
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "openai":    os.getenv("OPENAI_API_KEY"),
        "gemini":    os.getenv("GEMINI_API_KEY"),
    }
    missing = [k for k, v in keys.items() if not v or v.startswith("your_")]
    if missing:
        print(f"[ERROR] Missing or placeholder API keys: {missing}", file=sys.stderr)
        print("        Fill in .env with real keys before running.", file=sys.stderr)
        sys.exit(1)
    return keys


def extract_json(text: str) -> dict:
    """
    Parse JSON from a model response.
    Handles responses that may wrap the JSON in markdown code fences.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:] if lines[0].startswith("```") else lines
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse JSON from model response: {e}\n\nRaw text:\n{text[:500]}")


def compute_weighted_total(scores: dict) -> float:
    """
    Compute weighted total from a scores dict.
    N/A (null) categories are excluded from the denominator so the student
    is not penalized for unasked questions.
    """
    total = 0.0
    weight_sum = 0.0
    for cat, weight in WEIGHTS.items():
        score = scores.get(cat)
        if score is not None:
            total += score * weight
            weight_sum += weight
    if weight_sum == 0:
        return 0.0
    # Rescale to account for missing categories
    return round(total / weight_sum * 100, 1) if weight_sum < 1.0 else round(total, 1)


def print_scores_table(model_name: str, round_num: int, assessment: dict):
    """Pretty-print a score table for a single model/round."""
    label = f"{model_name} — Round {round_num}"
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    scores = assessment.get("scores", {})
    for cat, weight in WEIGHTS.items():
        score = scores.get(cat)
        score_str = f"{score:>5.1f}" if score is not None else "  N/A"
        print(f"  {cat:<35} {score_str}  (wt {weight:.0%})")
    print(f"  {'─'*50}")
    wt = assessment.get("weighted_total")
    print(f"  {'Weighted Total':<35} {wt:>5.1f}" if wt is not None else f"  Weighted Total: N/A")
    print()


# ---------------------------------------------------------------------------
# Model callers
# ---------------------------------------------------------------------------

def call_claude(system: str, user: str, model_name: str = None) -> str:
    """Call Anthropic Claude."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def call_gpt(system: str, user: str, model_name: str = None) -> str:
    """Call OpenAI GPT."""
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=GPT_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content


def call_gemini(system: str, user: str, model_name: str = None) -> str:
    """Call Google Gemini."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system,
    )
    response = model.generate_content(
        user,
        generation_config=genai.types.GenerationConfig(max_output_tokens=4096),
    )
    return response.text


# Map model keys to caller functions
MODEL_CALLERS = {
    "claude": call_claude,
    "gpt":    call_gpt,
    "gemini": call_gemini,
}

# ---------------------------------------------------------------------------
# Grading rounds
# ---------------------------------------------------------------------------

def run_round1(transcript: str, verbose: bool = False) -> dict:
    """
    Run Round 1: all three models grade the transcript independently, in parallel.
    Returns dict: { "claude": {...}, "gpt": {...}, "gemini": {...} }
    """
    print("\n[Round 1] Independent grading — running all 3 models in parallel...")

    user_prompt = ROUND1_USER.format(rubric=RUBRIC, transcript=transcript)

    def grade(model_key: str) -> tuple[str, dict]:
        caller = MODEL_CALLERS[model_key]
        raw = caller(ROUND1_SYSTEM, user_prompt)
        assessment = extract_json(raw)
        # Ensure weighted_total is computed correctly
        assessment["weighted_total"] = compute_weighted_total(assessment.get("scores", {}))
        assessment["model"] = model_key
        assessment["round"] = 1
        return model_key, assessment

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(grade, k): k for k in MODEL_CALLERS}
        for future in as_completed(futures):
            model_key = futures[future]
            try:
                key, assessment = future.result()
                results[key] = assessment
                if verbose:
                    print_scores_table(key.upper(), 1, assessment)
                else:
                    print(f"  ✓ {key} complete  ({assessment.get('weighted_total', '?'):.1f}/100)")
            except Exception as e:
                print(f"  ✗ {model_key} FAILED: {e}", file=sys.stderr)
                results[model_key] = {"error": str(e), "round": 1, "model": model_key}

    return results


def run_round2(transcript: str, round1: dict, verbose: bool = False) -> dict:
    """
    Run Round 2: each model sees the other two's Round 1 and may revise.
    Returns dict: { "claude": {...}, "gpt": {...}, "gemini": {...} }
    """
    print("\n[Round 2] Deliberation — each model reviews peers' Round 1 assessments...")

    models = list(MODEL_CALLERS.keys())

    def deliberate(model_key: str) -> tuple[str, dict]:
        peers = [m for m in models if m != model_key]
        peer_a, peer_b = peers[0], peers[1]
        user_prompt = ROUND2_USER.format(
            rubric=RUBRIC,
            transcript=transcript,
            my_round1=json.dumps(round1.get(model_key, {}), indent=2),
            peer_a_round1=json.dumps(round1.get(peer_a, {}), indent=2),
            peer_b_round1=json.dumps(round1.get(peer_b, {}), indent=2),
        )
        caller = MODEL_CALLERS[model_key]
        raw = caller(ROUND2_SYSTEM, user_prompt)
        assessment = extract_json(raw)
        assessment["weighted_total"] = compute_weighted_total(assessment.get("scores", {}))
        assessment["model"] = model_key
        assessment["round"] = 2
        return model_key, assessment

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(deliberate, k): k for k in models}
        for future in as_completed(futures):
            model_key = futures[future]
            try:
                key, assessment = future.result()
                results[key] = assessment
                r1_total = round1.get(key, {}).get("weighted_total", "?")
                r2_total = assessment.get("weighted_total", "?")
                delta = ""
                if isinstance(r1_total, (int, float)) and isinstance(r2_total, (int, float)):
                    diff = r2_total - r1_total
                    delta = f"  (Δ {diff:+.1f})"
                if verbose:
                    print_scores_table(key.upper(), 2, assessment)
                else:
                    print(f"  ✓ {key} complete  {r1_total:.1f} → {r2_total:.1f}{delta}")
            except Exception as e:
                print(f"  ✗ {model_key} FAILED: {e}", file=sys.stderr)
                results[model_key] = {"error": str(e), "round": 2, "model": model_key}

    return results


def run_chair_synthesis(transcript: str, round1: dict, round2: dict, verbose: bool = False) -> dict:
    """
    Chair synthesis: Claude receives all 6 assessments and produces the final grade.
    """
    print("\n[Chair] Claude synthesizing final grade...")

    user_prompt = CHAIR_USER.format(
        rubric=RUBRIC,
        transcript=transcript,
        claude_r1=json.dumps(round1.get("claude", {}), indent=2),
        claude_r2=json.dumps(round2.get("claude", {}), indent=2),
        gpt_r1=json.dumps(round1.get("gpt",    {}), indent=2),
        gpt_r2=json.dumps(round2.get("gpt",    {}), indent=2),
        gemini_r1=json.dumps(round1.get("gemini", {}), indent=2),
        gemini_r2=json.dumps(round2.get("gemini", {}), indent=2),
    )

    raw = call_claude(CHAIR_SYSTEM, user_prompt)
    final = extract_json(raw)
    final["weighted_total"] = compute_weighted_total(final.get("final_scores", {}))
    return final


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def assemble_report(
    student_id: str,
    transcript_file: str,
    round1: dict,
    round2: dict | None,
    final: dict,
) -> dict:
    """Assemble the full JSON report."""
    return {
        "metadata": {
            "student_id":      student_id,
            "transcript_file": transcript_file,
            "graded_at":       datetime.now().isoformat(),
            "models": {
                "claude": CLAUDE_MODEL,
                "gpt":    GPT_MODEL,
                "gemini": GEMINI_MODEL,
            },
        },
        "round1": round1,
        "round2": round2,
        "final":  final,
    }


def print_final_summary(final: dict):
    """Print a human-readable final summary."""
    print("\n" + "="*60)
    print("  FINAL GRADE SUMMARY")
    print("="*60)
    scores = final.get("final_scores", {})
    for cat, weight in WEIGHTS.items():
        score = scores.get(cat)
        score_str = f"{score:>5.1f}" if score is not None else "  N/A"
        print(f"  {cat:<35} {score_str}  (wt {weight:.0%})")
    print(f"  {'─'*50}")
    wt = final.get("weighted_total", 0)
    letter = final.get("letter_grade", "?")
    print(f"  {'WEIGHTED TOTAL':<35} {wt:>5.1f}/100  [{letter}]")
    print()

    if final.get("agreement_analysis"):
        print(f"  Grader Agreement: {final['agreement_analysis']}")
        print()

    if final.get("strengths"):
        print("  STRENGTHS:")
        for s in final["strengths"]:
            print(f"    • {s}")
        print()

    if final.get("weaknesses"):
        print("  WEAKNESSES:")
        for w in final["weaknesses"]:
            print(f"    • {w}")
        print()

    if final.get("recommended_actions"):
        print("  RECOMMENDED ACTIONS:")
        for r in final["recommended_actions"]:
            print(f"    → {r}")
        print()

    if final.get("chair_summary"):
        print(f"  SUMMARY:\n  {final['chair_summary']}")
        print()

    print("="*60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="NSE 351 Oral Exam Grading Council — multi-LLM transcript grader"
    )
    parser.add_argument("transcript",     help="Path to the transcript text file")
    parser.add_argument("--student-id",   default="unknown", help="Student ID for labeling")
    parser.add_argument("--output",       default=None, help="Write JSON report to this file")
    parser.add_argument("--skip-round2",  action="store_true", help="Skip deliberation round")
    parser.add_argument("--verbose",      action="store_true", help="Print per-round score tables")
    args = parser.parse_args()

    # Load API keys
    keys = load_env()

    # Load transcript
    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"[ERROR] Transcript file not found: {transcript_path}", file=sys.stderr)
        sys.exit(1)
    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        print("[ERROR] Transcript file is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"\nNSE 351 Grading Council")
    print(f"Transcript : {transcript_path.name}")
    print(f"Student ID : {args.student_id}")
    print(f"Models     : Claude={CLAUDE_MODEL}, GPT={GPT_MODEL}, Gemini={GEMINI_MODEL}")
    print(f"Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    t_start = time.time()

    # Round 1
    round1 = run_round1(transcript, verbose=args.verbose)

    # Round 2 (deliberation)
    round2 = None
    if not args.skip_round2:
        round2 = run_round2(transcript, round1, verbose=args.verbose)
    else:
        print("\n[Round 2] Skipped (--skip-round2 flag set)")
        # If no round2, use round1 results as the deliberation input for the chair
        round2 = round1

    # Chair synthesis
    final = run_chair_synthesis(transcript, round1, round2, verbose=args.verbose)

    elapsed = time.time() - t_start
    print(f"\n  Grading complete in {elapsed:.1f}s")

    # Assemble and output report
    report = assemble_report(
        student_id=args.student_id,
        transcript_file=str(transcript_path.resolve()),
        round1=round1,
        round2=round2 if not args.skip_round2 else None,
        final=final,
    )

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  Report written to: {out_path}")
    else:
        print("\n" + json.dumps(report, indent=2))

    print_final_summary(final)


if __name__ == "__main__":
    main()
