"""
Step 3: For a flagged position, select a protective put option contract.

Logic:
  1. Get the current market price of the underlying stock.
  2. Target strike = ~5% below current price (a common "how far below
     current price should my insurance kick in" convention).
  3. Target expiration = ~30-45 days out (long enough to matter, short
     enough that you're not overpaying for time you don't need).
  4. Pull the option chain for puts on that symbol, then pick the contract
     whose strike and expiration are closest to those targets.

"""

import asyncio,os
import json
from datetime import datetime, timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()
# --- EDIT THESE ---
ALPACA_MCP_SERVER_DIR = os.getenv("LOCAL_ALPACA_MCP_SERVER_DIR","") 
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
# -------------------

TARGET_STRIKE_PCT_BELOW = 0.05   # 5% below current price
TARGET_DAYS_TO_EXPIRY = 37       # aim for the middle of the 30-45 day window
EXPIRY_WINDOW_DAYS = (25, 50)    # acceptable range around the target


def _extract_text(tool_result):
    for block in tool_result.content:
        if hasattr(block, "text"):
            return block.text
    return None


def _unwrap(envelope: dict):
    """Handles both shapes we've seen: {'data': {'result': X}} and {'data': X}."""
    data = envelope.get("data", {})
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


async def get_current_price(session: ClientSession, symbol: str) -> float:
    raw = await session.call_tool("get_stock_latest_trade", {"symbols": symbol})
    text = _extract_text(raw)
    envelope = json.loads(text) if text else {}
    result = _unwrap(envelope)
    trades = result.get("trades", result)  # unwrap the extra "trades" layer

    return float(trades[symbol]["p"])


def _parse_occ_option_symbol(option_symbol: str):
    """
    Parses a standard OCC option symbol, e.g. 'AAPL260918P00300000':
      - last 8 chars: strike price * 1000 (so 00300000 -> $300.00)
      - char before that: 'C' or 'P'
      - 6 chars before that: expiration date as YYMMDD
      - everything before that: underlying root symbol
    """
    strike_str = option_symbol[-8:]
    opt_type = option_symbol[-9]
    date_str = option_symbol[-15:-9]

    strike_price = int(strike_str) / 1000.0
    expiration_date = datetime.strptime(date_str, "%y%m%d").date()

    return {
        "strike_price": strike_price,
        "option_type": "put" if opt_type == "P" else "call",
        "expiration_date": expiration_date,
    }


async def select_protective_put(session: ClientSession, symbol: str, current_price: float):
    target_strike = round(current_price * (1 - TARGET_STRIKE_PCT_BELOW), 2)
    today = datetime.now().date()
    min_days, max_days = EXPIRY_WINDOW_DAYS

    exp_gte = (today + timedelta(days=min_days)).isoformat()
    exp_lte = (today + timedelta(days=max_days)).isoformat()

    raw = await session.call_tool("get_option_contracts", {
        "underlying_symbols": symbol,
        "type": "put",
        "expiration_date_gte": exp_gte,
        "expiration_date_lte": exp_lte,
        "strike_price_gte": round(target_strike * 0.85, 2),
        "strike_price_lte": round(target_strike * 1.15, 2),
    })
    text = _extract_text(raw)
    envelope = json.loads(text) if text else {}
    contracts = envelope.get("data", {}).get("option_contracts", [])

    if not contracts:
        print(f"No put contracts found for {symbol} in the {min_days}-{max_days} day window near strike ${target_strike}.")
        return None

    candidates = []
    for c in contracts:
        strike_price = float(c["strike_price"])
        exp_date = datetime.strptime(c["expiration_date"], "%Y-%m-%d").date()
        days_to_expiry = (exp_date - today).days

        strike_diff = abs(strike_price - target_strike)
        days_diff = abs(days_to_expiry - TARGET_DAYS_TO_EXPIRY)
        score = strike_diff + (days_diff * 0.1)

        candidates.append((score, c, days_to_expiry))

    candidates.sort(key=lambda x: x[0])
    _, best, days_to_expiry = candidates[0]

    return {
        "option_symbol": best["symbol"],
        "strike_price": float(best["strike_price"]),
        "expiration_date": best["expiration_date"],
        "days_to_expiry": days_to_expiry,
        "close_price": best.get("close_price"),  # last traded price - a rough cost estimate
        "open_interest": best.get("open_interest"),
    }


async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", ALPACA_MCP_SERVER_DIR, "run", "alpaca-mcp-server"],
        env={"ALPACA_API_KEY": ALPACA_API_KEY, "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY},
    )

    symbol = input("Which symbol do you want a protective put for? (e.g. AAPL): ").strip().upper()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            current_price = await get_current_price(session, symbol)
            print(f"\nCurrent price of {symbol}: ${current_price:.2f}")

            put = await select_protective_put(session, symbol, current_price)

            if put:
                print("\nSelected protective put:")
                print(json.dumps(put, indent=2))
            else:
                print("\nNo suitable put contract found.")


if __name__ == "__main__":
    asyncio.run(main())