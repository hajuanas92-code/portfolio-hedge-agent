"""
Portfolio Hedging Agent - Streamlit app

Wraps the tested pipeline (steps 1-7) into an interactive UI:
  1. Fetch real positions from Alpaca (via MCP)
  2. Apply a user-typed risk rule (via LLM)
  3. Select a protective put for each flagged position (via MCP option data)
  4. Generate a plain-language recommendation (via LLM)
  5. Approve/Decline gate
  6. Execute the order (via MCP) if approved
  7. Log the attempt to hedge_log.json

Run:
    uv run streamlit run app.py
"""

import asyncio
import json
import os
import sys
import streamlit as st
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from position import get_positions_with_risk_metrics
from threshold import apply_threshold_rule
from select_put import get_current_price, select_protective_put
from run_pipeline import compute_hedge_cost, generate_recommendation
from execute import execute_protective_put
from log import log_hedge_attempt, LOG_FILE_PATH

load_dotenv()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") 
LOCAL_ALPACA_MCP_SERVER_DIR = os.getenv("LOCAL_ALPACA_MCP_SERVER_DIR", "")

st.set_page_config(page_title="Portfolio Hedging Agent", layout="wide")


def render_table(rows: list[dict]):
    """
    Renders a list of dicts as a markdown table, avoiding st.dataframe/st.table
    entirely since those depend on pyarrow, which is blocked by this machine's
    Windows security policy.
    """
    if not rows:
        st.caption("(empty)")
        return

    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")

    st.markdown("\n".join(lines))


def run_async(coro):
    """Streamlit callbacks are sync, but our pipeline functions are async - this bridges them."""
    return asyncio.run(coro)


async def _with_session(fn):
    """Opens a fresh MCP connection, runs fn(session), closes the connection."""
    if LOCAL_ALPACA_MCP_SERVER_DIR:
        # Local Windows dev: run from the cloned repo (avoids the Application Control block)
        server_params = StdioServerParameters(
            command="uv",
            args=["--directory", LOCAL_ALPACA_MCP_SERVER_DIR, "run", "alpaca-mcp-server"],
            env={"ALPACA_API_KEY": ALPACA_API_KEY, "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY},
        )
    else:
        # Deployed (Streamlit Cloud): use the installed package directly
        server_params = StdioServerParameters(
            command="alpaca-mcp-server",
            args=[],
            env={"ALPACA_API_KEY": ALPACA_API_KEY, "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY},
        )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


# --- Session state defaults ---
if "portfolio_value" not in st.session_state:
    st.session_state.portfolio_value = None
if "positions" not in st.session_state:
    st.session_state.positions = []
if "flagged" not in st.session_state:
    st.session_state.flagged = []
if "hedge_data" not in st.session_state:
    st.session_state.hedge_data = {}  # symbol -> {put_contract, hedge_cost, recommendation}
if "order_results" not in st.session_state:
    st.session_state.order_results = {}  # symbol -> last order result, shown after the rerun


st.title("Portfolio Hedging Agent")
st.caption("Reads your Alpaca positions, flags risk against a rule you set, and recommends protective options hedges.")

# --- Step 1: portfolio overview ---
col1, col2 = st.columns([1, 3])
with col1:
    if st.button("Refresh Portfolio", type="primary"):
        with st.spinner("Fetching positions..."):
            portfolio_value, positions = run_async(_with_session(get_positions_with_risk_metrics))
            st.session_state.portfolio_value = portfolio_value
            st.session_state.positions = positions
            st.session_state.flagged = []  # reset downstream state on refresh
            st.session_state.hedge_data = {}

if st.session_state.portfolio_value is not None:
    st.metric("Total Portfolio Value", f"${st.session_state.portfolio_value:,.2f}")

    if st.session_state.positions:
        render_table(st.session_state.positions)
    else:
        st.info("No open positions.")

st.divider()

# --- Step 2: risk rule ---
st.subheader("Set your risk rule")
rule_text = st.text_input("e.g. \"flag anything down more than 8%, or over 30% of my portfolio\"")

if st.button("Check Risk") and st.session_state.positions:
    with st.spinner("Evaluating positions against your rule..."):
        result = apply_threshold_rule(st.session_state.positions, rule_text)
        st.session_state.flagged = result.get("flagged", [])

if st.session_state.flagged:
    st.subheader("Flagged positions")
    for f in st.session_state.flagged:
        st.write(f"**{f['symbol']}** — {f['reason']}")
elif rule_text:
    st.caption("No positions flagged yet (or rule not checked).")

st.divider()

# --- Steps 3 & 4: hedge selection + recommendation, per flagged position ---
for f in st.session_state.flagged:
    symbol = f["symbol"]
    position = next((p for p in st.session_state.positions if p["symbol"] == symbol), None)
    if not position:
        continue

    st.subheader(f"Hedge for {symbol}")

    if symbol not in st.session_state.hedge_data:
        if st.button(f"Get hedge recommendation for {symbol}", key=f"get_rec_{symbol}"):
            with st.spinner(f"Selecting a protective put for {symbol}..."):
                async def _select(session):
                    price = await get_current_price(session, symbol)
                    return await select_protective_put(session, symbol, price)

                put_contract = run_async(_with_session(_select))

                if put_contract:
                    hedge_cost = compute_hedge_cost(float(position["qty"]), put_contract)
                    recommendation = generate_recommendation(position, put_contract, hedge_cost)
                    st.session_state.hedge_data[symbol] = {
                        "put_contract": put_contract,
                        "hedge_cost": hedge_cost,
                        "recommendation": recommendation,
                    }
                    st.rerun()
                else:
                    st.warning(f"No suitable put contract found for {symbol}.")

    if symbol in st.session_state.hedge_data:
        data = st.session_state.hedge_data[symbol]
        st.write(data["recommendation"])

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(f"Approve hedge for {symbol}", key=f"approve_{symbol}", type="primary"):
                with st.spinner("Placing order..."):
                    order_result = run_async(_with_session(
                        lambda session: execute_protective_put(
                            session, data["put_contract"]["option_symbol"], data["hedge_cost"]["contracts_needed"]
                        )
                    ))
                    log_hedge_attempt(symbol, f["reason"], data["put_contract"], data["hedge_cost"], order_result, approved=True)
                    st.session_state.order_results[symbol] = order_result
                    st.session_state.hedge_data.pop(symbol, None)  # prevent re-clicking and double-ordering
                    st.rerun()

        with col_b:
            if st.button(f"Decline hedge for {symbol}", key=f"decline_{symbol}"):
                log_hedge_attempt(symbol, f["reason"], data["put_contract"], data["hedge_cost"], order_result=None, approved=False)
                st.info(f"Declined hedge for {symbol}.")
                st.session_state.hedge_data.pop(symbol, None)  # clear stale recommendation from screen
                st.rerun()

st.divider()

# --- Persistent order result display (survives the rerun after Approve) ---
for symbol, order_result in st.session_state.order_results.items():
    st.subheader(f"Last order result: {symbol}")
    st.json(order_result)

st.divider()

# --- Step 7: hedge history ---
st.subheader("Hedge history")
if os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "r") as f:
        try:
            log = json.load(f)
        except json.JSONDecodeError:
            log = []
    if log:
        render_table(log)
    else:
        st.caption("No hedge attempts logged yet.")
else:
    st.caption("No hedge attempts logged yet.")