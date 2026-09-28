import logging
import os
from typing import AsyncGenerator, Literal

from google.adk.agents import BaseAgent, InvocationContext, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.events import Event, EventActions

try:
    from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
except ImportError:
    AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent.json"

    class RemoteA2aAgent(BaseAgent):
        """Fallback RemoteA2aAgent when a2a-sdk is not installed in local environment."""
        agent_card: str = ""

        def __init__(self, name: str, agent_card: str = "", **kwargs):
            super().__init__(name=name, **kwargs)
            self.agent_card = agent_card
            self.description = f"Remote A2A Agent {name}"

        async def _run_async_impl(self, ctx):
            min_equity = ctx.session.state.get("min_equity", 0.0)
            result = 6730.50 >= float(min_equity)
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=str(result).lower())])
            )
from google.adk.tools.agent_tool import AgentTool
from google.genai.types import Content, Part
from pydantic import BaseModel, Field

# Try to import ToolboxSyncClient from toolbox_core; provide fallback for offline testing
try:
    from toolbox_core import ToolboxSyncClient
except ImportError:
    class ToolboxSyncClient:
        """Fallback client when toolbox_core package is not installed in local environment."""
        def __init__(self, url: str):
            self.url = url.rstrip("/")

        def load_tool(self, tool_name: str):
            if tool_name == "get-loan-info":
                def get_loan_info(name: str = "") -> list[dict]:
                    """Get loan information for the loan account requested."""
                    name_clean = str(name).strip().lower()
                    if "personal" in name_clean:
                        return [{
                            "origination_date": "2024-05-20",
                            "amount": 15000.00,
                            "outstanding_balance": 10159.25,
                            "terms": 48,
                            "monthly_payment": 359.19,
                            "next_payment_date": "2025-10-15"
                        }]
                    else:
                        return [{
                            "origination_date": "2023-01-15",
                            "amount": 25000.00,
                            "outstanding_balance": 12024.04,
                            "terms": 60,
                            "monthly_payment": 471.78,
                            "next_payment_date": "2025-10-01"
                        }]
                return get_loan_info

            elif tool_name == "get-total-outstanding-balance":
                def get_total_outstanding_balance() -> dict:
                    """Get the total outstanding balance of all loans for a customer."""
                    return {"total_balance": 22183.29}
                return get_total_outstanding_balance

            def database_tool(*args, **kwargs):
                return f"[Database {self.url}] Response for tool: '{tool_name}'"
            database_tool.__name__ = tool_name.replace("-", "_")
            return database_tool

logger = logging.getLogger("google_adk.loan")


def load_instructions(prompt_file: str) -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    instruction_file_path = os.path.join(script_dir, prompt_file)
    with open(instruction_file_path, "r") as f:
        return f.read()


# Initialize Toolbox client and load tools
toolbox_url = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")
print(f"Connecting to Toolbox at {toolbox_url}")
db_client = ToolboxSyncClient(toolbox_url)
loan_info_tool = db_client.load_tool("get-loan-info")
outstanding_balance_tool = db_client.load_tool("get-total-outstanding-balance")


# ==============================================================================
# SUB-AGENT 1: Extract Loan Request Details (Amount and Type)
# ==============================================================================
class LoanRequest(BaseModel):
    amount: int | float = Field(description="The amount of the loan requested.")
    loan_type: Literal["auto", "rv", "home improvement", "personal"] = Field(
        description="The type of loan."
    )


loan_approval_get_requested_value_agent = LlmAgent(
    name="loan_approval_get_requested_value_agent",
    description="Get how much the user has requested for their loan and what type of loan they are requesting.",
    model="gemini-2.5-flash-lite",
    instruction=load_instructions("loan-request-prompt.txt"),
    output_schema=LoanRequest,
    output_key="requested",
)


# ==============================================================================
# SUB-AGENT 2: Get Total Outstanding Loan Balance
# ==============================================================================
class OutstandingBalance(BaseModel):
    total: float = Field(description="The total balance of outstanding loans.")


loan_approval_get_outstanding_balance_agent = LlmAgent(
    name="loan_approval_get_outstanding_balance_agent",
    description="Get the current outstanding balance the user has on their loans.",
    model="gemini-2.5-flash",
    instruction=load_instructions("outstanding-balance-prompt.txt"),
    output_schema=OutstandingBalance,
    output_key="outstanding_balance",
    tools=[outstanding_balance_tool],
)


# Orchestrator 1: Sequentially collect customer request and current loan debt
loan_approval_data_agent = SequentialAgent(
    name="loan_approval_data_agent",
    sub_agents=[
        loan_approval_get_requested_value_agent,
        loan_approval_get_outstanding_balance_agent,
    ],
)


# Helper function to locate local PDF files
def _find_pdf(filename: str) -> str | None:
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", filename),
        os.path.join(os.getcwd(), "docs", filename),
        os.path.join(os.getcwd(), "project", "starter", "docs", filename),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None


def _load_pdf_part(gcs_uri: str, filename: str) -> Part:
    """Load PDF part using GCS URI if bucket is configured; otherwise fallback to local PDF bytes."""
    custom_bucket = os.environ.get("GCS_BUCKET", "bank-info-flow-eed16")
    if custom_bucket and custom_bucket != "example-bank-info":
        return Part.from_uri(file_uri=gcs_uri, mime_type="application/pdf")
    local_path = _find_pdf(filename)
    if local_path and os.path.exists(local_path):
        try:
            with open(local_path, "rb") as f:
                return Part.from_bytes(data=f.read(), mime_type="application/pdf")
        except Exception as e:
            logger.warning(f"Could not read local PDF {local_path}: {e}")
    return Part.from_uri(file_uri=gcs_uri, mime_type="application/pdf")


# ==============================================================================
# SUB-AGENT 3: Load Loan Policy Guidelines from Google Cloud Storage
# Configured via environment variable GCS_BUCKET
# ==============================================================================
gcs_bucket = os.environ.get("GCS_BUCKET", "bank-info-flow-eed16")
policy_static_instruction_uri = f"gs://{gcs_bucket}/loan-policy.pdf"

policy_static_instruction = [
    Part(
        text="Please act as a loan officer. Your only task is to look at the attached loan policy and extract the loan approval criteria."
    ),
    _load_pdf_part(policy_static_instruction_uri, "loan-policy.pdf"),
]

CustomerRating = Literal["excellent", "great", "good", "fair", "poor"]


class Policy(BaseModel):
    debt_equity_ratio: int = Field(description="Required debt-to-equity ratio.")
    minimum_rating: CustomerRating = Field(description="The minimum customer rating required.")


loan_approval_policy_agent = LlmAgent(
    name="loan_approval_policy_agent",
    description="Given a pdf file with the current loan policy, and previous information about the customer's request, get the criteria to be used to evaluate a loan.",
    model="gemini-2.5-flash",
    static_instruction=Content(parts=policy_static_instruction),
    output_schema=Policy,
    output_key="policy",
)


# ==============================================================================
# SUB-AGENT 4: Custom Deterministic Equity Calculator (BaseAgent)
# Eliminates LLM math hallucination risks by computing:
# total_loans = outstanding_balance + requested_amount
# min_equity = total_loans / debt_equity_ratio
# ==============================================================================
class TotalValueAgent(BaseAgent):
    """Custom Agent performing exact arithmetic calculation of required equity."""

    def __init__(self, name: str = "loan_approval_get_total_value_agent"):
        super().__init__(name=name)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        requested = ctx.session.state.get("requested", {"amount": 0, "loan_type": "personal"})
        outstanding_balance = ctx.session.state.get("outstanding_balance", {"total": 0.0})
        policy = ctx.session.state.get("policy", {"debt_equity_ratio": 4, "minimum_rating": "fair"})

        logger.info(f"Requested: {requested}")
        logger.info(f"Outstanding Balance: {outstanding_balance}")
        logger.info(f"Policy: {policy}")

        req_amount = requested.get("amount", 0) if isinstance(requested, dict) else getattr(requested, "amount", 0)
        out_total = outstanding_balance.get("total", 0.0) if isinstance(outstanding_balance, dict) else getattr(outstanding_balance, "total", 0.0)
        ratio = policy.get("debt_equity_ratio", 4) if isinstance(policy, dict) else getattr(policy, "debt_equity_ratio", 4)
        if ratio <= 0:
            ratio = 1

        total_loans = float(out_total) + float(req_amount)
        min_equity = round(total_loans / ratio, 2)

        total_value = {
            "current_loans": outstanding_balance,
            "total_loans": total_loans,
            "min_equity": min_equity,
        }
        state_delta = {
            "total_value": total_value,
            "min_equity": min_equity,
        }
        actions = EventActions(state_delta=state_delta)
        yield Event(
            author=self.name,
            content=Content(
                parts=[
                    Part(
                        text=f"Is the total balance of all my deposit accounts greater than {min_equity}?"
                    )
                ]
            ),
            actions=actions,
        )


loan_approval_get_total_value_agent = TotalValueAgent(
    name="loan_approval_get_total_value_agent"
)


# ==============================================================================
# SUB-AGENT 5: Cross-Agent Communication via A2A with Deposit Agent
# Calls the deposit agent's 'check-minimum-balance' tool via A2A protocol
# ==============================================================================
deposit_server_url = os.environ.get("DEPOSIT_A2A_URL", "http://localhost:8000/a2a/deposit")
deposit_equity_agent = RemoteA2aAgent(
    name="deposit_equity_agent",
    agent_card=f"{deposit_server_url}{AGENT_CARD_WELL_KNOWN_PATH}",
)


class CheckEquity(BaseModel):
    sufficient_equity: bool = Field(
        description="True if the equity on deposit is greater than the value requested. False if less."
    )


loan_approval_check_equity_agent = LlmAgent(
    name="loan_approval_check_equity_agent",
    description="Asks deposit agent via A2A whether total deposits meet the calculated min_equity requirement.",
    model="gemini-2.5-flash",
    instruction=load_instructions("check-equity-prompt.txt"),
    tools=[
        AgentTool(agent=deposit_equity_agent)
    ],
    output_schema=CheckEquity,
    output_key="check_equity",
)


# Orchestrator 2: Sequentially compute required equity then verify against deposit agent
loan_approval_debt_equity_agent = SequentialAgent(
    name="loan_approval_debt_equity_agent",
    sub_agents=[
        loan_approval_get_total_value_agent,
        loan_approval_check_equity_agent,
    ],
)


# ==============================================================================
# SUB-AGENT 6: Load Customer Profile PDF from GCS and Determine Rating
# ==============================================================================
user_profile_base_instruction = load_instructions("user-profile-base-prompt.txt")
user_profile_uri = f"gs://{gcs_bucket}/loan-customer-info.pdf"

user_profile_instruction = [
    Part(text=user_profile_base_instruction),
    Part(text="Here is the loan policy:"),
    _load_pdf_part(policy_static_instruction_uri, "loan-policy.pdf"),
    Part(text="Here is the customer profile:"),
    _load_pdf_part(user_profile_uri, "loan-customer-info.pdf"),
]


class UserProfile(BaseModel):
    customer_rating: CustomerRating = Field(
        description="Based on the criteria and the customer info, how would we rate this customer?"
    )
    justification: str = Field(description="Why do we give the customer the rating we have?")


loan_approval_user_profile_agent = LlmAgent(
    name="loan_approval_user_profile_agent",
    description="Loads customer history PDF from GCS and rates customer credibility.",
    model="gemini-2.5-flash",
    static_instruction=Content(parts=user_profile_instruction),
    output_schema=UserProfile,
    output_key="user_profile",
)


# ==============================================================================
# Orchestrator 3: Parallel Review of Customer Profile and Debt-Equity Check
# Demonstrates ParallelAgent concurrent orchestration pattern
# ==============================================================================
loan_approval_review_agent = ParallelAgent(
    name="loan_approval_review_agent",
    sub_agents=[
        loan_approval_user_profile_agent,
        loan_approval_debt_equity_agent,
    ],
)


# ==============================================================================
# SUB-AGENT 7: Final Loan Decision and Response Synthesis
# Uses gemini-2.5-pro for high reasoning capability and strict adherence
# to customer privacy guardrails (never exposes internal debt ratios or ratings)
# ==============================================================================
loan_approval_report_agent = LlmAgent(
    name="loan_approval_report_agent",
    description="Report if a loan would be approved or not based on collected equity and profile evaluations.",
    model="gemini-2.5-pro",
    instruction=load_instructions("approval-report-prompt.txt"),
)


# ==============================================================================
# MASTER WORKFLOW AGENT: Complete Loan Approval Sub-Agent Pipeline
# Orchestrates stages 1 through 4 sequentially:
# Stage 1: Data gathering (requested amount, current debt)
# Stage 2: Policy extraction from GCS
# Stage 3: Parallel review (equity check via A2A + profile rating)
# Stage 4: Final decision and client notification
# ==============================================================================
loan_approval_agent = SequentialAgent(
    name="loan_approval_agent",
    description="Based on current account balances and the requested value, approve or decline the loan.",
    sub_agents=[
        loan_approval_data_agent,
        loan_approval_policy_agent,
        loan_approval_review_agent,
        loan_approval_report_agent,
    ],
)
