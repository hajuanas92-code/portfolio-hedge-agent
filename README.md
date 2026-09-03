# Portfolio Hedging Agent

An AI agent that watches your Alpaca portfolio, flags positions against a risk rule you define in plain English, and recommends (and can execute) protective options hedges — built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/event/alpaca-ai-trading-agents-hackathon) on lablab.ai.

## What it does

1. **Reads your real Alpaca positions** — current holdings, drawdown %, and portfolio concentration.
2. **Applies a risk rule you type in plain English** (e.g. *"flag anything down more than 8%, or over 30% of my portfolio"*) — an LLM reasons about your rule against the data, so it isn't limited to rigid preset thresholds.
3. **Selects a real protective put option contract** for any flagged position, using live option chain data — targeting a strike ~5% out-of-the-money and an expiration ~30-45 days out.
4. **Explains the recommendation in plain language** — what's at risk, what the hedge costs, and what it does and doesn't protect against.
5. **Waits for your explicit approval** before doing anything — nothing executes automatically.
6. **Places the real order** (paper trading) via Alpaca's Trading API if you approve.
7. **Logs every hedge attempt** to `hedge_log.json` for a running history of the agent's decisions.

## Architecture

- **Streamlit** — the UI, deployed on Streamlit Community Cloud.
- **Alpaca MCP Server** (`alpaca-mcp-server`) — the required integration point for all Alpaca data and trading actions, connected to as an MCP client directly from this app's own Python backend (not via a chat client like Claude Desktop).
- **Groq** (LLM, OpenAI-compatible API) — powers the plain-English risk rule interpretation and the natural-language hedge recommendations.

```
Streamlit UI  <-->  Python backend (MCP client)  <-->  alpaca-mcp-server  <-->  Alpaca Trading API
                            |
                            v
                      Groq LLM API (risk reasoning + recommendations)
```

## Setup

### 1. Clone and install dependencies

```bash
git clone <this-repo-url>
cd portfolio-hedge-agent
uv sync
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```dotenv
ALPACA_API_KEY=your_alpaca_paper_trading_key
ALPACA_SECRET_KEY=your_alpaca_paper_trading_secret
GROQ_API_KEY=your_groq_api_key

# Optional, for local development only - point this at a local clone of
# alpacahq/alpaca-mcp-server if you hit issues running the installed package directly.
# Leave unset for normal use / deployment.
LOCAL_ALPACA_MCP_SERVER_DIR=
```

Get your Alpaca paper trading keys from the [Alpaca dashboard](https://alpaca.markets). Get a free Groq API key from [console.groq.com](https://console.groq.com).

### 3. Run it

```bash
uv run streamlit run app.py
```

## Usage

1. Click **Refresh Portfolio** to load your real positions.
2. Type a risk rule in plain English and click **Check Risk**.
3. For any flagged position, click **Get hedge recommendation** to see a selected put contract and a plain-language explanation.
4. **Approve** to place the real (paper) order, or **Decline** to skip it.
5. Scroll down to see the full **Hedge History** log of past decisions.

## Disclaimer

This project trades exclusively on an **Alpaca paper trading account** (no real money). It is a hackathon project and educational demonstration, not financial advice. The hedge selection logic uses simple, transparent heuristics (fixed strike/expiration targeting) rather than sophisticated options pricing models.

## Built for

[Alpaca AI Trading Agents Hackathon](https://lablab.ai/event/alpaca-ai-trading-agents-hackathon) — lablab.ai, August-September 2026.
