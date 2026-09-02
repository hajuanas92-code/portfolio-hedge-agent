"""
Step 1: Fetch clean position + portfolio data via alpaca-mcp-server.

For each position, this computes:
  - drawdown_pct: how far below cost basis the position currently is
                  (negative = loss, positive = gain)
  - concentration_pct: what % of your total portfolio value this position represents

These two numbers are exactly what the risk-threshold logic (step 2) will
compare against whatever rule the user types in chat later.

Run:
    uv run step1_positions.py
"""

import asyncio, os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv 

load_dotenv()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") 
# --- EDIT THESE ---
ALPACA_MCP_SERVER_DIR = r"C:\Users\anas\Desktop\Alpaca Agent\alpaca-mcp-server"

# -------------------


def _extract_text(tool_result):
    """MCP tool results come back as a list of content blocks; pull out the text."""
    for block in tool_result.content:
        if hasattr(block, "text"):
            return block.text
    return None


async def get_positions_with_risk_metrics(session: ClientSession):
    # 1. Get account info (for total portfolio value)
    account_raw = await session.call_tool("get_account_info", {})
    account_text = _extract_text(account_raw)
    account_envelope = json.loads(account_text) if account_text else {}
    account = account_envelope.get("data", {}).get("result", account_envelope.get("data", {}))
 
    portfolio_value = float(account.get("portfolio_value", 0))

    # 2. Get all positions
    positions_raw = await session.call_tool("get_all_positions", {})
    positions_text = _extract_text(positions_raw)
    positions_envelope = json.loads(positions_text) if positions_text else {}
    positions = positions_envelope.get("data", {}).get("result", [])

    enriched = []
    for pos in positions:
        symbol = pos.get("symbol")
        cost_basis = float(pos.get("cost_basis", 0))
        market_value = float(pos.get("market_value", 0))

        drawdown_pct = None
        if cost_basis != 0:
            drawdown_pct = ((market_value - cost_basis) / cost_basis) * 100

        concentration_pct = None
        if portfolio_value != 0:
            concentration_pct = (market_value / portfolio_value) * 100

        enriched.append({
            "symbol": symbol,
            "qty": pos.get("qty"),
            "cost_basis": cost_basis,
            "market_value": market_value,
            "drawdown_pct": round(drawdown_pct, 2) if drawdown_pct is not None else None,
            "concentration_pct": round(concentration_pct, 2) if concentration_pct is not None else None,
        })

    return portfolio_value, enriched


async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=[
            "--directory", ALPACA_MCP_SERVER_DIR,
            "run", "alpaca-mcp-server",
        ],
        env={
            "ALPACA_API_KEY": ALPACA_API_KEY,
            "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY,
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            portfolio_value, positions = await get_positions_with_risk_metrics(session)
            print(f"Total portfolio value: ${portfolio_value:,.2f}")

            # --- TEMPORARY TEST OVERRIDE: remove once a real position exists ---
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
# ---------------------------------------------------------------------


if __name__ == "__main__":
    asyncio.run(main())