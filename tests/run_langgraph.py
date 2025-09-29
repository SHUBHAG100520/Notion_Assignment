
import os, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.append(str(SRC))
from graph_langgraph import run_agent

def print_case(name, prompt, now_iso=None):
    if now_iso:
        os.environ["NOW_ISO"] = now_iso
    else:
        os.environ.pop("NOW_ISO", None)
    out = run_agent(prompt)
    trace = out["trace"]
    print(f"\n=== {name} ===")
    print("TRACE:")
    print(json.dumps(trace, indent=2))
    print("\nREPLY:")
    print(out["reply"])

def main():
    # By default, keep deterministic fallback; to call LLM, set OPENAI_API_KEY and unset USE_MOCK_LLM
    # Test 1 — Product Assist
    print_case(
        "Test 1 — Product Assist",
        "Wedding guest, midi, under $120 — I’m between M/L. ETA to 560001?"
    )
    # Test 2 — Order Help (allowed)
    print_case(
        "Test 2 — Order Help (allowed)",
        "Cancel order A1003 — email mira@example.com.",
        now_iso="2025-09-07T12:40:00Z"
    )
    # Test 3 — Order Help (blocked)
    print_case(
        "Test 3 — Order Help (blocked)",
        "Cancel order A1002 — email alex@example.com.",
        now_iso="2025-09-06T15:10:00Z"
    )
    # Test 4 — Guardrail
    print_case(
        "Test 4 — Guardrail",
        "Can you give me a discount code that doesn’t exist?"
    )

if __name__ == "__main__":
    main()
