"""
Step 2: Apply a user-typed, plain-English risk rule to position data using
an LLM hosted on Featherless AI (OpenAI-compatible API).

This takes the enriched positions from step 1 (symbol, drawdown_pct,
concentration_pct) plus a rule like:
    "flag anything down more than 8%, or over 30% of my portfolio"

...and asks the LLM to decide which positions are flagged and why,
returning strict JSON so the rest of our pipeline can use it programmatically.

Run:
    uv run step2_threshold.py
"""

import json, os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-20b"  

client = Groq()


SYSTEM_PROMPT = """You are a portfolio risk-flagging assistant.

You will be given:
1. A list of stock positions, each with a drawdown_pct (how far below cost
   basis the position is; negative = loss) and a concentration_pct (what %
   of the total portfolio this position represents).
2. A risk rule written by the user in plain English.

Your job: apply the rule to each position and decide which ones should be
flagged for hedging.

Respond with ONLY valid JSON, no other text, in this exact shape:
{
  "flagged": [
    {"symbol": "AAPL", "reason": "down 9.2%, exceeding the 8% drawdown rule"}
  ],
  "not_flagged": [
    {"symbol": "MSFT", "reason": "down 3.1%, within threshold"}
  ]
}

If a position doesn't clearly violate the rule, put it in not_flagged.
Do not invent positions that weren't given to you.
"""


def apply_threshold_rule(positions: list[dict], rule_text: str) -> dict:
    user_content = json.dumps({
        "positions": positions,
        "rule": rule_text,
    }, indent=2)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,  # deterministic — we want consistent risk decisions, not creativity
    )

    raw_text = response.choices[0].message.content.strip()

    # Some models wrap JSON in ```json ... ``` fences even when told not to — strip if present
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print("WARNING: model did not return valid JSON. Raw output was:")
        print(raw_text)
        return {"flagged": [], "not_flagged": []}


if __name__ == "__main__":
    # --- Test data (replace with real output from step1_pos.py once you have a filled position) ---
    test_positions = [
        {"symbol": "AAPL", "qty": "5", "cost_basis": 950.00, "market_value": 862.50,
         "drawdown_pct": -9.21, "concentration_pct": 0.86},
        {"symbol": "MSFT", "qty": "3", "cost_basis": 1200.00, "market_value": 1163.00,
         "drawdown_pct": -3.08, "concentration_pct": 1.16},
    ]

    rule = input("Type your risk rule (e.g. 'flag anything down more than 8%'): ")

    result = apply_threshold_rule(test_positions, rule)

    print("\nFlagged positions:")
    for p in result.get("flagged", []):
        print(f"  - {p['symbol']}: {p['reason']}")

    print("\nNot flagged:")
    for p in result.get("not_flagged", []):
        print(f"  - {p['symbol']}: {p['reason']}")