#!/usr/bin/env python3
"""
Test Suite for AI Research Assistant Multi-Agent System TODOs
============================================================
Validates Task 1 to Task 5 implementations.

Usage:
    python -m unittest tests/test_todos.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent, LlmAgent
from agents.researcher import (
    ResearcherAgent,
    ResearchCriticAgent,
    create_research_loop_agent,
    execute_research_loop
)
from agents.source_gatherer import (
    WebSearchAgent,
    ArxivSearchAgent,
    ScholarSearchAgent,
    SourceAggregatorAgent,
    create_source_gathering_workflow,
    execute_source_gathering
)
from agents.router import DomainClassifierAgent
from agents.evaluator import PerformanceEvaluator, PerformanceMetrics


class TestTask1_LoopAgent(unittest.TestCase):
    """Test Task 1: Implement LoopAgent pattern in agents/researcher.py"""

    def test_create_research_loop_agent_type(self):
        """Test that create_research_loop_agent returns a LoopAgent."""
        loop = create_research_loop_agent(model="gemini-2.0-flash", max_iterations=3)
        self.assertIsNotNone(loop, "LoopAgent should not be None")
        self.assertIsInstance(loop, LoopAgent, "Should return an instance of LoopAgent")
        self.assertEqual(loop.name, "research_refinement_loop")
        self.assertEqual(loop.max_iterations, 3)

    def test_loop_agent_sub_agents(self):
        """Test that LoopAgent contains ResearcherAgent and ResearchCriticAgent."""
        loop = create_research_loop_agent(model="gemini-2.0-flash", max_iterations=4)
        self.assertEqual(len(loop.sub_agents), 2, "LoopAgent must contain exactly 2 sub-agents")
        
        generator = loop.sub_agents[0]
        validator = loop.sub_agents[1]

        self.assertIsInstance(generator, ResearcherAgent, "First sub-agent must be ResearcherAgent")
        self.assertIsInstance(validator, ResearchCriticAgent, "Second sub-agent must be ResearchCriticAgent")
        self.assertEqual(generator.name, "researcher")
        self.assertEqual(validator.name, "critic")

    @patch.object(ResearchCriticAgent, 'evaluate')
    @patch.object(ResearcherAgent, 'generate')
    def test_loop_agent_adk_runner_execution(self, mock_generate, mock_evaluate):
        """Test that execute_research_loop runs through ADK Runner with multiple iterations."""
        import asyncio
        mock_generate.side_effect = [
            {'answer': 'Draft 1', 'confidence': 'medium'},
            {'answer': 'Draft 2', 'confidence': 'high'}
        ]
        mock_evaluate.side_effect = [
            {'quality': 'needs_improvement', 'quality_score': 0.75, 'should_stop': False, 'feedback': 'Add evidence'},
            {'quality': 'good', 'quality_score': 0.88, 'should_stop': True, 'feedback': 'Looks solid'}
        ]
        mock_client = Mock()

        result = asyncio.run(
            execute_research_loop(
                client=mock_client,
                query="CRISPR gene editing",
                max_iterations=3,
                model="gemini-2.0-flash"
            )
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['pattern'], 'ADK LoopAgent')
        self.assertEqual(result['execution_mode'], 'adk_runner')
        self.assertEqual(result['iterations_run'], 2)
        self.assertEqual(result['final_answer']['answer'], 'Draft 2')
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(mock_evaluate.call_count, 2)


class TestTask2_ParallelAndSequentialAgent(unittest.TestCase):
    """Test Task 2: Implement ParallelAgent workflow in agents/source_gatherer.py"""

    def test_create_source_gathering_workflow_type(self):
        """Test that create_source_gathering_workflow returns a SequentialAgent."""
        workflow = create_source_gathering_workflow(model="gemini-2.0-flash")
        self.assertIsNotNone(workflow, "Workflow should not be None")
        self.assertIsInstance(workflow, SequentialAgent, "Workflow should be a SequentialAgent")
        self.assertEqual(workflow.name, "source_gathering_workflow")

    def test_parallel_fan_out_and_fan_in(self):
        """Test that stage 1 is ParallelAgent (fan-out) and stage 2 is aggregator (fan-in)."""
        workflow = create_source_gathering_workflow(model="gemini-2.0-flash")
        self.assertEqual(len(workflow.sub_agents), 2, "Sequential workflow must have 2 stages")

        parallel_stage = workflow.sub_agents[0]
        aggregator_stage = workflow.sub_agents[1]

        self.assertIsInstance(parallel_stage, ParallelAgent, "Stage 1 must be ParallelAgent")
        self.assertEqual(parallel_stage.name, "parallel_source_searches")
        self.assertEqual(len(parallel_stage.sub_agents), 3, "Parallel stage must have 3 searchers")

        search_agent_types = [type(a) for a in parallel_stage.sub_agents]
        self.assertIn(WebSearchAgent, search_agent_types)
        self.assertIn(ArxivSearchAgent, search_agent_types)
        self.assertIn(ScholarSearchAgent, search_agent_types)

        self.assertIsInstance(aggregator_stage, SourceAggregatorAgent, "Stage 2 must be SourceAggregatorAgent")
        self.assertEqual(aggregator_stage.name, "source_aggregator")

    @patch.object(SourceAggregatorAgent, 'aggregate')
    @patch.object(ScholarSearchAgent, 'search')
    @patch.object(ArxivSearchAgent, 'search')
    @patch.object(WebSearchAgent, 'search')
    def test_source_gathering_adk_runner_execution(self, mock_web, mock_arxiv, mock_scholar, mock_agg):
        """Test that execute_source_gathering runs through ADK Runner concurrently."""
        import asyncio
        mock_web.return_value = {'source_type': 'web', 'total_found': 10, 'results': [{'title': 'Web1'}]}
        mock_arxiv.return_value = {'source_type': 'arxiv', 'total_found': 8, 'results': [{'title': 'Arxiv1'}]}
        mock_scholar.return_value = {'source_type': 'scholar', 'total_found': 7, 'results': [{'title': 'Scholar1'}]}
        mock_agg.return_value = {'total_sources': 25, 'unique_sources': 25, 'top_sources': [{'title': 'Top1'}]}
        mock_client = Mock()

        result = asyncio.run(
            execute_source_gathering(
                client=mock_client,
                query="CRISPR agriculture",
                model="gemini-2.0-flash"
            )
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['pattern'], 'ADK ParallelAgent + SequentialAgent')
        self.assertEqual(result['execution_mode'], 'adk_runner')
        self.assertEqual(result['aggregated_sources']['total_sources'], 25)
        mock_web.assert_called_once()
        mock_arxiv.assert_called_once()
        mock_scholar.assert_called_once()
        mock_agg.assert_called_once()


class TestTask3_RouterLlmAgent(unittest.TestCase):
    """Test Task 3: Configure LlmAgent in agents/router.py"""

    def test_domain_classifier_initialization(self):
        """Test that DomainClassifierAgent initializes properly as an ADK LlmAgent."""
        agent = DomainClassifierAgent(model="gemini-2.0-flash")
        self.assertIsInstance(agent, LlmAgent, "DomainClassifierAgent must inherit from LlmAgent")
        self.assertEqual(agent.name, "domain_classifier")
        self.assertEqual(agent.model, "gemini-2.0-flash")
        self.assertIsNotNone(agent.generate_content_config)
        self.assertEqual(agent.generate_content_config.response_mime_type, "application/json")


class TestTask4_OrchestratorWiring(unittest.TestCase):
    """Test Task 4: Connect components together and handle async execution in orchestrator."""

    def test_execute_research_loop_signature_accepts_sources(self):
        """Verify execute_research_loop accepts sources parameter."""
        import inspect
        sig = inspect.signature(execute_research_loop)
        self.assertIn("sources", sig.parameters, "execute_research_loop must accept 'sources' parameter")

    @patch('agents.orchestrator.DomainClassifierAgent')
    @patch('agents.orchestrator.execute_source_gathering', new_callable=AsyncMock)
    @patch('agents.orchestrator.execute_research_loop', new_callable=AsyncMock)
    @patch('agents.orchestrator.FactCheckAgent')
    @patch('agents.orchestrator.SynthesisAgent')
    @patch('agents.orchestrator.CitationAgent')
    def test_wiring_sources_to_research_loop(
        self,
        mock_citation,
        mock_synthesis,
        mock_fact_check,
        mock_research_loop,
        mock_source_gathering,
        mock_classifier
    ):
        """Test that gathered sources from Stage 2 are passed into Stage 3."""
        import asyncio
        from agents.orchestrator import execute_research_workflow

        # Setup mock returns
        mock_classifier.return_value.classify.return_value = {
            'domain': 'biology',
            'confidence': 0.95,
            'complexity': 'high',
            'recommended_sources': ['web', 'arxiv', 'scholar']
        }
        mock_sources_data = {
            'aggregated_sources': {'total_sources': 15, 'top_sources': [{'title': 'CRISPR Paper'}]}
        }
        mock_source_gathering.return_value = mock_sources_data

        mock_research_loop.return_value = {
            'query': 'CRISPR',
            'final_answer': {'answer': 'Detailed answer', 'confidence': 'high'},
            'iterations_run': 2
        }

        mock_fact_check.return_value.check.return_value = {
            'credibility_score': 0.92,
            'verified_claims': ['Claim 1'],
            'questionable_claims': []
        }

        mock_synthesis.return_value.synthesize.return_value = {
            'executive_summary': 'Summary',
            'key_insights': ['Insight 1'],
            'themes': ['Theme 1'],
            'coherence_score': 0.90
        }

        mock_citation.return_value.format_citations.return_value = {
            'total_citations': 8,
            'citation_style': 'APA',
            'bibliography': 'Bibliography entry'
        }

        mock_client = Mock()

        # Run workflow
        result = asyncio.run(
            execute_research_workflow(
                client=mock_client,
                query="Test Query",
                max_iterations=2,
                model="gemini-2.0-flash"
            )
        )

        # Verify Stage 2 sources were passed to execute_research_loop
        mock_research_loop.assert_called_once()
        _, kwargs = mock_research_loop.call_args
        self.assertEqual(kwargs.get('sources'), mock_sources_data, "Stage 2 sources must be passed into Stage 3")


class TestTask5_PerformanceEvaluator(unittest.TestCase):
    """Test Task 5: Implement PerformanceEvaluator metrics in orchestrator."""

    def test_evaluator_metrics_calculation(self):
        """Test that PerformanceEvaluator records and analyzes query metrics."""
        evaluator = PerformanceEvaluator()
        result_data = {
            'quality_score': 0.88,
            'sources_found': 25,
            'iterations': 2,
            'fact_checks': 5,
            'citations_count': 10
        }
        processing_time = 14.5

        evaluator.evaluate_query_result(result_data, processing_time)
        summary = evaluator.analyze_performance()

        self.assertEqual(evaluator.metrics.queries_processed, 1)
        self.assertEqual(summary['performance_score'], 0.88)
        self.assertEqual(summary['health_status'], 'excellent')
        self.assertIn('metrics', summary)
        self.assertEqual(summary['metrics']['total_sources'], 25)
        self.assertEqual(summary['metrics']['total_citations'], 10)


if __name__ == "__main__":
    unittest.main()
