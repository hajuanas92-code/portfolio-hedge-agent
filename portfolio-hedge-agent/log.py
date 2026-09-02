"""
Step 7: Log every hedge attempt to a local JSON file.

Called after step 6's execution result comes back - logs regardless of
whether the order succeeded or was rejected, since both are useful
evidence ("the agent works" / "the agent correctly respects market rules").

This is meant to be imported into run_pipeline.py, not run standalone.
"""

import json
import os
from datetime import datetime, timezone

LOG_FILE_PATH = "hedge_log.json"


def log_hedge_attempt(symbol: str, flag_reason: str, put_contract: dict,
                       hedge_cost: dict, order_result: dict, approved: bool):
    """
    Appends one entry to hedge_log.json. Creates the file if it doesn't exist yet.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "flag_reason": flag_reason,
        "option_symbol": put_contract.get("option_symbol"),
        "strike_price": put_contract.get("strike_price"),
        "expiration_date": put_contract.get("expiration_date"),
        "contracts": hedge_cost.get("contracts_needed"),
        "total_cost": hedge_cost.get("total_cost"),
        "approved": approved,
        "order_result": order_result if approved else None,
    }

    # Load existing log, or start a new list if the file doesn't exist yet
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "r") as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []  # handles an empty or corrupted file gracefully
    else:
        log = []

    log.append(entry)

    with open(LOG_FILE_PATH, "w") as f:
        json.dump(log, f, indent=2)

    return entry