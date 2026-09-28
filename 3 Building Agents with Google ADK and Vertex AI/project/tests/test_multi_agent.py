import asyncio
import unittest
from agent import root_agent, avian_specialist, inventory_specialist, store_specialist, session_service
from google.adk.runners import Runner
from google.genai import types

class TestMultiAgentSystem(unittest.IsolatedAsyncioTestCase):

    async def test_agent_structure(self):
        # 1. Verify Root Agent is Concierge with 3 Sub-Agents
        self.assertEqual(root_agent.name, "bettys_bird_boutique_concierge")
        self.assertEqual(len(root_agent.sub_agents), 3)
        sub_agent_names = {a.name for a in root_agent.sub_agents}
        self.assertEqual(sub_agent_names, {"avian_specialist", "inventory_specialist", "store_specialist"})

        # 2. Verify Chloe has RAG and Google Search
        chloe_tools = [getattr(t, "__name__", getattr(t, "name", str(t))) for t in avian_specialist.tools]
        self.assertTrue(any("datastore" in t for t in chloe_tools))
        self.assertTrue(any("google_search" in t for t in chloe_tools))

        # 3. Verify David has SQL database tools
        david_tools = [getattr(t, "__name__", getattr(t, "name", str(t))) for t in inventory_specialist.tools]
        self.assertTrue(any("price" in t for t in david_tools))
        self.assertTrue(any("list" in t for t in david_tools))

        # 4. Verify James has Datastore RAG and Date tools
        james_tools = [getattr(t, "__name__", getattr(t, "name", str(t))) for t in store_specialist.tools]
        self.assertTrue(any("datastore" in t for t in james_tools))
        self.assertTrue(any("date" in t for t in james_tools))

if __name__ == "__main__":
    unittest.main()
