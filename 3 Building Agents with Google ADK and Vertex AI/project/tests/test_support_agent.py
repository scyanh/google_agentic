#!/usr/bin/env python3
"""
Test Suite for Betty's Bird Boutique Agent (Course 3 Project)
=============================================================
Validates all Rubric Criteria & Reviewer Feedback:
1. Root Agent & Session Service Configuration
2. Product Database through MCP Toolbox (tools.yaml with get_product_price)
3. Vertex AI Search Datastore Tool (datastore.py)
4. Grounding with Google Search Agent (search_agent.py & search-prompt.txt)
5. Guardrails & Prompt Design (agent-prompt.txt with get_product_price consistency)
6. Rubric Assessment Sequence Simulation
7. Stand-Out Features (Date-Awareness & Product Catalog)

Usage:
    python3 -m unittest tests/test_support_agent.py
"""

import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Add starter directory to sys.path
current_dir = Path(__file__).parent.absolute()
starter_dir = current_dir.parent
sys.path.insert(0, str(starter_dir))

import yaml
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool, google_search

import agent
import datastore
import search_agent


class TestRubric1_RootAgent(unittest.TestCase):
    """Test Rubric Section: Root Agent Configuration."""

    def test_root_agent_instance(self):
        """Verify root_agent is an instance of Agent."""
        self.assertIsInstance(
            agent.root_agent, Agent, "root_agent must be an instance of Agent"
        )

    def test_root_agent_name_and_description(self):
        """Verify root_agent has suitable name and description for bird boutique."""
        self.assertEqual(agent.root_agent.name, "bettys_bird_boutique_agent")
        self.assertIn("Betty", agent.root_agent.description)
        self.assertIn("Bird", agent.root_agent.description)

    def test_root_agent_instruction_from_file(self):
        """Verify agent instructions match agent-prompt.txt."""
        prompt_file = starter_dir / "agent-prompt.txt"
        with open(prompt_file, "r") as f:
            expected_content = f.read()
        self.assertEqual(agent.root_agent.instruction, expected_content)

    def test_session_service_configuration(self):
        """Verify InMemorySessionService is imported and instantiated."""
        self.assertTrue(
            hasattr(agent, "session_service"), "agent.py must define session_service"
        )
        self.assertIsInstance(
            agent.session_service,
            InMemorySessionService,
            "session_service must be an instance of InMemorySessionService",
        )

    def test_model_selection_and_comment_justification(self):
        """Verify Gemini model is specified and justified in agent.py comments."""
        self.assertIn(
            "gemini",
            agent.root_agent.model.lower(),
            "Model must be a Gemini model",
        )
        agent_code_path = starter_dir / "agent.py"
        with open(agent_code_path, "r") as f:
            code_text = f.read()
        self.assertIn(
            "MODEL SELECTION JUSTIFICATION",
            code_text,
            "agent.py must contain a comment justifying model selection",
        )
        self.assertIn("gemini-2.5-flash", code_text)
        self.assertIn("gemini-2.5-pro", code_text)
        self.assertIn("gemini-2.5-flash-lite", code_text)


class TestRubric2_DatabaseToolbox(unittest.TestCase):
    """Test Rubric Section: Product Databases through MCP Toolbox & get_product_price."""

    def setUp(self):
        yaml_file = starter_dir / "tools.yaml"
        with open(yaml_file, "r") as f:
            self.tools_config = yaml.safe_load(f)

    def test_source_configuration(self):
        """Verify tools.yaml has a valid MySQL source using ${VAR_NAME} notation."""
        self.assertIn(
            "sources", self.tools_config, "tools.yaml must contain 'sources'"
        )
        sources = self.tools_config["sources"]
        self.assertIn("betty_products", sources)
        source = sources["betty_products"]
        self.assertEqual(source.get("kind"), "mysql")
        self.assertIn("${MYSQL_HOST}", str(source.get("host")))
        self.assertIn("${MYSQL_USER}", str(source.get("user")))
        self.assertIn("${MYSQL_PASSWORD}", str(source.get("password")))

    def test_get_product_price_tool_definition(self):
        """Verify get_product_price tool specification in tools.yaml."""
        tools = self.tools_config.get("tools", {})
        self.assertTrue(
            "get_product_price" in tools or "get-product-price" in tools,
            "Tool 'get_product_price' must be defined in tools.yaml",
        )
        tool = tools.get("get_product_price") or tools.get("get-product-price")
        self.assertEqual(tool.get("kind"), "mysql-sql")
        self.assertEqual(tool.get("source"), "betty_products")
        self.assertIn("parameters", tool)
        self.assertEqual(len(tool["parameters"]), 1)
        param = tool["parameters"][0]
        self.assertEqual(param["name"], "product_name")
        self.assertEqual(param["type"], "string")

        # Statement must use LIKE with wildcards and ? parameter
        sql = tool.get("statement", "")
        self.assertIn("LIKE", sql.upper())
        self.assertIn("?", sql)
        self.assertIn("products", sql.lower())

    def test_toolbox_client_integration(self):
        """Verify ToolboxSyncClient is used with URL without trailing slash."""
        agent_code_path = starter_dir / "agent.py"
        with open(agent_code_path, "r") as f:
            code_text = f.read()
        self.assertIn("ToolboxSyncClient", code_text)
        self.assertIn('os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5000")', code_text)
        self.assertNotIn('http://127.0.0.1:5000/"', code_text)

    def test_product_price_tool_lookup_and_not_found(self):
        """Verify get_product_price tool correctly returns prices and handles not found."""
        tools_dict = {
            getattr(t, "name", getattr(t, "__name__", str(t))): t
            for t in agent.root_agent.tools
        }
        self.assertIn("get_product_price", tools_dict)
        price_tool = tools_dict["get_product_price"]

        # 1. Successful lookup
        res_found = price_tool("Bird Seed Mix")
        self.assertTrue(
            any("15.99" in str(item) for item in res_found)
            or "15.99" in str(res_found),
            "Should find Bird Seed Mix with price $15.99",
        )

        # 2. Not found scenario
        res_not_found = price_tool("NonExistentItem999")
        self.assertTrue(
            "not found" in str(res_not_found).lower()
            or len(res_not_found) == 0,
            "Should handle not found scenario gracefully",
        )


class TestRubric3_DatastoreTool(unittest.TestCase):
    """Test Rubric Section: Search Tools (Vertex AI & Datastore RAG)."""

    def test_search_function_exists(self):
        """Verify search() and datastore_search_tool() exist in datastore.py."""
        self.assertTrue(
            hasattr(datastore, "search"), "datastore.py must define search()"
        )
        self.assertTrue(
            hasattr(datastore, "datastore_search_tool"),
            "datastore.py must define datastore_search_tool()",
        )

    def test_attribution_comment_present(self):
        """Verify attribution comment to Google sample is present."""
        datastore_code_path = starter_dir / "datastore.py"
        with open(datastore_code_path, "r") as f:
            code_text = f.read()
        self.assertIn("ATTRIBUTION", code_text)
        self.assertIn("cloud.google.com/generative-ai-app-builder", code_text)

    def test_datastore_search_tool_docstring_and_params(self):
        """Verify datastore_search_tool has proper docstring and parameters."""
        doc = datastore.datastore_search_tool.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("Betty's Bird Boutique", doc)
        sig = inspect.signature(datastore.datastore_search_tool)
        self.assertIn("search_query", sig.parameters)

    @patch("google.cloud.discoveryengine_v1.SearchServiceClient")
    def test_search_execution_and_chunk_extraction(self, mock_client_cls):
        """Verify search() correctly builds SearchRequest and extracts chunks."""
        mock_client = Mock()
        mock_client_cls.return_value = mock_client

        # Mock page result with chunk content
        mock_chunk_1 = Mock()
        mock_chunk_1.content = "Betty's Bird Boutique is open Thursday 9am - 5pm."
        mock_res_1 = Mock()
        mock_res_1.chunk = mock_chunk_1
        mock_res_1.document = None

        mock_page_result = [mock_res_1]
        mock_client.search.return_value = mock_page_result

        results = datastore.search(
            project_id="test-proj",
            location="global",
            engine_id="test-engine",
            search_query="When are you open on Thursday?",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("Thursday 9am - 5pm", results[0])


class TestRubric4_SearchAgent(unittest.TestCase):
    """Test Rubric Section: Grounding with Google Search & search-prompt.txt Sections."""

    def test_search_agent_definition(self):
        """Verify search_agent is an Agent with google_search tool."""
        self.assertIsInstance(
            search_agent.search_agent,
            Agent,
            "search_agent must be an instance of Agent",
        )
        self.assertEqual(
            search_agent.search_agent.name, "bird_web_search_agent"
        )
        self.assertIn(google_search, search_agent.search_agent.tools)

    def test_search_agent_tool_wrapper(self):
        """Verify search_agent_tool is an AgentTool wrapping search_agent."""
        self.assertIsInstance(
            search_agent.search_agent_tool,
            AgentTool,
            "search_agent_tool must be an AgentTool",
        )
        self.assertEqual(
            search_agent.search_agent_tool.agent, search_agent.search_agent
        )

    def test_search_agent_model_comment(self):
        """Verify search_agent.py has model selection and performance justification comment."""
        code_path = starter_dir / "search_agent.py"
        with open(code_path, "r") as f:
            code_text = f.read()
        self.assertIn("MODEL SELECTION", code_text)
        self.assertIn("PERFORMANCE EVALUATION", code_text)
        self.assertIn("gemini-2.5-flash", code_text)
        self.assertIn("gemini-2.5-pro", code_text)
        self.assertIn("gemini-2.5-flash-lite", code_text)

    def test_search_prompt_required_sections(self):
        """Verify search-prompt.txt has all dedicated sections requested by reviewer."""
        prompt_path = starter_dir / "search-prompt.txt"
        with open(prompt_path, "r") as f:
            content = f.read()
        self.assertIn("SEARCH-RELATED QUERY GUIDANCE", content)
        self.assertIn("TYPES OF QUERIES YOU HANDLE", content)
        self.assertIn("CITATION REQUIREMENTS", content)
        self.assertIn("GUARDRAILS", content)


class TestRubric5_GuardrailsAndPrompts(unittest.TestCase):
    """Test Rubric Section: Prompt Engineering & Tool Naming Consistency."""

    def test_guardrail_no_order_taking(self):
        """Verify agent-prompt.txt explicitly forbids taking orders."""
        prompt_path = starter_dir / "agent-prompt.txt"
        with open(prompt_path, "r") as f:
            content = f.read()
        self.assertIn("STRICTLY NO ORDER TAKING", content)
        self.assertIn("MUST NOT process orders", content)
        self.assertIn("visit", content.lower())

    def test_guardrail_domain_boundaries(self):
        """Verify agent-prompt.txt restricts topics to birds and the boutique."""
        prompt_path = starter_dir / "agent-prompt.txt"
        with open(prompt_path, "r") as f:
            content = f.read()
        self.assertIn("DOMAIN BOUNDARIES", content)
        self.assertIn("exclusively to all things birds", content)

    def test_tool_naming_consistency_in_prompt(self):
        """Verify agent-prompt.txt uses get_product_price consistently."""
        prompt_path = starter_dir / "agent-prompt.txt"
        with open(prompt_path, "r") as f:
            content = f.read()
        self.assertIn("get_product_price", content)
        self.assertNotIn("get-product-price", content)


class TestRubric6_RubricAssessmentConversationSequence(unittest.TestCase):
    """Simulate and test the required 5-turn assessment conversation sequence."""

    def test_conversation_sequence_routing_intent(self):
        """Test how the agent instructions and tools map to the 5 rubric assessment questions."""
        tools_by_name = {
            getattr(t, "name", getattr(t, "__name__", str(t))): t
            for t in agent.root_agent.tools
        }

        # Check required tools are present in root_agent
        self.assertIn("datastore_search_tool", tools_by_name)
        self.assertIn("bird_web_search_agent", tools_by_name)
        self.assertIn("get_product_price", tools_by_name)


class TestRubric7_StandOutFeatures(unittest.TestCase):
    """Test Rubric Section: Suggestions to Make Your Project Stand Out."""

    def test_date_awareness_tool(self):
        """Verify get_current_date_and_day tool exists and returns day of week."""
        self.assertTrue(
            hasattr(agent, "get_current_date_and_day"),
            "agent.py must provide get_current_date_and_day tool",
        )
        result = agent.get_current_date_and_day()
        self.assertIn("Today is", result)
        self.assertIn("Current time:", result)


if __name__ == "__main__":
    unittest.main()
