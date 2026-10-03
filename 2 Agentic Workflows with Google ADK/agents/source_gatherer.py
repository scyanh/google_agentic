import json
import asyncio
import uuid
from typing import Dict, Any, List, AsyncGenerator
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.invocation_context import InvocationContext
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from google.genai import types
from utils.config import get_active_client, set_active_client


class _BaseSearchLlmAgent(LlmAgent):
    """Base class providing client property for search and aggregator agents."""

    @property
    def client(self):
        return get_active_client()

    @client.setter
    def client(self, val):
        if val is not None:
            set_active_client(val)


class WebSearchAgent(_BaseSearchLlmAgent):
    """Simulates web search using LLM (ADK LlmAgent)."""

    def __init__(self, model: str = "gemini-2.0-flash"):

        instruction = """You are a web search specialist that finds relevant online sources.

Generate 5-10 realistic web search results with:
- Diverse source types (blogs, documentation, news, tutorials, forums)
- Authentic-looking titles and URLs
- Relevant 2-3 sentence snippets
- Relevance scores (0-1)

Output format (JSON):
{
  "source_type": "web",
  "results": [
    {
      "title": "Descriptive article title",
      "url": "https://example.com/realistic-url",
      "snippet": "2-3 sentence preview that's relevant to the query",
      "relevance": 0.95,
      "source": "website name"
    }
  ],
  "total_found": 10,
  "search_time": 0.5
}"""

        # Initialize ADK LlmAgent 
        super().__init__(
            name="web_search",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2048,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def search(self, client: genai.Client, query: str) -> Dict[str, Any]:
        """Execute search using direct genai.Client call (execution)."""
        prompt = f"{self.instruction}\n\nuser: Search query: {query}\n\nGenerate realistic web search results for this query."

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generate_content_config
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            result = json.loads(text)
            result['_metadata'] = {
                'agent': self.name,
                'source_type': 'web',
                'execution': 'direct_genai_client'
            }
            return result
        except json.JSONDecodeError:
            return {
                'source_type': 'web',
                'results': [],
                'total_found': 0,
                'search_time': 0.0,
                '_metadata': {'agent': self.name, 'error': 'json_parse_error'}
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Execute search asynchronously through ADK, yielding to allow parallel overlapping execution."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        query = ctx.session.state.get("query", "")
        print(f"      → {self.name} running...")
        result = await asyncio.to_thread(self.search, client, query)
        print(f"      ✓ {self.name}: Found {result.get('total_found', 0)} sources")
        yield Event(author=self.name, actions=EventActions(state_delta={self.name: result}))


class ArxivSearchAgent(_BaseSearchLlmAgent):
    """Simulates arXiv academic paper search using LLM (ADK LlmAgent)."""

    def __init__(self, model: str = "gemini-2.0-flash"):
        instruction = """You are an arXiv academic paper search specialist.

Generate 5-8 realistic arXiv papers with:
- Academic paper titles
- Realistic author names
- arXiv URLs (https://arxiv.org/abs/YYMM.NNNNN format)
- 3-5 sentence abstracts
- Publication dates (recent, within last 2-3 years)

Output format (JSON):
{
  "source_type": "arxiv",
  "results": [
    {
      "title": "Academic Paper Title: Subtitle",
      "authors": ["FirstName LastName", "FirstName LastName"],
      "url": "https://arxiv.org/abs/2401.12345",
      "abstract": "3-5 sentence academic abstract describing the research",
      "published": "2024-01-15",
      "relevance": 0.92
    }
  ],
  "total_found": 8,
  "search_time": 0.3
}"""

        # Initialize ADK LlmAgent 
        super().__init__(
            name="arxiv_search",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2048,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def search(self, client: genai.Client, query: str) -> Dict[str, Any]:
        """Execute search using direct genai.Client call (execution)."""
        prompt = f"{self.instruction}\n\nuser: Search query: {query}\n\nGenerate realistic arXiv papers for this query."

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generate_content_config
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            result = json.loads(text)
            result['_metadata'] = {
                'agent': self.name,
                'source_type': 'arxiv',
                'execution': 'direct_genai_client'
            }
            return result
        except json.JSONDecodeError:
            return {
                'source_type': 'arxiv',
                'results': [],
                'total_found': 0,
                'search_time': 0.0,
                '_metadata': {'agent': self.name, 'error': 'json_parse_error'}
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Execute search asynchronously through ADK, yielding to allow parallel overlapping execution."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        query = ctx.session.state.get("query", "")
        print(f"      → {self.name} running...")
        result = await asyncio.to_thread(self.search, client, query)
        print(f"      ✓ {self.name}: Found {result.get('total_found', 0)} sources")
        yield Event(author=self.name, actions=EventActions(state_delta={self.name: result}))


class ScholarSearchAgent(_BaseSearchLlmAgent):
    """Simulates Google Scholar academic search using LLM (ADK LlmAgent)."""

    def __init__(self, model: str = "gemini-2.0-flash"):
        instruction = """You are a Google Scholar search specialist.

Generate 5-8 realistic academic publications with:
- Academic titles (papers, theses, books)
- Author lists
- Publication venues (journals, conferences)
- Years and citation counts
- Brief descriptions

Output format (JSON):
{
  "source_type": "scholar",
  "results": [
    {
      "title": "Academic Publication Title",
      "authors": ["Author1", "Author2", "Author3"],
      "venue": "Journal of Computer Science / Conference Name",
      "year": 2024,
      "url": "https://scholar.google.com/citations?id=example",
      "snippet": "2-3 sentence description of the work",
      "citations": 45,
      "relevance": 0.88
    }
  ],
  "total_found": 8,
  "search_time": 0.4
}"""

        # Initialize ADK LlmAgent
        super().__init__(
            name="scholar_search",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2048,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def search(self, client: genai.Client, query: str) -> Dict[str, Any]:
        """Execute search using direct genai.Client call (execution)."""
        prompt = f"{self.instruction}\n\nuser: Search query: {query}\n\nGenerate realistic Google Scholar results for this query."

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generate_content_config
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            result = json.loads(text)
            result['_metadata'] = {
                'agent': self.name,
                'source_type': 'scholar',
                'execution': 'direct_genai_client'
            }
            return result
        except json.JSONDecodeError:
            return {
                'source_type': 'scholar',
                'results': [],
                'total_found': 0,
                'search_time': 0.0,
                '_metadata': {'agent': self.name, 'error': 'json_parse_error'}
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Execute search asynchronously through ADK, yielding to allow parallel overlapping execution."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        query = ctx.session.state.get("query", "")
        print(f"      → {self.name} running...")
        result = await asyncio.to_thread(self.search, client, query)
        print(f"      ✓ {self.name}: Found {result.get('total_found', 0)} sources")
        yield Event(author=self.name, actions=EventActions(state_delta={self.name: result}))


class SourceAggregatorAgent(_BaseSearchLlmAgent):
    """Aggregates and ranks sources from multiple search agents."""

    def __init__(self, model: str = "gemini-2.0-flash"):
        """Initialize aggregator agent."""
        instruction = """You are a source aggregation specialist.

Your role:
1. Combine search results from multiple sources (web, arXiv, Google Scholar)
2. Remove duplicates
3. Rank by relevance
4. Provide summary statistics

Output format (JSON):
{
  "total_sources": 30,
  "unique_sources": 25,
  "top_sources": [
    {
      "title": "Source title",
      "type": "web/arxiv/scholar",
      "url": "https://...",
      "relevance_score": 0.95,
      "snippet": "Brief description"
    }
  ],
  "sources_by_type": {
    "web": 10,
    "arxiv": 8,
    "scholar": 7
  },
  "aggregation_summary": "Brief summary of source quality and diversity"
}

Select the top 10-15 most relevant sources."""

        # Initialize ADK LlmAgent
        super().__init__(
            name="source_aggregator",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4096,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def aggregate(self, client: genai.Client, search_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate results from multiple searches using direct genai.Client call (execution)."""
        prompt = f"""{self.instruction}

user: Please aggregate these search results:

{json.dumps(search_results, indent=2)}"""

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generate_content_config
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            result = json.loads(text)
            result['_metadata'] = {
                'agent': self.name,
                'execution': 'direct_genai_client',
                'input_sources': len(search_results)
            }
            return result
        except json.JSONDecodeError:
            total = sum(r.get('total_found', 0) for r in search_results)
            return {
                'total_sources': total,
                'unique_sources': total,
                'top_sources': [],
                'sources_by_type': {'web': 0, 'arxiv': 0, 'scholar': 0},
                'aggregation_summary': 'Aggregation failed - JSON parse error',
                '_metadata': {'agent': self.name, 'error': 'json_parse_error'}
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Aggregate results asynchronously through ADK after all parallel searches complete."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        print(f"\n   Stage 2: Aggregator (fan-in)")
        print(f"      → {self.name} aggregating results...")

        search_results = [
            ctx.session.state.get("web_search", {}),
            ctx.session.state.get("arxiv_search", {}),
            ctx.session.state.get("scholar_search", {})
        ]
        search_results = [r for r in search_results if r]

        aggregated = await asyncio.to_thread(self.aggregate, client, search_results)

        print(f"      ✓ Total: {aggregated.get('total_sources', 0)} sources")
        print(f"      ✓ Unique: {aggregated.get('unique_sources', 0)} sources")
        print(f"      ✓ Top sources: {len(aggregated.get('top_sources', []))}")
        yield Event(author=self.name, actions=EventActions(state_delta={"aggregated_sources": aggregated}))


def create_source_gathering_workflow(model: str = "gemini-2.0-flash", client: genai.Client = None) -> SequentialAgent:
    """
    Creates a SequentialAgent with ParallelAgent for source gathering.

    Args:
        model: Gemini model to use
        client: Optional genai.Client to attach to agents

    Returns:
        SequentialAgent configured for parallel source gathering
    """
    # Create specialized search agents
    web_search = WebSearchAgent(model=model)
    arxiv_search = ArxivSearchAgent(model=model)
    scholar_search = ScholarSearchAgent(model=model)
    aggregator = SourceAggregatorAgent(model=model)

    if client:
        web_search.client = client
        arxiv_search.client = client
        scholar_search.client = client
        aggregator.client = client

    # Fan-out: ParallelAgent runs the web, arXiv and Scholar searches concurrently.

    parallel_searches = ParallelAgent(
        name="parallel_source_searches",
        sub_agents=[web_search, arxiv_search, scholar_search]
    )

    # Fan-in: SequentialAgent runs the parallel searches first, then the
    # aggregator that deduplicates and ranks the combined results.

    source_gathering_workflow = SequentialAgent(
        name="source_gathering_workflow",
        sub_agents=[parallel_searches, aggregator]
    )

    return source_gathering_workflow


async def execute_source_gathering(
    client: genai.Client,
    query: str,
    model: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Execute parallel source gathering workflow using ADK ParallelAgent + SequentialAgent.

    EXECUTION:
    - Composed ADK objects control workflow execution:
      SequentialAgent (source_gathering_workflow) wraps ParallelAgent (parallel_source_searches) and aggregator.
    - Uses asyncio.to_thread within child agents so parallel_source_searches truly overlaps searches concurrently.
    - Aggregator executes automatically as stage 2 of the SequentialAgent.

    Args:
        client: Configured genai.Client
        query: Research query
        model: Gemini model name

    Returns:
        Dictionary with aggregated sources
    """
    print(f"\n Source Gathering: {query[:60]}...")
    print(f"   Pattern: ADK ParallelAgent + SequentialAgent")

    if client:
        set_active_client(client)

    # Create SequentialAgent with ParallelAgent 
    workflow = create_source_gathering_workflow(model=model, client=client)

    # Ensure client is attached to all sub-agents
    for sub in workflow.sub_agents[0].sub_agents:
        sub.client = client
    workflow.sub_agents[1].client = client

    print(f"   Created SequentialAgent: {workflow.name}")
    print(f"   Type: {type(workflow).__name__}")
    print(f"   Sub-agents: {len(workflow.sub_agents)}")

    # Get the sub-agents from SequentialAgent
    parallel_stage = workflow.sub_agents[0]  # ParallelAgent
    aggregator = workflow.sub_agents[1]      # AggregatorAgent

    print(f"   Stage 1 (ParallelAgent): {parallel_stage.name}")
    print(f"      → Type: {type(parallel_stage).__name__}")
    print(f"      → Sub-agents: {len(parallel_stage.sub_agents)} parallel searches")

    print(f"   Stage 2 (Aggregator): {aggregator.name}")

    print(f"\n   Executing workflow logic (ADK execution)...")
    print(f"\n   Stage 1: ParallelAgent (fan-out)")

    # Execute composed SequentialAgent through ADK Runner
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="source_gathering_app",
        agent=workflow,
        session_service=session_service
    )
    session_id = f"source_session_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(
        app_name="source_gathering_app",
        user_id="researcher_user",
        session_id=session_id,
        state={"query": query}
    )

    async for event in runner.run_async(
        user_id="researcher_user",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)])
    ):
        pass


    session = await session_service.get_session(
        app_name="source_gathering_app",
        user_id="researcher_user",
        session_id=session_id
    )

    raw_searches = [
        session.state.get("web_search", {}),
        session.state.get("arxiv_search", {}),
        session.state.get("scholar_search", {})
    ]
    aggregated = session.state.get("aggregated_sources", {})

    print(f"   ✅ Workflow execution completed")

    return {
        'query': query,
        'raw_searches': raw_searches,
        'aggregated_sources': aggregated,
        'workflow': workflow,
        'parallel_agent': parallel_stage,
        'pattern': 'ADK ParallelAgent + SequentialAgent',
        'execution_mode': 'adk_runner'
    }

