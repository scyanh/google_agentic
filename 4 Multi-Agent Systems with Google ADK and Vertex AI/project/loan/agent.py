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

# Import the loan info tool and the complete loan approval sub-agent
try:
    from .loan import loan_approval_agent, loan_info_tool
except (ImportError, ValueError):
    from loan import loan_approval_agent, loan_info_tool

# Set up the tools that we will be using for the root agent
tools = [
    loan_info_tool,
]

# Set up sub-agents for specialized workflows (Loan Approval Pipeline)
sub_agents = [
    loan_approval_agent,
]

# ==============================================================================
# MODEL SELECTION JUSTIFICATION:
# We use 'gemini-2.5-pro' for the loan account root agent to ensure sophisticated
# multi-step conversational reasoning, accurate classification of customer loan
# intent (differentiating between balance inquiries and new loan requests), and
# strict compliance with financial communication standards.
# Comparison:
# - gemini-2.5-pro: Optimal reasoning for loan terms synthesis, repayment schedules,
#   and delegation routing to the approval pipeline.
# - gemini-2.5-flash: Fast, but may prematurely answer loan approval queries without
#   delegating to the formal approval sub-agent pipeline.
# - gemini-2.5-flash-lite: Lightweight, suitable for sub-agent text extraction tasks.
# ==============================================================================
model = "gemini-2.5-pro"

# Create our root loan agent
root_agent = Agent(
    name="loan_account_agent",
    description="Agent to answer questions about bank loan accounts.",
    model=model,
    instruction=instruction,
    tools=tools,
    sub_agents=sub_agents,
)