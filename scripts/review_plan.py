import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Load variables from local .env file
load_dotenv()

# Priority fallback sequence across available Flash endpoints
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

def extract_review_guidelines(agents_file: Path) -> str:
    """Extracts only the fidelity hierarchy and parity rules to keep the prompt small and fast."""
    if not agents_file.exists():
        return ""
    
    text = agents_file.read_text(encoding="utf-8")
    sections = []
    
    # 1. Extract Core Optimization Principles
    if "## Core Optimization Principles" in text:
        start = text.find("## Core Optimization Principles")
        end = text.find("### Core Stack", start)
        if end != -1:
            sections.append(text[start:end].strip())
        else:
            sections.append(text[start:start+1200].strip())
            
    # 2. Extract Critical File Parity Rules
    if "### Critical File Parity Rules" in text:
        start = text.find("### Critical File Parity Rules")
        end = text.find("## 6. Execution Modes", start)
        if end != -1:
            sections.append(text[start:end].strip())
        else:
            sections.append(text[start:start+1000].strip())

    return "\n\n---\n\n".join(sections)

def generate_with_fallback(client, prompt: str) -> str:
    """Tries models sequentially with backoff on 503 capacity errors."""
    for model_name in CANDIDATE_MODELS:
        for attempt in range(3):
            try:
                print(f"[Reviewer] Trying {model_name} (attempt {attempt + 1})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    wait_time = 2 * (attempt + 1)
                    print(f"[Reviewer] {model_name} busy (503). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                # If non-503 or repeated failure, advance to next model
                print(f"[Reviewer] Error on {model_name}: {err_str}")
                break
    raise RuntimeError("All candidate models were unavailable due to high demand.")

def run_review():
    plan_file = Path(".scratch/plan.md")
    agents_file = Path("AGENTS.md")
    review_output = Path(".scratch/plan_review.md")

    if not plan_file.exists():
        print("ERROR: .scratch/plan.md not found. Cannot perform review.")
        sys.exit(1)

    plan_content = plan_file.read_text(encoding="utf-8")
    # Load only targeted sections rather than the full AGENTS.md document
    agents_guide = extract_review_guidelines(agents_file)

    prompt = f"""
You are the dedicated Senior Architecture & Engineering Reviewer for the 2025 Chevrolet Equinox EV Route Optimizer & Pricing Engine.

Strictly audit the implementation plan against our project standards:

--- PROJECT AGENTS.MD GUIDELINES ---
{agents_guide}

--- PROPOSED IMPLEMENTATION PLAN (.scratch/plan.md) ---
{plan_content}

REVIEW INSTRUCTIONS:
1. Enforce Ground-Truth Fidelity (Highest Priority):
   - Reject any plan that degrades FastSim road-load physics, flattens the Ultium charging taper, simplifies weather/elevation impacts, or introduces heuristics that risk missing the true Fastest, Cheapest, or Balanced Pareto routes.
   - Ensure proposed latency improvements rely on precomputed offline caches (data/*.json), vectorized NumPy operations, or geometric pruning—never precision loss.
2. Verify File Parity:
   - Ensure any UI edits explicitly account for synchronizing index.html, public/index.html, and ui/templates/index.html.
3. Check Serverless Runtime Limits:
   - Verify statelessness (no persistent file writes outside /tmp, no persistent in-memory global caches).
4. Verify Required Test Gates:
   - Ensure tests/test_engine.py, tests/test_js_syntax.py, or other relevant suites are gated.

OUTPUT FORMAT:
Your output must start with either:
Status: APPROVED
or
Status: CHANGES REQUESTED

Followed by:
- Fidelity Assessment: (Pass/Fail with brief reason)
- File Parity & Runtime Assessment: (Pass/Fail with brief reason)
- Actionable Blockers / Required Changes: (Numbered list if changes requested, or confirmation if approved)
"""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment or .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    try:
        verdict = generate_with_fallback(client, prompt)
    except Exception as e:
        print(f"Failed to generate review: {e}")
        sys.exit(1)

    review_output.write_text(verdict, encoding="utf-8")
    print(f"\n[Review Complete] Written to {review_output}\n")
    print(verdict)

    if "Status: APPROVED" in verdict:
        sys.exit(0)
    else:
        sys.exit(2)

if __name__ == "__main__":
    run_review()