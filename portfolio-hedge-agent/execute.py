"""
Step 6: Execute the protective put order.

Takes the selected put contract (from step 3) and the number of contracts
needed (from step 4's hedge cost calculation), and places a real market
order to buy those puts, opening a new long put position.

This function is meant to be called AFTER the approval gate (step 5) -
only when the user has explicitly typed "yes".

Run standalone for testing:
    uv run step6_execute.py
(will prompt for a symbol/contract/qty to test with)
"""

import asyncio, os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()

# --- EDIT THESE ---
ALPACA_MCP_SERVER_DIR = r"C:\Users\anas\Desktop\Alpaca Agent\alpaca-mcp-server"
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
# -------------------


def _extract_text(tool_result):
    for block in tool_result.content:
        if hasattr(block, "text"):
            return block.text
    return None


async def execute_protective_put(session: ClientSession, option_symbol: str, contracts_needed: int) -> dict:
    """
    Places a market order to buy `contracts_needed` put contracts, opening
    a new long put position (buy_to_open).
    """
    raw = await session.call_tool("place_option_order", {
        "symbol": option_symbol,
        "qty": str(contracts_needed),
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "position_intent": "buy_to_open",
    })
    text = _extract_text(raw)
    envelope = json.loads(text) if text else {}
    return envelope


async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", ALPACA_MCP_SERVER_DIR, "run", "alpaca-mcp-server"],
        env={"ALPACA_API_KEY": ALPACA_API_KEY, "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY},
    )

    option_symbol = input("Option contract symbol to buy (e.g. AAPL261009P00305000): ").strip()
    contracts_needed = int(input("How many contracts? (e.g. 1): ").strip())

    confirm = input(f"\nAbout to BUY {contracts_needed}x {option_symbol} at market. Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await execute_protective_put(session, option_symbol, contracts_needed)

            print("\n--- Order result ---")
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())