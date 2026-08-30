"""
Read-only monday.com GraphQL client.

Design notes:
- monday.com paginates board items (max 100/page via `items_page`), so we loop with cursors.
- column_values come back as a list of {id, text, value} — `text` is the human-readable
  rendering, which is what we want for BI purposes (dates as strings, numbers as strings, etc).
- We never write to monday.com. Every query here is read-only by construction (no mutations).
- Failures are raised as MondayAPIError with a message safe to surface to the agent/user,
  so the agent can say "I couldn't reach monday.com right now" instead of hallucinating data.
"""

import time
import httpx

from config import MONDAY_API_TOKEN, MONDAY_API_URL


class MondayAPIError(Exception):
    pass


_ITEMS_QUERY = """
query ($boardId: [ID!], $cursor: String) {
  boards(ids: $boardId) {
    id
    name
    items_page(limit: 100, cursor: $cursor) {
      cursor
      items {
        id
        name
        column_values {
          id
          column {
            title
          }
          text
          value
        }
      }
    }
  }
}
"""


def _post(query: str, variables: dict, retries: int = 3) -> dict:
    headers = {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }
    last_err = None
    for attempt in range(retries):
        try:
            resp = httpx.post(
                MONDAY_API_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30,
            )
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
            continue

        if resp.status_code == 429:
            # rate limited — back off and retry
            time.sleep(2 * (attempt + 1))
            continue

        if resp.status_code != 200:
            raise MondayAPIError(
                f"monday.com API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        payload = resp.json()
        if "errors" in payload:
            raise MondayAPIError(f"monday.com API error: {payload['errors']}")

        return payload["data"]

    raise MondayAPIError(f"monday.com API unreachable after {retries} retries: {last_err}")


def fetch_board_items(board_id: str) -> list[dict]:
    """Return every item on a board as a flat list of dicts:
    { "_item_id": ..., "_item_name": ..., "<Column Title>": "<text value>", ... }
    """
    if not board_id:
        raise MondayAPIError("No board id configured.")

    items: list[dict] = []
    cursor = None

    while True:
        data = _post(_ITEMS_QUERY, {"boardId": [board_id], "cursor": cursor})
        boards = data.get("boards") or []
        if not boards:
            raise MondayAPIError(f"Board {board_id} not found or not accessible with this token.")

        page = boards[0]["items_page"]
        for item in page["items"]:
            row = {"_item_id": item["id"], "_item_name": item["name"]}
            for cv in item["column_values"]:
                title = cv["column"]["title"]
                row[title] = cv["text"]
            items.append(row)

        cursor = page.get("cursor")
        if not cursor:
            break

    return items
