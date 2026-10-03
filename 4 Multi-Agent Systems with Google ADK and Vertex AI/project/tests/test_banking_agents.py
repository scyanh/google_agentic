#!/usr/bin/env python3
"""
Test Suite for Multi-Agent Banking System (Course 4 Project: 1790031746)
========================================================================
Validates all Rubric Criteria:
1. Part 1: Deposit Account Agent (DB config, tools, prompts, agent card, guardrails)
2. Part 2: Loan Account Agent (DB config, tools, prompts, agent card, sub-agent integration)
3. Part 3: Manager Agent (A2A Remote sub-agents, prompt routing, direct bank FAQ, agent card)
4. Part 4: Loan Approval Sub-Agent (SequentialAgent & ParallelAgent, TotalValueAgent math,
          output schemas/keys, GCS bucket env var, privacy guardrails)
5. Part 5: Guardrails, Privacy & Safety Verification

Usage:
    python3 -m unittest tests/test_banking_agents.py -v
"""

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
import yaml

# Add starter directory to sys.path
starter_dir = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(starter_dir))

from google.adk.agents import Agent, BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.sessions import InMemorySessionService

import deposit.agent as deposit_module
import loan.agent as loan_module
import loan.loan as loan_workflow
import manager.agent as manager_module


class TestRubric1_DepositAgent(unittest.TestCase):
    """Test Rubric Section 1: Deposit Account Agent Configuration."""

    def setUp(self):
        yaml_file = starter_dir / "deposit" / "tools.yaml"
        with open(yaml_file, "r") as f:
            self.tools_config = yaml.safe_load(f)

    def test_deposit_tools_yaml_configuration(self):
        """Verify deposit/tools.yaml specifies MySQL source with env vars."""
        self.assertIn("sources", self.tools_config, "tools.yaml must contain 'sources'")
        sources = self.tools_config["sources"]
        self.assertIn("deposit", sources)
        source = sources["deposit"]
        self.assertEqual(source.get("kind"), "mysql")
        self.assertIn("${MYSQL_HOST}", str(source.get("host")))
        self.assertIn("${MYSQL_USER}", str(source.get("user")))
        self.assertIn("${MYSQL_PASSWORD}", str(source.get("password")))

    def test_deposit_tools_defined(self):
        """Verify all required deposit tools are defined in tools.yaml."""
        tools = self.tools_config.get("tools", {})
        required_tools = ["get-accounts", "get-balance", "check-minimum-balance", "get-transactions"]
        for tool_name in required_tools:
            self.assertIn(tool_name, tools, f"Tool '{tool_name}' must be defined in deposit/tools.yaml")

    def test_deposit_root_agent_instance(self):
        """Verify deposit root_agent is an instance of Agent with valid tools."""
        self.assertIsInstance(deposit_module.root_agent, Agent)
        self.assertEqual(deposit_module.root_agent.name, "deposit_account_agent")
        self.assertGreaterEqual(len(deposit_module.root_agent.tools), 4)

    def test_deposit_prompt_guardrail_no_total_balance(self):
        """Verify deposit prompt strictly forbids revealing total balance of all accounts."""
        prompt_file = starter_dir / "deposit" / "agent-prompt.txt"
        with open(prompt_file, "r") as f:
            prompt_text = f.read()
        self.assertIn("NEVER", prompt_text)
        self.assertIn("total balance", prompt_text.lower())
        self.assertIn("check-minimum-balance", prompt_text)

    def test_deposit_agent_card(self):
        """Verify deposit/agent.json contains valid A2A agent card."""
        card_file = starter_dir / "deposit" / "agent.json"
        with open(card_file, "r") as f:
            card_data = json.load(f)
        self.assertEqual(card_data.get("name"), "deposit")
        self.assertIn("/a2a/deposit", card_data.get("url", ""))
        self.assertIn("skills", card_data)
        self.assertGreaterEqual(len(card_data["skills"]), 1)

    def test_deposit_session_service(self):
        """Verify InMemorySessionService is configured for deposit agent."""
        self.assertIsInstance(deposit_module.session_service, InMemorySessionService)


class TestRubric2_LoanAgent(unittest.TestCase):
    """Test Rubric Section 2: Loan Account Agent Configuration."""

    def setUp(self):
        yaml_file = starter_dir / "loan" / "tools.yaml"
        with open(yaml_file, "r") as f:
            self.tools_config = yaml.safe_load(f)

    def test_loan_tools_yaml_configuration(self):
        """Verify loan/tools.yaml specifies MySQL source with env vars."""
        self.assertIn("sources", self.tools_config)
        source = self.tools_config["sources"].get("loan", {})
        self.assertEqual(source.get("kind"), "mysql")
        self.assertIn("${MYSQL_HOST}", str(source.get("host")))
        self.assertIn("${MYSQL_USER}", str(source.get("user")))
        self.assertIn("${MYSQL_PASSWORD}", str(source.get("password")))

    def test_loan_tools_defined(self):
        """Verify required loan tools are defined in tools.yaml."""
        tools = self.tools_config.get("tools", {})
        self.assertIn("get-loan-info", tools)
        self.assertIn("get-total-outstanding-balance", tools)

    def test_loan_root_agent_instance(self):
        """Verify loan root_agent has loan_info_tool and sub_agents."""
        self.assertIsInstance(loan_module.root_agent, Agent)
        self.assertEqual(loan_module.root_agent.name, "loan_account_agent")
        self.assertGreaterEqual(len(loan_module.root_agent.tools), 1)
        sub_agent_names = [sa.name for sa in loan_module.root_agent.sub_agents]
        self.assertIn("loan_approval_agent", sub_agent_names)

    def test_loan_agent_card(self):
        """Verify loan/agent.json contains valid A2A agent card."""
        card_file = starter_dir / "loan" / "agent.json"
        with open(card_file, "r") as f:
            card_data = json.load(f)
        self.assertEqual(card_data.get("name"), "loan")
        self.assertIn("/a2a/loan", card_data.get("url", ""))
        self.assertIn("skills", card_data)


class TestRubric3_ManagerAgent(unittest.TestCase):
    """Test Rubric Section 3: Manager Agent Configuration and Routing."""

    def test_manager_root_agent_instance(self):
        """Verify manager root_agent is an instance of Agent."""
        self.assertIsInstance(manager_module.root_agent, Agent)
        self.assertEqual(manager_module.root_agent.name, "bank_agent")

    def test_manager_a2a_sub_agents(self):
        """Verify manager agent connects to deposit and loan agents as sub_agents."""
        sub_agent_names = [sa.name for sa in manager_module.root_agent.sub_agents]
        self.assertIn("deposit_agent", sub_agent_names)
        self.assertIn("loan_agent", sub_agent_names)

    def test_manager_prompt_routing_and_faq(self):
        """Verify manager prompt handles general bank questions directly and routes account queries."""
        prompt_file = starter_dir / "manager" / "agent-prompt.txt"
        with open(prompt_file, "r") as f:
            prompt_text = f.read()
        self.assertIn("Hours", prompt_text)
        self.assertIn("deposit_agent", prompt_text)
        self.assertIn("loan_agent", prompt_text)

    def test_manager_agent_card(self):
        """Verify manager/agent.json contains valid A2A agent card."""
        card_file = starter_dir / "manager" / "agent.json"
        with open(card_file, "r") as f:
            card_data = json.load(f)
        self.assertEqual(card_data.get("name"), "manager")
        self.assertIn("/a2a/manager", card_data.get("url", ""))
        self.assertIn("skills", card_data)


class TestRubric4_LoanApprovalOrchestration(unittest.TestCase):
    """Test Rubric Section 4: Loan Approval Orchestration and State Management."""

    def test_orchestration_agents_present(self):
        """Verify loan approval workflow employs both SequentialAgent and ParallelAgent."""
        self.assertIsInstance(
            loan_workflow.loan_approval_agent, SequentialAgent,
            "Master loan_approval_agent must be a SequentialAgent"
        )
        self.assertIsInstance(
            loan_workflow.loan_approval_review_agent, ParallelAgent,
            "loan_approval_review_agent must be a ParallelAgent"
        )
        self.assertIsInstance(
            loan_workflow.loan_approval_data_agent, SequentialAgent,
            "loan_approval_data_agent must be a SequentialAgent"
        )

    def test_total_value_agent_custom_arithmetic(self):
        """Verify TotalValueAgent is a custom BaseAgent that accurately calculates equity."""
        self.assertTrue(
            issubclass(loan_workflow.TotalValueAgent, BaseAgent),
            "TotalValueAgent must subclass BaseAgent (custom agent, not LLM)"
        )
        agent_instance = loan_workflow.TotalValueAgent("test_calculator")

        class MockSession:
            def __init__(self, state):
                self.state = state

        class MockContext:
            def __init__(self, state):
                self.session = MockSession(state)

        test_state = {
            "requested": {"amount": 10000.0, "loan_type": "auto"},
            "outstanding_balance": {"total": 12024.04},
            "policy": {"debt_equity_ratio": 4, "minimum_rating": "good"},
        }
        ctx = MockContext(test_state)

        async def run_calc():
            events = []
            async for ev in agent_instance._run_async_impl(ctx):
                events.append(ev)
            return events

        events = asyncio.run(run_calc())
        self.assertEqual(len(events), 1)
        ev = events[0]
        state_delta = ev.actions.state_delta
        self.assertIn("min_equity", state_delta)
        # (12024.04 + 10000) / 4 = 22024.04 / 4 = 5506.01
        self.assertAlmostEqual(state_delta["min_equity"], 5506.01, places=2)
        self.assertIn("5506.01", ev.content.parts[0].text)

    def test_output_schema_and_keys(self):
        """Verify sub-agents define output_schema and output_key to save to state."""
        self.assertEqual(loan_workflow.loan_approval_get_requested_value_agent.output_key, "requested")
        self.assertEqual(loan_workflow.loan_approval_get_outstanding_balance_agent.output_key, "outstanding_balance")
        self.assertEqual(loan_workflow.loan_approval_policy_agent.output_key, "policy")
        self.assertEqual(loan_workflow.loan_approval_check_equity_agent.output_key, "check_equity")
        self.assertEqual(loan_workflow.loan_approval_user_profile_agent.output_key, "user_profile")

    def test_gcs_bucket_env_var_configured(self):
        """Verify GCS bucket for policy and customer PDFs is configured via environment variable."""
        code_path = starter_dir / "loan" / "loan.py"
        with open(code_path, "r") as f:
            code_text = f.read()
        self.assertIn("GCS_BUCKET", code_text)
        self.assertIn("loan-policy.pdf", code_text)
        self.assertIn("loan-customer-info.pdf", code_text)

    def test_final_decision_report_model(self):
        """Verify final loan decision agent uses gemini-2.5-pro for high reasoning."""
        self.assertEqual(
            loan_workflow.loan_approval_report_agent.model,
            "gemini-2.5-pro"
        )


class TestRubric5_GuardrailsAndPrivacy(unittest.TestCase):
    """Test Rubric Section 5: Security Guardrails and Rejection Privacy."""

    def test_rejection_privacy_prompt(self):
        """Verify approval report prompt strictly prevents disclosing sensitive reasons upon rejection."""
        prompt_file = starter_dir / "loan" / "approval-report-prompt.txt"
        with open(prompt_file, "r") as f:
            prompt = f.read()
        self.assertIn("loan officer", prompt.lower())
        self.assertIn("never explain the details", prompt.lower())

    def test_deposit_guardrail_unauthorized_actions(self):
        """Verify deposit prompt declines fund transfers/deposits."""
        prompt_file = starter_dir / "deposit" / "agent-prompt.txt"
        with open(prompt_file, "r") as f:
            prompt = f.read()
        self.assertIn("cannot deposit", prompt.lower())


if __name__ == "__main__":
    unittest.main()
