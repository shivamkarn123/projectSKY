"""
One-off setup helper (run locally, NOT part of the deployed agent).

monday.com's simplest, most reliable path for importing a CSV into a new board is the
native importer in the UI (Board -> ... -> Import data -> Excel/CSV), which auto-detects
column types. That's the recommended path — do it manually first:

  1. In monday.com, create board "Deals" and import Deal_funnel_Data.xlsx.
  2. Create board "Work Orders" and import Work_Order_Tracker_Data.xlsx.
  3. Set column types sensibly: Status/Dropdown for status-like columns (Deal Status,
     Deal Stage, Execution Status, Invoice Status...), Date for date columns, Numbers for
     money/quantity columns. Leave everything else as Text.
  4. Open each board, copy its Board ID from the URL (monday.com/boards/<BOARD_ID>).
  5. Create a personal API token: avatar -> Admin -> API, or Profile -> Developers ->
     My Access Tokens. Use a token scoped read-only if your plan supports it.
  6. Put the token + both board IDs into backend/.env (see .env.example).

This script is only a fallback/verification helper: it re-checks that the columns monday.com
ended up with roughly match what the agent's normalization layer expects, by pulling one page
of items and printing the column titles it sees. Run it AFTER the manual import above.
"""

import sys
import json

sys.path.insert(0, ".")
import config
from monday_client import fetch_board_items


def main():
    config.require_config()

    print("Fetching Deals board columns...")
    deals = fetch_board_items(config.MONDAY_DEALS_BOARD_ID)
    if deals:
        print(json.dumps(list(deals[0].keys()), indent=2))
    else:
        print("No items found — did the import work?")

    print("\nFetching Work Orders board columns...")
    wos = fetch_board_items(config.MONDAY_WORK_ORDERS_BOARD_ID)
    if wos:
        print(json.dumps(list(wos[0].keys()), indent=2))
    else:
        print("No items found — did the import work?")


if __name__ == "__main__":
    main()
