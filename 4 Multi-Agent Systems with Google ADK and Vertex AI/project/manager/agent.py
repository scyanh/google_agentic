import logging
import os
from google.adk.agents import Agent

try:
    from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
except ImportError:
    from google.adk.agents import BaseAgent
    AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent.json"

    class RemoteA2aAgent(BaseAgent):
        """Fallback RemoteA2aAgent when a2a-sdk is not installed in local environment."""
        agent_card: str = ""

        def __init__(self, name: str, agent_card: str = "", **kwargs):
            super().__init__(name=name, **kwargs)
            self.agent_card = agent_card
            self.description = f"Remote A2A Agent {name}"

        async def _run_async_impl(self, ctx):
            if "deposit" in self.name:
                from deposit.agent import root_agent as target
            elif "loan" in self.name:
                from loan.agent import root_agent as target
            else:
                target = None
            if target:
                async for event in target.run_async(ctx):
                    yield event
from google.adk.sessions import InMemorySessionService

# Configure short-term session to use the in-memory service
session_service = InMemorySessionService()

# Read the instructions from a file in the same
# directory as this agent.py file.
script_dir = os.path.dirname(os.path.abspath(__file__))
instruction_file_path = os.path.join(script_dir, "agent-prompt.txt")
with open(instruction_file_path, "r") as f:
    instruction = f.read()

# Set up the tools that we will be using for the root agent
tools = []

# Set up remote agents that we can delegate to via A2A
deposit_base_url = os.environ.get("DEPOSIT_A2A_URL", "http://localhost:8000/a2a/deposit")
loan_base_url = os.environ.get("LOAN_A2A_URL", "http://localhost:8000/a2a/loan")

deposit_agent = RemoteA2aAgent(
    name="deposit_agent",
    agent_card=f"{deposit_base_url}{AGENT_CARD_WELL_KNOWN_PATH}",
)

loan_agent = RemoteA2aAgent(
    name="loan_agent",
    agent_card=f"{loan_base_url}{AGENT_CARD_WELL_KNOWN_PATH}",
)

sub_agents = [
    deposit_agent,
    loan_agent,
]

# ==============================================================================
# MODEL SELECTION JUSTIFICATION:
# We select 'gemini-2.5-flash' for the manager agent because front-desk routing
# and triage requires minimal latency, fast conversational turns, and reliable
# tool/sub-agent invocation according to user intent.
# Comparison:
# - gemini-2.5-flash: Extremely responsive, excellent classification of domain queries
#   (deposit vs. loan vs. general bank info), highly cost-effective for high-frequency gateway.
# - gemini-2.5-pro: Over-provisioned for routing-only tasks; adds unnecessary latency.
# - gemini-2.5-flash-lite: Adequate for strict routing, but flash provides smoother
#   general conversational replies for bank FAQ queries.
# ==============================================================================
model = "gemini-2.5-flash"

# Create our agent
root_agent = Agent(
    name="bank_agent",
    description="Central bank management agent.",
    model=model,
    instruction=instruction,
    tools=tools,
    sub_agents=sub_agents,
)
