"""
Legal Intelligence Agent System - Core Agent Implementation
===========================================================
Orchestrates the specialized personas: connects to Vertex AI through the
google-genai SDK, generates each report section with retry logic and token/cost
tracking, chains context between sections and validates quality before
assembling the final report.
"""

import os
import time
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

# Google AI imports
import vertexai
from vertexai.generative_models import GenerativeModel
from google import genai
from google.genai import types

# Internal imports
from ..models.legal_models import (
    LegalScenario,
    AnalysisReport,
    AgentResponse,
    ReportSection,
    TokenUsage
)
from ..prompts.personas import LegalPersonas
from .quality_validator import QualityValidator, QualityScore

logger = logging.getLogger(__name__)

# Vertex AI list prices in USD per 1M tokens (input, output) for prompts up to
# 200k tokens; thinking tokens are billed as output. Unknown models fall back to
# DEFAULT_PRICING, the example rates the project shipped with.
MODEL_PRICING = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
}
DEFAULT_PRICING = (0.25, 1.25)


class _VertexAISession:
    """
    google-genai client behind the classic ``vertexai.init()`` entry point.

    The module (and its test-suite) talks to Vertex AI through
    ``vertexai.init(project=..., location=...)`` and
    ``GenerativeModel(name).generate_content(...)``; underneath it is the
    google-genai client from requirements.txt, so no legacy SDK is needed.
    """

    def __init__(self):
        self.client: Optional[genai.Client] = None
        self.project: Optional[str] = None
        self.location: Optional[str] = None

    def init(self, project: str, location: str) -> genai.Client:
        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.project = project
        self.location = location
        return self.client


vertexai = _VertexAISession()


class GenerativeModel:
    """Handle for one model name over ``vertexai.client.models.generate_content``."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate_content(self, contents: Any, config: Optional[types.GenerateContentConfig] = None):
        if vertexai.client is None:
            raise RuntimeError("vertexai.init() must be called before generating content")
        return vertexai.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=config,
        )


class LegalIntelligenceAgent:
    """
    Main orchestrator for the Legal Intelligence AI System.

    - Connects to Vertex AI (``initialize_vertex_ai``)
    - Generates one section at a time with retries and cost tracking
      (``generate_section_content``)
    - Chains sections, validates quality and assembles the report
      (``generate_complete_report``)
    """

    def __init__(self, project_id: str, location: str = "us-central1", model_name: str = "gemini-2.5-flash"):
        """Initialize the Legal Intelligence Agent system."""
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.model = None
        self.client = None
        self.model = None
        self.initialized = False

        # Components
        self.personas = LegalPersonas()
        self.quality_validator = QualityValidator()

        # Performance tracking
        self.token_usage_history = []
        self.processing_times = []
        self.success_count = 0
        self.total_attempts = 0

        # Configuration. Gemini 2.5 thinking tokens count against
        # max_output_tokens, so the budget is capped to keep room for the answer.
        thinking_config = (
            types.ThinkingConfig(thinking_budget=1024)
            if model_name.startswith("gemini-2.5") else None
        )
        self.generation_config = types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.95,
            top_k=40,
            max_output_tokens=4096,
            thinking_config=thinking_config,
        )

        self.input_price, self.output_price = self._pricing_for(model_name)

        logger.info(f"LegalIntelligenceAgent initialized for project {project_id}")

    def initialize_vertex_ai(self) -> bool:
        """
        Initialize Vertex AI and create the model instance.

        Opens the Gen AI client for the configured project/location, creates the
        model handle and verifies the connection with a one-word prompt. Returns
        True on success; failures are logged and reported as False so the caller
        decides how to degrade.
        """
        try:
            logger.info(f"Initializing Vertex AI for project: {self.project_id}")

            if not self.project_id:
                raise ValueError("A Google Cloud project id is required")

            self.client = vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)

            response = self.model.generate_content(
                "Reply with the single word OK.",
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=256),
            )
            if response is None:
                raise RuntimeError("Vertex AI returned no response to the connection test")

            reply = (getattr(response, "text", None) or "").strip()
            if reply:
                logger.info(
                    f"Vertex AI connection verified (model={self.model_name}, "
                    f"location={self.location}, reply={reply[:20]!r})"
                )
            else:
                logger.warning(
                    f"Vertex AI reachable but the connection test returned no text "
                    f"(model={self.model_name})"
                )

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {str(e)}")
            self.initialized = False
            return False

    def generate_section_content(
        self,
        persona: str,
        section_type: str,
        scenario: LegalScenario,
        previous_sections: List[ReportSection] = None
    ) -> Tuple[str, TokenUsage, float]:
        """
        Generate content for a specific report section.

        Builds the prompt from persona, scenario and previous sections, calls the
        model with exponential backoff (2^attempt seconds, 3 attempts) and tracks
        token usage, cost, latency and success rate.

        Args:
            persona: The agent persona text (from personas.py)
            section_type: Type of section (e.g., "liability_assessment")
            scenario: The legal case to analyze
            previous_sections: Previous sections for context chaining

        Returns:
            Tuple of (content, token_usage, cost)

        Raises:
            RuntimeError: if the agent is not initialized or every attempt fails
        """
        if not self.initialized:
            raise RuntimeError("Agent system not initialized. Call initialize_vertex_ai() first.")

        start_time = time.time()
        previous_sections = previous_sections or []

        # Build the comprehensive prompt
        prompt = self._build_prompt(persona, section_type, scenario, previous_sections)

        max_retries = 3
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            self.total_attempts += 1
            try:
                logger.info(f"Generating {section_type} (attempt {attempt + 1}/{max_retries})")
                response = self.model.generate_content(prompt, config=self.generation_config)

                content = (getattr(response, "text", None) or "").strip()
                finish_reason = self._finish_reason(response)
                if not content:
                    raise ValueError(f"Model returned no text (finish reason: {finish_reason})")
                if "MAX_TOKENS" in finish_reason:
                    logger.warning(f"{section_type} was truncated at max_output_tokens")

                token_usage = self._token_usage_from(response)
                cost = self._calculate_cost(token_usage)
                elapsed = time.time() - start_time

                self.token_usage_history.append(token_usage)
                self.processing_times.append(elapsed)
                self.success_count += 1
                logger.info(
                    f"Generated {section_type}: {token_usage.total_tokens} tokens, "
                    f"${cost:.4f}, {elapsed:.1f}s"
                )
                return content, token_usage, cost

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/{max_retries} for {section_type} failed: {str(e)}")
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt
                    logger.info(f"Retrying {section_type} in {backoff}s")
                    time.sleep(backoff)

        raise RuntimeError(
            f"Content generation for {section_type} failed after {max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _finish_reason(response: Any) -> str:
        try:
            return str(response.candidates[0].finish_reason)
        except Exception:
            return "unknown"

    @staticmethod
    def _token_usage_from(response: Any) -> TokenUsage:
        """Read token counts from response.usage_metadata; missing counts become 0."""
        usage = getattr(response, "usage_metadata", None)

        def count(field: str) -> int:
            value = getattr(usage, field, None)
            return value if isinstance(value, int) else 0

        input_tokens = count("prompt_token_count")
        output_tokens = count("candidates_token_count")
        total_tokens = count("total_token_count") or (input_tokens + output_tokens)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    async def generate_complete_report(self, scenario: LegalScenario) -> AnalysisReport:
        """
        Generate a complete analysis report.

        Runs the six sections in sequence, each with the persona that owns it,
        passing the sections already written as context. Every section is scored
        by the quality validator; a section below the threshold is regenerated
        once with the validator's feedback and the better draft is kept. A
        section that still fails after the retries is included as a failed
        placeholder (score 0) so the rest of the report survives, and the report
        is marked partial in its metadata.
        """
        logger.info(f"Starting complete report generation for case: {scenario.case_name}")
        start_time = time.time()

        if not self.initialized:
            raise RuntimeError("Agent system not initialized. Call initialize_vertex_ai() first.")

        section_config = [
            ("liability_assessment", "business_analyst"),
            ("damage_calculation", "business_analyst"),
            ("prior_art_analysis", "market_researcher"),
            ("competitive_landscape", "market_researcher"),
            ("risk_assessment", "strategic_consultant"),
            ("strategic_recommendations", "strategic_consultant"),
        ]
        threshold = self.quality_validator.min_quality_threshold

        sections: List[ReportSection] = []
        context_sections: List[ReportSection] = []
        total_cost = 0.0
        total_tokens = 0
        input_tokens = 0
        output_tokens = 0
        retried: List[str] = []
        failed: List[str] = []
        context_chain: Dict[str, List[str]] = {}

        for section_type, persona_type in section_config:
            persona = self.personas.get_persona(persona_type)
            expected_elements = self._get_expected_elements(section_type)
            context_chain[section_type] = [s.type for s in context_sections[-2:]]
            section_tokens = 0
            section_cost = 0.0

            try:
                content, usage, cost = await asyncio.to_thread(
                    self.generate_section_content, persona, section_type, scenario, context_sections
                )
                section_tokens, section_cost = usage.total_tokens, cost
                input_tokens += usage.input_tokens
                output_tokens += usage.output_tokens
                quality = self.quality_validator.validate_section(content, section_type, expected_elements)

                if quality.overall_score < threshold:
                    logger.warning(
                        f"{section_type} scored {quality.overall_score:.2f} < {threshold:.2f}; "
                        f"regenerating with validator feedback"
                    )
                    retried.append(section_type)
                    try:
                        retry_content, retry_usage, retry_cost = await asyncio.to_thread(
                            self.generate_section_content,
                            self._persona_with_feedback(persona, quality, threshold),
                            section_type, scenario, context_sections
                        )
                    except Exception as retry_error:
                        logger.warning(f"Regeneration of {section_type} failed, keeping first draft: {retry_error}")
                    else:
                        section_tokens += retry_usage.total_tokens
                        section_cost += retry_cost
                        input_tokens += retry_usage.input_tokens
                        output_tokens += retry_usage.output_tokens
                        retry_quality = self.quality_validator.validate_section(
                            retry_content, section_type, expected_elements
                        )
                        if retry_quality.overall_score >= quality.overall_score:
                            content, quality = retry_content, retry_quality

                quality_score = quality.overall_score
                logger.info(f"{section_type} accepted with quality {quality_score:.2f}")

            except Exception as e:
                logger.error(f"{section_type} could not be generated: {str(e)}")
                failed.append(section_type)
                content = (
                    f"[GENERATION FAILED] {self._get_section_title(section_type)} is unavailable "
                    f"in this report: {str(e)}"
                )
                quality_score = 0.0

            section = ReportSection(
                type=section_type,
                title=self._get_section_title(section_type),
                content=content,
                agent_type=persona_type,
                quality_score=quality_score,
                tokens_used=section_tokens,
                cost=section_cost,
                timestamp=datetime.now().isoformat()
            )
            sections.append(section)
            if section_type not in failed:
                context_sections.append(section)
            total_tokens += section_tokens
            total_cost += section_cost

        if len(failed) == len(section_config):
            raise RuntimeError("Report generation failed: no section could be generated")

        processing_time = time.time() - start_time
        confidence_score = sum(s.quality_score for s in sections) / len(sections)

        report = AnalysisReport(
            scenario=scenario,
            sections=sections,
            executive_summary=self._generate_executive_summary(sections, scenario),
            total_cost=round(total_cost, 6),
            total_tokens=total_tokens,
            processing_time=round(processing_time, 2),
            confidence_score=round(confidence_score, 4),
            timestamp=datetime.now().isoformat(),
            metadata={
                "model": self.model_name,
                "location": self.location,
                "quality_threshold": threshold,
                "sections_generated": len(sections) - len(failed),
                "sections_retried": retried,
                "sections_failed": failed,
                "partial": bool(failed),
                "context_chain": context_chain,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )

        logger.info(
            f"Report complete for {scenario.case_name}: {len(sections)} sections "
            f"({len(failed)} failed, {len(retried)} retried), {total_tokens} tokens, "
            f"${total_cost:.4f}, {processing_time:.1f}s, confidence {confidence_score:.2f}"
        )
        return report

    def _persona_with_feedback(self, persona: str, quality: QualityScore, threshold: float) -> str:
        """Persona plus the validator's feedback, used to regenerate a weak section."""
        feedback = "\n".join(f"- {item}" for item in quality.feedback)
        if not feedback:
            feedback = "- Provide deeper, better structured analysis"
        return (
            f"{persona}\n\nQUALITY REVIEW OF YOUR PREVIOUS DRAFT "
            f"(score {quality.overall_score:.2f}, minimum {threshold:.2f}):\n{feedback}\n"
            "Rewrite the section from scratch and fix every point above: use several "
            "paragraphs with headings, numbered steps, explicit reasoning ('because', "
            "'based on') and the domain terminology the section requires."
        )

    def _build_prompt(
        self,
        persona: str,
        section_type: str,
        scenario: LegalScenario,
        previous_sections: List[ReportSection]
    ) -> str:
        """Build a comprehensive prompt combining persona, context, and chain-of-thought instructions."""

        # Start with the persona
        prompt = persona + "\n\n"

        # Add chain-of-thought reasoning instructions
        prompt += """
REASONING INSTRUCTIONS:
You must use step-by-step reasoning to analyze this legal case. Structure your analysis as follows:
1. First, identify the key legal issues
2. Second, analyze the relevant facts
3. Third, apply legal principles
4. Finally, provide your conclusions

Think through each step carefully before moving to the next.
Write 400-700 words for this section, using headings, short paragraphs and lists;
finish with a clear conclusion. Do not invent case citations, patent numbers or
figures that are not supported by the facts provided; label estimates as such.
"""

        # Add context from previous sections if available
        if previous_sections:
            prompt += "\n\nPREVIOUS ANALYSIS:\n"
            for section in previous_sections[-2:]:  # Include last 2 sections for context
                prompt += f"\n{section.title}:\n"
                prompt += f"{section.content[:500]}...\n"  # Include summary

        # Add the specific task
        prompt += f"\n\nTASK: Provide a {section_type.replace('_', ' ')} for the following legal case:\n\n"

        # Add case details
        prompt += f"Case Name: {scenario.case_name}\n"
        prompt += f"Case Type: {scenario.case_type}\n"
        prompt += f"Key Issues: {', '.join(scenario.key_issues)}\n"
        prompt += f"Urgency: {scenario.urgency_level}\n"
        if scenario.parties_involved:
            prompt += f"Parties: {', '.join(scenario.parties_involved)}\n"
        prompt += f"\nComplaint Summary:\n{scenario.complaint_text[:1500]}\n\n"
        if scenario.additional_context:
            prompt += f"Additional Context:\n{scenario.additional_context}\n\n"

        # Add section-specific instructions
        prompt += self._get_section_instructions(section_type)

        return prompt

    def _get_section_instructions(self, section_type: str) -> str:
        """Get specific instructions for each section type."""
        instructions = {
            "liability_assessment": """
Analyze liability by:
- Identifying each potential claim
- Evaluating strength of evidence
- Assessing probability of success (use percentages)
- Citing relevant precedents or legal principles
""",
            "damage_calculation": """
Calculate potential damages by:
- Identifying categories of damages (actual, statutory, punitive)
- Providing specific dollar ranges
- Explaining calculation methodology
- Considering mitigation factors
""",
            "prior_art_analysis": """
Analyze prior art and precedents by:
- Identifying relevant existing patents/IP
- Assessing validity challenges
- Evaluating obviousness arguments
- Determining freedom to operate
""",
            "competitive_landscape": """
Analyze competitive implications by:
- Identifying key competitors affected
- Assessing market position changes
- Evaluating licensing opportunities
- Predicting competitor responses
""",
            "risk_assessment": """
Assess risks by:
- Identifying legal risks (probability and impact)
- Evaluating business risks
- Analyzing reputational risks
- Providing risk mitigation strategies
""",
            "strategic_recommendations": """
Provide strategic recommendations by:
- Outlining 3-5 specific action items
- Prioritizing by impact and urgency
- Estimating resource requirements
- Defining success metrics
"""
        }
        return instructions.get(section_type, "Provide comprehensive analysis for this section.")

    def _get_expected_elements(self, section_type: str) -> List[str]:
        """Get expected elements for quality validation."""
        elements_map = {
            "liability_assessment": ["claims", "evidence", "probability", "precedent"],
            "damage_calculation": ["damages", "calculation", "amount", "methodology"],
            "prior_art_analysis": ["patents", "prior art", "validity", "obviousness"],
            "competitive_landscape": ["competitors", "market", "position", "licensing"],
            "risk_assessment": ["risks", "probability", "impact", "mitigation"],
            "strategic_recommendations": ["recommendations", "action", "timeline", "resources"]
        }
        return elements_map.get(section_type, ["analysis", "assessment", "conclusion"])

    def _get_section_title(self, section_type: str) -> str:
        """Get formatted title for section."""
        titles = {
            "liability_assessment": "Liability Assessment",
            "damage_calculation": "Damage Calculation",
            "prior_art_analysis": "Prior Art Analysis",
            "competitive_landscape": "Competitive Landscape",
            "risk_assessment": "Risk Assessment",
            "strategic_recommendations": "Strategic Recommendations"
        }
        return titles.get(section_type, section_type.replace("_", " ").title())

    def _get_agent_type(self, persona: str) -> str:
        """Determine agent type from persona text."""
        if "Business Analyst" in persona:
            return "business_analyst"
        elif "Market Research" in persona:
            return "market_researcher"
        elif "Strategic" in persona:
            return "strategic_consultant"
        else:
            return "unknown"

    def _generate_executive_summary(self, sections: List[ReportSection], scenario: LegalScenario) -> str:
        """Generate executive summary from all sections."""
        summary = f"EXECUTIVE SUMMARY - {scenario.case_name}\n"
        summary += "=" * 50 + "\n\n"

        # Extract key points from each section
        for section in sections:
            # Get first substantive paragraph
            paragraphs = [p.strip() for p in section.content.split('\n\n') if len(p.strip()) > 50]
            if paragraphs:
                summary += f"{section.title}:\n"
                summary += f"{paragraphs[0][:200]}...\n\n"

        # Add overall assessment
        avg_quality = sum(s.quality_score for s in sections) / len(sections) if sections else 0
        summary += f"Overall Confidence: {avg_quality:.1%}\n"
        summary += f"Key Issues Identified: {len(scenario.key_issues)}\n"
        summary += f"Urgency Level: {scenario.urgency_level}\n"

        return summary

    def _calculate_cost(self, token_usage: TokenUsage) -> float:
        """Calculate cost in USD; thinking tokens (total - input - output) are billed as output."""
        billable_output = max(token_usage.total_tokens - token_usage.input_tokens, token_usage.output_tokens)
        return (token_usage.input_tokens * self.input_price + billable_output * self.output_price) / 1_000_000

    @staticmethod
    def _pricing_for(model_name: str) -> Tuple[float, float]:
        for prefix, rates in sorted(MODEL_PRICING.items(), key=lambda item: -len(item[0])):
            if model_name.startswith(prefix):
                return rates
        logger.warning(f"No price list for model {model_name}; costs use the default example rates")
        return DEFAULT_PRICING

    # Metric tracking methods

    def get_token_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics."""
        if not self.token_usage_history:
            return {"error": "No usage data available"}

        total_input = sum(u.input_tokens for u in self.token_usage_history)
        total_output = sum(u.output_tokens for u in self.token_usage_history)
        total_tokens = sum(u.total_tokens for u in self.token_usage_history)

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "average_per_request": total_tokens / len(self.token_usage_history) if self.token_usage_history else 0,
            "request_count": len(self.token_usage_history)
        }

    def get_avg_processing_time(self) -> float:
        """Get average processing time."""
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times)

    def get_success_rate(self) -> float:
        """Get success rate of generations."""
        if self.total_attempts == 0:
            return 0.0
        return self.success_count / self.total_attempts