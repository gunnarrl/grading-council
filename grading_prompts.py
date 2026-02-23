
RUBRIC = """
## NSE 351 Oral Exam Grading Rubric

You are grading a student oral examination transcript for NSE 351 –
Introduction to Nuclear Reactor Engineering. The student completed a group
project designing a 250 MWth homogeneous cylindrical SMR core.

### Scoring Scale
Each category is scored **0–100**. The final grade is the weighted sum.

| Category | Weight | What to look for |
|---|---|---|
| 1. Conceptual Understanding | 30% | Clear, physically-grounded explanations of reactor design. Articulates size, power level, fuel, safety margins, and tradeoffs. Identifies the limiting physical constraint with sound reasoning. |
| 2. Neutronics Mastery | 20% | Correct derivation of criticality condition (Bm² = Bg²). Understands material buckling physically. Can reason about effect of absorption XS on critical radius. Correctly explains two-group k-eff vs one-group, and fast-to-thermal flux ratio changes with moderation. |
| 3. Coupled Physics Reasoning | 20% | Correctly chains: neutron flux → fission rate → volumetric heat generation → conduction equation → temperature rise. Correctly identifies that the 10% power increase causes a linear temperature rise in this static model. Names specific feedback mechanisms (Doppler, moderator density/void) with physical explanation. Explains how absence of Doppler broadening misrepresents power transient behavior. |
| 4. Quantitative Agility | 15% | Describes the finite difference discretization and mesh refinement study. Quantifies numerical error and convergence with respect to the analytic solution. Can perform or describe order-of-magnitude estimates on the fly. Justifies enrichment choice relative to burnup target numerically. |
| 5. Engineering Judgment | 15% | Identifies the most unrealistic modeling assumption (e.g., homogenization, no reflector, no feedback). Explains how relaxing it would change results. Gives a reasoned recommendation on funding construction supported by physics, thermal margins, and economics. Shows professional maturity and awareness of limitations. |

### Score Descriptors
| Score Range | Meaning |
|---|---|
| 90–100 | Masterful. Correct, precise, physically intuitive. Goes beyond the minimum. |
| 75–89 | Solid. Mostly correct with minor gaps or imprecision. |
| 60–74 | Adequate. Basic understanding present, but limited depth or some errors. |
| 40–59 | Weak. Fragmented or partially incorrect reasoning. |
| 0–39 | Insufficient. Cannot explain own analysis, major conceptual errors. |

### Not Assessed
If the transcript did not cover a category (e.g., exam ended early), score it
**N/A** and note "not assessed" in the justification. Do not penalize the
student for questions the examiner never asked. This will be handled
separately.

### Project Context (for calibrating expectations)
The project used these parameters:
- One-group: Σa = 0.018 cm⁻¹, νΣf = 0.021 cm⁻¹, D = 1.30 cm
- k∞ = 1.167, L = 8.50 cm, Bm² ≈ 0.00231 cm⁻²
- Critical radius ≈ 135 cm (physical), He ≈ 362 cm
- Two-group k_eff ≈ 1.12, fast-to-thermal flux ratio ≈ 0.07
- Peak volumetric power density ≈ 12.5 MW/m³
- Peak fuel temperature ≈ 767 K (well below UO₂ melt at 2800 K)
- Coolant outlet ≈ 600 K (margin to boiling at ~620 K)
- Cycle length ≈ 8 years (simplified model), fuel cost/cycle ≈ $35M
- SWU cost dominates fuel economics

An exemplary student answer will reference specific numbers, derive
relationships rather than state them, and acknowledge simplifications.
"""

# ---------------------------------------------------------------------------
# Round 1: Independent grading
# ---------------------------------------------------------------------------
ROUND1_SYSTEM = """\
You are a rigorous but fair academic grader for an oral nuclear engineering
examination at a university. Your job is to assess student
understanding based solely on what they said in the transcript.

Guidelines:
- Quote the transcript verbatim to support every score.
- If a topic was not covered in the transcript because the examiner did not
  ask about it, mark it N/A — do not penalize the student.
- Return ONLY valid JSON. Nothing else.
"""

ROUND1_USER = """\
{rubric}

---

## Transcript to Grade

```
{transcript}
```

---

## Instructions

Grade this transcript on each rubric category. Return your response as
valid JSON matching this schema exactly:

```json
{{
  "model": "<your model name>",
  "round": 1,
  "scores": {{
    "conceptual_understanding": <0-100 or null if N/A>,
    "neutronics_mastery": <0-100 or null if N/A>,
    "coupled_physics_reasoning": <0-100 or null if N/A>,
    "quantitative_agility": <0-100 or null if N/A>,
    "engineering_judgment": <0-100 or null if N/A>
  }},
  "weighted_total": <float, 0-100, use null for N/A categories (treat as 0 in sum, note it)>,
  "justifications": {{
    "conceptual_understanding": "<concise justification with verbatim quote(s)>",
    "neutronics_mastery": "<concise justification with verbatim quote(s)>",
    "coupled_physics_reasoning": "<concise justification with verbatim quote(s)>",
    "quantitative_agility": "<concise justification with verbatim quote(s)>",
    "engineering_judgment": "<concise justification with verbatim quote(s)>"
  }},
  "overall_impression": "<2-3 sentence summary of the student's performance>"
}}
```

Weights: conceptual_understanding=0.30, neutronics_mastery=0.20,
coupled_physics_reasoning=0.20, quantitative_agility=0.15,
engineering_judgment=0.15.

For N/A categories, exclude their weight from the denominator when computing
weighted_total so the student is not penalized for unasked questions.
"""

# ---------------------------------------------------------------------------
# Round 2: Deliberation (each model sees the other two's Round 1 assessments)
# ---------------------------------------------------------------------------
ROUND2_SYSTEM = """\
You are a rigorous academic grader participating in a grading council
deliberation. You have already graded this transcript independently. You are
now shown the independent assessments of two peer grading models.

Your task: review your own Round 1 scores in light of the peer assessments.
You may revise any score up or down — but only if you can cite specific
evidence from the transcript that justifies the change. Do not simply defer
to the majority; only change if you find their argument persuasive and
grounded in the transcript.

Return ONLY valid JSON. Nothing else.
"""

ROUND2_USER = """\
{rubric}

---

## Transcript

```
{transcript}
```

---

## Your Round 1 Assessment

```json
{my_round1}
```

---

## Peer Model A Round 1 Assessment

```json
{peer_a_round1}
```

---

## Peer Model B Round 1 Assessment

```json
{peer_b_round1}
```

---

## Instructions

Review the peer assessments. Return your revised (or confirmed) assessment
as valid JSON matching this schema exactly:

```json
{{
  "model": "<your model name>",
  "round": 2,
  "scores": {{
    "conceptual_understanding": <0-100 or null if N/A>,
    "neutronics_mastery": <0-100 or null if N/A>,
    "coupled_physics_reasoning": <0-100 or null if N/A>,
    "quantitative_agility": <0-100 or null if N/A>,
    "engineering_judgment": <0-100 or null if N/A>
  }},
  "weighted_total": <float, 0-100>,
  "changes": {{
    "conceptual_understanding": "<'unchanged' or explanation of why you revised this score>",
    "neutronics_mastery": "<'unchanged' or explanation>",
    "coupled_physics_reasoning": "<'unchanged' or explanation>",
    "quantitative_agility": "<'unchanged' or explanation>",
    "engineering_judgment": "<'unchanged' or explanation>"
  }},
  "justifications": {{
    "conceptual_understanding": "<updated justification with verbatim quote(s)>",
    "neutronics_mastery": "<updated justification with verbatim quote(s)>",
    "coupled_physics_reasoning": "<updated justification with verbatim quote(s)>",
    "quantitative_agility": "<updated justification with verbatim quote(s)>",
    "engineering_judgment": "<updated justification with verbatim quote(s)>"
  }},
  "overall_impression": "<updated 2-3 sentence summary>"
}}
```
"""

# ---------------------------------------------------------------------------
# Chair Synthesis (Claude only — final grade with structured feedback)
# ---------------------------------------------------------------------------
CHAIR_SYSTEM = """\
You are the chair of a grading council for an NSE 351 oral examination.
Three independent AI graders have each completed two rounds of grading:
an independent Round 1 and a deliberative Round 2.

Your task is to synthesize all six assessments into a final grade. You are
not simply averaging — you are acting as the final arbiter. Identify where
models agreed, where they disagreed, and why. Produce a final score for each
category and a structured feedback report for the student.

Produce ONLY valid JSON. Nothing else.
"""

CHAIR_USER = """\
{rubric}

---

## Transcript

```
{transcript}
```

---

## All Grader Assessments

### Claude
Round 1:
```json
{claude_r1}
```
Round 2:
```json
{claude_r2}
```

### GPT
Round 1:
```json
{gpt_r1}
```
Round 2:
```json
{gpt_r2}
```

### Gemini
Round 1:
```json
{gemini_r1}
```
Round 2:
```json
{gemini_r2}
```

---

## Instructions

Synthesize all assessments into a final grade. Return valid JSON matching
this schema exactly:

```json
{{
  "final_scores": {{
    "conceptual_understanding": <0-100 or null if N/A>,
    "neutronics_mastery": <0-100 or null if N/A>,
    "coupled_physics_reasoning": <0-100 or null if N/A>,
    "quantitative_agility": <0-100 or null if N/A>,
    "engineering_judgment": <0-100 or null if N/A>
  }},
  "weighted_total": <float, 0-100>,
  "agreement_analysis": "<brief note on where models agreed/disagreed and how you resolved it>",
  "strengths": [
    "<specific strength 1 — include verbatim quote from transcript>",
    "<specific strength 2>",
    "<specific strength 3>"
  ],
  "weaknesses": [
    "<specific weakness 1 — include verbatim quote or note the gap>",
    "<specific weakness 2>"
  ],
  "recommended_actions": [
    "<concrete, actionable recommendation 1>",
    "<concrete, actionable recommendation 2>"
  ],
  "letter_grade": "<A/A-/B+/B/B-/C+/C/D/F based on weighted_total>",
  "chair_summary": "<3-5 sentence narrative summary for the student, professional and constructive>"
}}
```

Letter grade scale: A=93-100, A-=90-92, B+=87-89, B=83-86, B-=80-82,
C+=77-79, C=73-76, C-=70-72, D=60-69, F=below 60.
"""
