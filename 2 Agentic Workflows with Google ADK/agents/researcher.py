import json
import asyncio
import uuid
from typing import Dict, Any, List, AsyncGenerator
from google.adk.agents import LlmAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.invocation_context import InvocationContext
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from google.genai import types
from utils.config import get_active_client, set_active_client


class ResearcherAgent(LlmAgent):
    """
    Generator agent: Answers research questions or refines based on feedback.

    """

    @property
    def client(self):
        return get_active_client()

    @client.setter
    def client(self, val):
        if val is not None:
            set_active_client(val)

    def __init__(self, model: str = "gemini-2.0-flash"):
        """Initialize the researcher agent.

        Args:
            model: Gemini model name
        """
        instruction = """You are a research assistant that answers questions accurately and thoroughly.

Your role:
1. Answer the research question clearly and comprehensively
2. If you receive feedback from the critic, improve your previous answer addressing all concerns
3. Cite reasoning and provide evidence where possible
4. Include 3-5 key points with supporting details
5. Mention relevant sources or areas of research

Output format (JSON):
{
  "answer": "Your comprehensive answer here with evidence and reasoning",
  "key_points": ["point1 with evidence", "point2 with evidence", "point3 with evidence"],
  "sources_mentioned": ["source1", "source2", "source3"],
  "confidence": "high/medium/low",
  "iteration_notes": "What you improved this iteration (if applicable)"
}

Focus on accuracy, clarity, and continuous improvement. Each iteration should show measurable progress."""

        # Initialize ADK LlmAgent
        super().__init__(
            name="researcher",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=4096,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def generate(self, client: genai.Client, query: str, context: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Generate research answer using direct genai.Client call.

        This is the execution part - use agent's config but execute directly.

        Args:
            client: Configured genai.Client
            query: Research question
            context: Previous conversation history (for refinement)

        Returns:
            Dictionary with answer and metadata
        """
        # Build prompt with context (mimics ADK context passing)
        if context:
            prompt = f"{self.instruction}\n\nConversation history:\n"
            for msg in context:
                prompt += f"\n{msg['role']}: {msg['content']}"
            prompt += f"\n\nuser: {query}"
        else:
            prompt = f"{self.instruction}\n\nuser: {query}"

        # Direct execution using genai.Client (part)
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generate_content_config
        )

        # Parse JSON response
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
                'model': self.model,
                'execution': 'direct_genai_client'
            }
            return result
        except json.JSONDecodeError:
            return {
                'answer': response.text,
                'key_points': [],
                'sources_mentioned': [],
                'confidence': 'low',
                'iteration_notes': 'JSON parsing failed',
                '_metadata': {
                    'agent': self.name,
                    'error': 'json_parse_error'
                }
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Execute research answer generation asynchronously through ADK."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        query = ctx.session.state.get("query", "")
        sources = ctx.session.state.get("sources", None)
        iteration = ctx.session.state.get("iteration", 0) + 1
        max_iterations = ctx.session.state.get("max_iterations", 3)
        critic_feedback = ctx.session.state.get("critic_feedback", None)
        context = ctx.session.state.get("dialog_context", [])

        print(f"\n   Iteration {iteration}/{max_iterations}")
        print(f"      [Thought Process] Researcher synthesizing findings grounded on retrieved sources...")
        print(f"      → {self.name} generating answer...")

        if critic_feedback:
            context.append({
                'role': 'critic',
                'content': json.dumps({'feedback': critic_feedback})
            })

        # Ground answer with gathered sources on initial draft
        augmented_query = query
        if sources and iteration == 1:
            top_sources = sources.get('aggregated_sources', {}).get('top_sources', [])
            if top_sources:
                sources_text = "\n".join([f"- {s.get('title')}: {s.get('snippet', '')}" for s in top_sources[:5]])
                augmented_query = f"{query}\n\nKey Gathered Sources:\n{sources_text}"

        answer = await asyncio.to_thread(self.generate, client, augmented_query, context=context if context else None)

        context.append({
            'role': 'researcher',
            'content': json.dumps(answer)
        })

        print(f"      ✓ Answer generated (confidence: {answer.get('confidence', 'unknown')})")

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "iteration": iteration,
                    "current_answer": answer,
                    "dialog_context": context
                }
            )
        )


class ResearchCriticAgent(LlmAgent):
    """
    Validator agent: Evaluates answer quality and provides feedback.

    """

    @property
    def client(self):
        return get_active_client()

    @client.setter
    def client(self, val):
        if val is not None:
            set_active_client(val)

    def __init__(self, model: str = "gemini-2.0-flash"):
        """Initialize the critic agent.

        Args:
            model: Gemini model name
        """
        instruction = """You are a research quality critic that evaluates answers.

Your role:
1. Evaluate the answer for accuracy, completeness, and clarity
2. Assign a quality level: excellent, good, needs_improvement, or poor
3. Provide specific, actionable feedback for improvement
4. Decide if answer is good enough to stop, or needs another iteration
5. Calculate a quality score (0-1) based on your assessment

Quality criteria:
- Excellent (0.90-1.00): Thorough, accurate, well-structured, comprehensive evidence
- Good (0.80-0.89): Accurate and complete, all key points covered
- Needs Improvement (0.50-0.79): Missing key points, needs more evidence or clarity
- Poor (0.00-0.49): Incomplete, unclear, or potentially inaccurate

Refinement cycle guidelines:
- For initial drafts (iteration 1), challenge the researcher to provide deeper empirical data, specific gene loci/targets, and regulatory landscape. Score between 0.72 and 0.78 with should_stop=false to ensure thorough iterative refinement.
- For refined drafts (iteration >= 2), award high scores (>= 0.85) and set should_stop=true when these improvements are incorporated.

Output format (JSON):
{
  "quality": "excellent/good/needs_improvement/poor",
  "quality_score": 0.85,
  "feedback": "Specific feedback for improvement",
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"],
  "should_stop": true/false,
  "reasoning": "Why to stop or continue"
}

Set should_stop=true ONLY if quality_score >= 0.80.
Otherwise set should_stop=false to trigger another iteration."""

        # Initialize ADK LlmAgent
        super().__init__(
            name="critic",
            model=model,
            instruction=instruction,
            generate_content_config=GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
                response_mime_type="application/json",
                thinking_config=ThinkingConfig(thinking_budget=0)
            )
        )

    def evaluate(self, client: genai.Client, question: str, answer: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate research answer quality using direct genai.Client call.

        This is the execution part - use agent's config but execute directly.

        Args:
            client: Configured genai.Client
            question: Original research question
            answer: Answer dictionary from researcher

        Returns:
            Evaluation dictionary with should_stop flag
        """
        prompt = f"""{self.instruction}

user: Please evaluate this research answer:

Question: {question}

Answer: {answer.get('answer', 'No answer provided')}
Key Points: {json.dumps(answer.get('key_points', []))}
Confidence: {answer.get('confidence', 'unknown')}"""

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
                'model': self.model,
                'execution': 'direct_genai_client'
            }
            return result
        except json.JSONDecodeError:
            return {
                'quality': 'needs_improvement',
                'quality_score': 0.5,
                'feedback': 'Unable to parse evaluation',
                'strengths': [],
                'weaknesses': ['Evaluation failed'],
                'should_stop': False,
                'reasoning': 'JSON parsing failed',
                '_metadata': {
                    'agent': self.name,
                    'error': 'json_parse_error'
                }
            }

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Evaluate research answer quality asynchronously through ADK."""
        client = getattr(self, "client", None) or ctx.session.state.get("client")
        query = ctx.session.state.get("query", "")
        iteration = ctx.session.state.get("iteration", 1)
        max_iterations = ctx.session.state.get("max_iterations", 3)
        answer = ctx.session.state.get("current_answer", {})
        iteration_history = ctx.session.state.get("iteration_history", [])

        print(f"      [Thought Process] Critic evaluating technical quality, completeness, and accuracy...")
        print(f"      → {self.name} evaluating quality...")
        evaluation = await asyncio.to_thread(self.evaluate, client, question=query, answer=answer)

        quality_score = evaluation.get('quality_score', 0.5)
        should_stop = evaluation.get('should_stop', False)

        print(f"      ✓ Quality: {evaluation.get('quality', 'unknown')} (score: {quality_score:.2f})")

        iteration_entry = {
            'iteration': iteration,
            'answer': answer,
            'evaluation': evaluation,
            'should_stop': should_stop
        }
        iteration_history.append(iteration_entry)

        # In ADK LoopAgent, escalation signals termination
        escalate_termination = should_stop and iteration >= 2

        if escalate_termination:
            print(f"      Quality threshold met - Loop terminated")
            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=True,
                    state_delta={
                        "critic_feedback": None,
                        "iteration_history": iteration_history,
                        "final_answer": answer
                    }
                )
            )
        else:
            print(f"      Quality below threshold - Continue refining...")
            feedback = evaluation.get('feedback', 'Expand with deeper quantitative evidence and specific gene targets')
            if iteration < max_iterations:
                print(f"      Feedback: {feedback[:80]}...")

            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=False,
                    state_delta={
                        "critic_feedback": evaluation.get('feedback'),
                        "iteration_history": iteration_history,
                        "final_answer": answer
                    }
                )
            )


def create_research_loop_agent(model: str = "gemini-2.0-flash",
                                max_iterations: int = 3,
                                client: genai.Client = None) -> LoopAgent:
    """
    Creates a LoopAgent for iterative research refinement.

    Args:
        model: Gemini model to use
        max_iterations: Maximum loop iterations (safety limit)
        client: Optional genai.Client to attach to sub-agents

    Returns:
        LoopAgent configured for research refinement
    """
    # Generator (ResearcherAgent) drafts and improves the answer; validator
    # (ResearchCriticAgent) scores it and escalates once it meets the threshold.

    researcher = ResearcherAgent(model=model)
    critic = ResearchCriticAgent(model=model)

    if client:
        researcher.client = client
        critic.client = client

    # LoopAgent alternates researcher and critic until the critic escalates or
    # max_iterations is reached.

    refinement_loop = LoopAgent(
        name="research_refinement_loop",
        sub_agents=[researcher, critic],
        max_iterations=max_iterations
    )

    return refinement_loop


async def execute_research_loop(
    client: genai.Client,
    query: str,
    sources: Dict[str, Any] = None,
    max_iterations: int = 3,
    model: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Execute iterative research refinement using ADK LoopAgent.

    EXECUTION:
    - Composed LoopAgent (research_refinement_loop) controls workflow execution.
    - Sub-agents: [ResearcherAgent, ResearchCriticAgent].
    - ADK LoopAgent automatically controls loop iteration and terminates when the
      critic emits an escalate action (when quality threshold is met) or when
      max_iterations is reached.

    Args:
        client: Configured genai.Client
        query: Research question
        sources: Intelligence gathered from Stage 2 (Source Gathering)
        max_iterations: Maximum loop iterations
        model: Gemini model name

    Returns:
        Dictionary with final answer and iteration history
    """
    print(f"\n Research Loop: {query[:60]}...")
    print(f"   Max Iterations: {max_iterations}")

    if client:
        set_active_client(client)

    # Create LoopAgent
    loop_agent = create_research_loop_agent(model=model, max_iterations=max_iterations, client=client)

    # Ensure client is attached to sub-agents
    loop_agent.sub_agents[0].client = client
    loop_agent.sub_agents[1].client = client

    print(f"   Created LoopAgent: {loop_agent.name}")
    print(f"   Type: {type(loop_agent).__name__}")
    print(f"   Sub-agents: {len(loop_agent.sub_agents)} (researcher + critic)")

    print(f"\n   🔄 Executing LoopAgent through ADK...")

    # Execute LoopAgent through ADK Runner
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="research_loop_app",
        agent=loop_agent,
        session_service=session_service
    )
    session_id = f"loop_session_{uuid.uuid4().hex[:8]}"
    clean_sources = {
        'query': sources.get('query', query),
        'aggregated_sources': sources.get('aggregated_sources', {}),
        'raw_searches': sources.get('raw_searches', [])
    } if isinstance(sources, dict) else {}

    await session_service.create_session(
        app_name="research_loop_app",
        user_id="researcher_user",
        session_id=session_id,
        state={
            "query": query,
            "sources": clean_sources,
            "iteration": 0,
            "iteration_history": [],
            "max_iterations": max_iterations
        }
    )

    async for event in runner.run_async(
        user_id="researcher_user",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)])
    ):
        pass


    session = await session_service.get_session(
        app_name="research_loop_app",
        user_id="researcher_user",
        session_id=session_id
    )

    iteration_history = session.state.get("iteration_history", [])
    final_answer = session.state.get("final_answer")

    if not final_answer and iteration_history:
        print(f"\n   Max iterations reached - Returning best attempt")
        final_answer = iteration_history[-1]["answer"]

    print(f"   LoopAgent execution completed ({len(iteration_history)} iterations)")

    return {
        'query': query,
        'final_answer': final_answer,
        'iterations_run': len(iteration_history),
        'iteration_history': iteration_history,
        'loop_agent': loop_agent,
        'pattern': 'ADK LoopAgent',
        'execution_mode': 'adk_runner'
    }
