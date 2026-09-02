import asyncio, os
import json
import math
from datetime import datetime, timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from groq import Groq
from dotenv import load_dotenv

from position import get_positions_with_risk_metrics
from threshold import apply_threshold_rule
from select_put import get_current_price, select_protective_put
from recommendation import compute_hedge_cost, generate_recommendation
from execute import execute_protective_put
from log import log_hedge_attempt

load_dotenv()

ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") 
# --- EDIT THESE ---
ALPACA_MCP_SERVER_DIR = r"C:\Users\anas\Desktop\Alpaca Agent\alpaca-mcp-server"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-20b"  

async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", ALPACA_MCP_SERVER_DIR, "run", "alpaca-mcp-server"],
        env={"ALPACA_API_KEY": ALPACA_API_KEY, "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Step 1: get real positions ---
            portfolio_value, positions = await get_positions_with_risk_metrics(session)
            print(f"Total portfolio value: ${portfolio_value:,.2f}")

            if not positions:
                print("(No real positions — injecting a fake test position for pipeline testing)")
                positions = [{
                    "symbol": "AAPL",
                    "qty": "1",
                    "cost_basis": 350.00,
                    "market_value": 319.92,
                    "drawdown_pct": -8.6,
                    "concentration_pct": 100.0,
                }]
                portfolio_value = 319.92

            for p in positions:
                print(f"  {p['symbol']}: drawdown={p['drawdown_pct']}%  concentration={p['concentration_pct']}%")

            # --- Step 2: apply threshold rule ---
            rule = input("\nType your risk rule (e.g. 'flag anything down more than 8%'): ")
            threshold_result = apply_threshold_rule(positions, rule)

            flagged = threshold_result.get("flagged", [])
            if not flagged:
                print("\nNo positions flagged under this rule. Nothing to hedge.")
                return

            print(f"\n{len(flagged)} position(s) flagged:")
            for f in flagged:
                print(f"  - {f['symbol']}: {f['reason']}")

            # --- Steps 3 & 4: for each flagged position, select a hedge and explain it ---
            for f in flagged:
                symbol = f["symbol"]
                position = next((p for p in positions if p["symbol"] == symbol), None)
                if not position:
                    continue

                print(f"\n--- Evaluating hedge for {symbol} ---")
                current_price = await get_current_price(session, symbol)
                put_contract = await select_protective_put(session, symbol, current_price)

                if not put_contract:
                    print(f"No suitable put contract found for {symbol}. Skipping.")
                    continue

                hedge_cost = compute_hedge_cost(float(position["qty"]), put_contract)
                recommendation = generate_recommendation(position, put_contract, hedge_cost)

                print("\n--- Recommendation ---")
                print(recommendation)

                # --- Step 5: approval gate ---
                approval = input(f"\nApprove this hedge for {symbol}? (yes/no): ").strip().lower()
                if approval in ("yes", "y"):
                    order_result = await execute_protective_put(session, put_contract["option_symbol"], hedge_cost["contracts_needed"])
                    print(f"\n[APPROVED] Order result:")
                    print(json.dumps(order_result, indent=2))
                    log_hedge_attempt(symbol, f["reason"], put_contract, hedge_cost, order_result, approved=True)
                else:
                    print(f"[DECLINED] Skipping hedge for {symbol}.")
                    log_hedge_attempt(symbol, f["reason"], put_contract, hedge_cost, order_result=None, approved=False)


if __name__ == "__main__":
    asyncio.run(main())