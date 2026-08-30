import os
from dotenv import load_dotenv

load_dotenv()

# Mock mode: when enabled, the system uses mock data instead of real API credentials
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

MONDAY_API_TOKEN = os.getenv("MONDAY_API_TOKEN", "")
MONDAY_DEALS_BOARD_ID = os.getenv("MONDAY_DEALS_BOARD_ID", "1234567890")
MONDAY_WORK_ORDERS_BOARD_ID = os.getenv("MONDAY_WORK_ORDERS_BOARD_ID", "0987654321")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# How long fetched board data stays cached in memory before we re-hit the monday.com API.
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "120"))

MONDAY_API_URL = "https://api.monday.com/v2"


def require_config():
    """Check if required config is available. In mock mode, only ANTHROPIC_API_KEY is required.
    In real mode, all API credentials are required."""
    if MOCK_MODE:
        # In mock mode, we don't need real credentials
        return
    
    missing = [
        name
        for name, val in [
            ("MONDAY_API_TOKEN", MONDAY_API_TOKEN),
            ("MONDAY_DEALS_BOARD_ID", MONDAY_DEALS_BOARD_ID),
            ("MONDAY_WORK_ORDERS_BOARD_ID", MONDAY_WORK_ORDERS_BOARD_ID),
            ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill these in, or set MOCK_MODE=false to use mock data."
        )
