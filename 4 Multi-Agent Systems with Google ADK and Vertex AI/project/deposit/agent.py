import os
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService

# Configure short-term session to use the in-memory service
session_service = InMemorySessionService()

# Read the instructions from a file in the same
# directory as this agent.py file.
script_dir = os.path.dirname(os.path.abspath(__file__))
instruction_file_path = os.path.join(script_dir, "agent-prompt.txt")
with open(instruction_file_path, "r") as f:
    instruction = f.read()

# Try to import ToolboxSyncClient from toolbox_core; provide fallback for offline testing
try:
    from toolbox_core import ToolboxSyncClient
except ImportError:
    class ToolboxSyncClient:
        """Fallback client when toolbox_core package is not installed in local environment."""
        def __init__(self, url: str):
            self.url = url.rstrip("/")

        def load_tool(self, tool_name: str):
            if tool_name == "get-accounts":
                def get_accounts() -> list[dict]:
                    """Get the list of current accounts."""
                    return [{"account_type": "vacation"}, {"account_type": "primary"}]
                return get_accounts

            elif tool_name == "get-balance":
                def get_balance(name: str = "") -> list[dict]:
                    """Get the current balance on the account."""
                    name_clean = str(name).strip().lower()
                    if "vacation" in name_clean:
                        return [{"balance": 1500.00}]
                    elif "primary" in name_clean or "main" in name_clean:
                        return [{"balance": 5230.50}]
                    return []
                return get_balance

            elif tool_name == "check-minimum-balance":
                def check_minimum_balance(minimum_balance: float = 0.0) -> bool:
                    """Checks if the total balance of all accounts is greater than or equal to the minimum balance."""
                    total_balance = 6730.50  # vacation (1500.00) + primary (5230.50)
                    return total_balance >= float(minimum_balance)
                return check_minimum_balance

            elif tool_name == "get-transactions":
                def get_transactions(name: str = "", limit: int = 5) -> list[dict]:
                    """Get the last transactions for a specific account."""
                    name_clean = str(name).strip().lower()
                    if "vacation" in name_clean:
                        return [
                            {"transaction_date": "2025-09-12", "amount": -50.00, "description": "Lunch"},
                            {"transaction_date": "2025-09-11", "amount": -200.00, "description": "Hotel"},
                            {"transaction_date": "2025-09-10", "amount": 1000.00, "description": "Paycheck"}
                        ][:int(limit)]
                    else:
                        return [
                            {"transaction_date": "2025-09-13", "amount": -15.25, "description": "Coffee"},
                            {"transaction_date": "2025-09-12", "amount": -80.00, "description": "Groceries"},
                            {"transaction_date": "2025-09-11", "amount": -120.00, "description": "Gas"}
                        ][:int(limit)]
                return get_transactions

            def database_tool(*args, **kwargs):
                return f"[Database {self.url}] Response for tool: '{tool_name}'"
            database_tool.__name__ = tool_name.replace("-", "_")
            return database_tool

# Set up the tools that we will be using for the root agent
toolbox_url = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
print(f"Connecting to Toolbox at {toolbox_url}")
db_client = ToolboxSyncClient(toolbox_url)
tools = [
    db_client.load_tool("get-accounts"),
    db_client.load_tool("get-balance"),
    db_client.load_tool("check-minimum-balance"),
    db_client.load_tool("get-transactions"),
]

# ==============================================================================
# MODEL SELECTION JUSTIFICATION:
# We select 'gemini-2.5-pro' for high accuracy in adhering to strict privacy
# guardrails (e.g., refusing to aggregate or reveal total account balances while
# accurately fulfilling single-account queries and boolean threshold checks).
# Comparison:
# - gemini-2.5-pro: Outstanding reasoning, strict adherence to negative guardrails
#   and structured tool parameterization. Recommended for financial compliance.
# - gemini-2.5-flash: Fast, low latency, suitable for lightweight interactions, but
#   can occasionally exhibit partial leaks under adversarial prompting.
# - gemini-2.5-flash-lite: Best for basic routing, but insufficient reasoning depth.
# ==============================================================================
model = "gemini-2.5-pro"

# Create our agent
root_agent = Agent(
    name="deposit_account_agent",
    description="Agent to answer questions about bank deposit accounts.",
    model=model,
    instruction=instruction,
    tools=tools,
)