import os
from datetime import datetime
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService

# Automatically load environment variables from .env
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

# Import custom tools defined in separate module files
try:
    from .datastore import datastore_search_tool
    from .search_agent import search_agent_tool
except (ImportError, ValueError):
    from datastore import datastore_search_tool
    from search_agent import search_agent_tool

# ==============================================================================
# SESSION STORAGE CONFIGURATION:
# In-memory session service manages multi-turn conversational state across all agents.
# ==============================================================================
session_service = InMemorySessionService()

# Products catalog from betty_db.sql for reliable query matching and offline fallback
PRODUCTS_CATALOG = [
    {"product_name": "Bird Seed Mix", "price": 15.99},
    {"product_name": "Premium Parakeet Seed", "price": 14.99},
    {"product_name": "Sunflower Seeds", "price": 22.50},
    {"product_name": "Suet Cakes", "price": 12.75},
    {"product_name": "Bird Feeder", "price": 25.00},
    {"product_name": "Bluebird House", "price": 35.50},
    {"product_name": "Bird Bath", "price": 75.99},
    {"product_name": "Cuttlebone", "price": 4.25},
    {"product_name": "Millet", "price": 8.00},
    {"product_name": "Parrot Pellets", "price": 28.99},
    {"product_name": "Finch & Canary Food", "price": 10.50},
]

def _search_product_catalog(product_name: str = ""):
    """Helper to search the product inventory with exact and fuzzy term matching."""
    q = product_name.lower().strip()
    matches = [p for p in PRODUCTS_CATALOG if q in p["product_name"].lower()]
    if not matches:
        words = [w for w in q.split() if len(w) > 3]
        for w in words:
            sub_m = [p for p in PRODUCTS_CATALOG if w in p["product_name"].lower()]
            if sub_m:
                matches = sub_m
                break
    if matches:
        return matches
    return f"Product '{product_name}' was not found in the inventory database."

# Try to import ToolboxSyncClient from toolbox_core; provide mock fallback for offline local testing
try:
    from toolbox_core import ToolboxSyncClient
except ImportError:
    class ToolboxSyncClient:
        """Fallback client when toolbox_core package is not yet installed in host environment."""
        def __init__(self, url: str):
            self.url = url.rstrip("/")
        def load_tool(self, tool_name: str):
            if "price" in tool_name:
                def get_product_price(product_name: str = ""):
                    """Queries the product database to find the price and name of items matching the product search term."""
                    return _search_product_catalog(product_name)
                get_product_price.__name__ = "get_product_price"
                get_product_price.__doc__ = "Queries product pricing from database."
                return get_product_price
            elif "list" in tool_name:
                def list_products():
                    """Retrieves the complete list of all products and prices currently offered."""
                    return PRODUCTS_CATALOG
                list_products.__name__ = "list_products"
                list_products.__doc__ = "Lists all available products and prices."
                return list_products
            raise ValueError(f"Unknown tool: {tool_name}")

# MCP Database Toolbox Integration
toolbox_url = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
db_client = ToolboxSyncClient(toolbox_url)

try:
    product_price_tool = db_client.load_tool("get_product_price")
except Exception:
    try:
        product_price_tool = db_client.load_tool("get-product-price")
    except Exception:
        def get_product_price(product_name: str = ""):
            """Queries the product database to find the price and name of items matching the product search term."""
            return _search_product_catalog(product_name)
        product_price_tool = get_product_price

try:
    list_products_tool = db_client.load_tool("list_products")
except Exception:
    try:
        list_products_tool = db_client.load_tool("list-products")
    except Exception:
        def list_products():
            """Retrieves the complete list of all products and prices currently offered."""
            return PRODUCTS_CATALOG
        list_products_tool = list_products

product_price_tool.__name__ = "get_product_price"
list_products_tool.__name__ = "list_products"


def get_current_date_and_day() -> str:
    """Returns the current date, day of the week, and local time.

    Use this tool to determine today's day of the week (e.g., Monday, Thursday, Sunday)
    when customers ask relative time questions such as 'Are you open today?',
    'What time do you close tonight?', or 'Are you open tomorrow?'.
    """
    now = datetime.now()
    return now.strftime("Today is %A, %B %d, %Y. Current time: %I:%M %p.")


# ==============================================================================
# MODEL CONFIGURATION
# ==============================================================================
model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Load instructions from prompts directory
script_dir = os.path.dirname(os.path.abspath(__file__))
prompts_dir = os.path.join(script_dir, "prompts")

def _read_prompt(name: str, fallback_file: str = None) -> str:
    path = os.path.join(prompts_dir, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    if fallback_file and os.path.exists(fallback_file):
        with open(fallback_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""

concierge_instruction = _read_prompt("concierge_prompt.txt", os.path.join(script_dir, "agent-prompt.txt"))
avian_instruction = _read_prompt("avian_prompt.txt", os.path.join(script_dir, "search-prompt.txt"))
inventory_instruction = _read_prompt("inventory_prompt.txt")
store_instruction = _read_prompt("store_prompt.txt")

# ==============================================================================
# SPECIALIST SUB-AGENTS (The Flock of Experts)
# ==============================================================================

# 1. Chloe: Avian Health, Species Care, and Nutrition Specialist
avian_specialist = Agent(
    name="avian_specialist",
    description=(
        "Chloe, our resident ornithologist and avian care specialist. Consult Chloe for any "
        "questions regarding bird species, avian health, behavior, dietary needs, cage enrichment, "
        "and safe or toxic foods."
    ),
    instruction=avian_instruction,
    model=model,
    tools=[datastore_search_tool, search_agent_tool],
)

# 2. David: Inventory & Product Catalog Specialist
inventory_specialist = Agent(
    name="inventory_specialist",
    description=(
        "David, head of inventory. Consult David for product pricing, availability, and catalog "
        "items including seeds, pellets, cages, feeders, cuttlebone, and accessories from our SQL database."
    ),
    instruction=inventory_instruction,
    model=model,
    tools=[product_price_tool, list_products_tool],
)

# 3. James: Boutique Owner, Store History, & Operating Hours Specialist
store_specialist = Agent(
    name="store_specialist",
    description=(
        "James, the owner of Betty's Bird Boutique. Consult James for store operating hours, "
        "visiting the physical boutique, the founding history of Betty and Bob Winger, the store team, "
        "and our mascot Leo the Moluccan cockatoo."
    ),
    instruction=store_instruction,
    model=model,
    tools=[datastore_search_tool, get_current_date_and_day],
)

# ==============================================================================
# ROOT / CONCIERGE AGENT
# Central Host coordinating customer greetings and seamless specialist delegation
# ==============================================================================
root_agent = Agent(
    name="bettys_bird_boutique_concierge",
    description=(
        "Warm, welcoming host at Betty's Bird Boutique. Welcomes customers, handles general greetings, "
        "and routes inquiries to Chloe (avian specialist), David (inventory specialist), or James (store owner)."
    ),
    instruction=concierge_instruction,
    model=model,
    tools=[get_current_date_and_day],
    sub_agents=[avian_specialist, inventory_specialist, store_specialist],
)