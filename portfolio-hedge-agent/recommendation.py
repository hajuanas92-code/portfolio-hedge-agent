"""
Step 4: Generate a plain-language hedge recommendation.

Takes:
  - A flagged position (symbol, drawdown_pct, concentration_pct, reason) - from step 2
  - A selected put contract (strike, expiration, cost) - from step 3
  - How many shares are actually owned - from step 1

Computes:
  - How many option contracts are needed to cover the full position
    (each contract covers 100 shares)
  - Total cost of the hedge in dollars

Then asks the LLM to explain the recommendation in clear, plain language -
the kind of explanation a human would actually want to read before approving
a trade.

Run:
    uv run step4_recommendation.py
"""

import math, os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- EDIT THIS ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-20b"
# ------------------

client = Groq()

SYSTEM_PROMPT = """You are a portfolio risk assistant explaining a hedge recommendation
to the account owner in plain, clear language. You will be given structured data about
a flagged position and a selected protective put option contract.

Write a short recommendation (4-6 sentences) that:
1. States which position is flagged and why (the risk).
2. Explains the recommended hedge in plain terms (what contract, how many, strike, expiration).
3. States the total cost in dollars and as a percentage of the position's value.
4. Briefly notes what this hedge does and doesn't protect against (e.g. protects below the
   strike price, doesn't cap upside since this is a plain put, not a collar).
5. IMPORTANT: if the hedge data includes a non-zero "over_hedged_shares" value, explicitly
   mention that the contracts cover more shares than are actually owned (since each option
   contract covers exactly 100 shares), and by how many shares. If over_hedged_shares is 0,
   don't mention this at all.

Do not use excessive jargon. Write as if explaining to someone who understands basic investing
but isn't an options expert. Do not just restate the raw numbers - explain what they mean.
"""


def compute_hedge_cost(shares_owned: float, put_contract: dict) -> dict:
    contracts_needed = math.ceil(shares_owned / 100)
    cost_per_contract = float(put_contract["close_price"]) * 100  # option premiums are quoted per share, contract = 100 shares
    total_cost = contracts_needed * cost_per_contract

    shares_covered = contracts_needed * 100
    over_hedged_shares = shares_covered - shares_owned

    return {
        "contracts_needed": contracts_needed,
        "cost_per_contract": round(cost_per_contract, 2),
        "total_cost": round(total_cost, 2),
        "shares_covered": shares_covered,
        "over_hedged_shares": over_hedged_shares,  # 0 if shares_owned is a clean multiple of 100
    }


def generate_recommendation(position: dict, put_contract: dict, hedge_cost: dict) -> str:
    position_value = position["market_value"]
    cost_pct_of_position = round((hedge_cost["total_cost"] / position_value) * 100, 2) if position_value else None

    user_content = f"""
Flagged position:
{position}

Selected put contract:
{put_contract}

Hedge cost:
{hedge_cost}

Cost as % of position value: {cost_pct_of_position}%
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,  
    )

    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    # --- Test data - replace with real output from steps 1-3 once wired together ---
    test_position = {
        "symbol": "AAPL",
        "qty": 250,
        "cost_basis": 35200.00,
        "market_value": 31992.00,
        "drawdown_pct": -9.10,
        "concentration_pct": 32.0,
    }

    test_put_contract = {
        "option_symbol": "AAPL261009P00305000",
        "strike_price": 305.0,
        "expiration_date": "2026-10-09",
        "days_to_expiry": 39,
        "close_price": "4.23",
        "open_interest": "9",
    }

    hedge_cost = compute_hedge_cost(test_position["qty"], test_put_contract)
    print("Hedge cost breakdown:", hedge_cost)

    recommendation = generate_recommendation(test_position, test_put_contract, hedge_cost)
    print("\n--- Recommendation ---\n")
    print(recommendation)