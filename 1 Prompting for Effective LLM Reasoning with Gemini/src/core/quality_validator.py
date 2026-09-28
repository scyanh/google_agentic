"""
Quality Validation System for Legal Intelligence AI
===================================================
Heuristic scoring of AI-generated legal analysis: coherence (structure and
logical flow), groundedness (domain terminology and evidence-based reasoning),
completeness and structure, combined into a weighted score with feedback that
drives regeneration of weak sections.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import statistics

from ..models.legal_models import AnalysisReport, ReportSection

logger = logging.getLogger(__name__)

LOGICAL_CONNECTORS = [
    "therefore", "however", "furthermore", "moreover", "additionally", "consequently",
    "thus", "hence", "as a result", "in addition", "nevertheless", "nonetheless",
    "accordingly", "because", "whereas", "in contrast", "on the other hand",
    "for example", "for instance", "specifically", "notably", "similarly", "conversely",
    "ultimately", "given that", "in particular",
]

# Ordinal words, numbered or bulleted lists and markdown headings (multiline regexes)
STRUCTURE_MARKERS = [
    r"\bfirst(ly)?\b", r"\bsecond(ly)?\b", r"\bthird(ly)?\b", r"\bfinally\b", r"\blastly\b",
    r"\bin conclusion\b", r"\bto conclude\b", r"\bin summary\b", r"\bstep \d",
    r"^\s*\d+[.)]\s+\S", r"^\s*[-•*]\s+\S", r"^\s*#{1,6}\s+\S",
]

REASONING_INDICATORS = [
    "based on", "because", "due to", "as a result", "therefore", "according to",
    "given that", "this suggests", "indicates", "supported by", "in light of",
    "consequently", "demonstrates", "evidence", "precedent", "pursuant to",
    "for example", "specifically", "the record shows", "analysis shows", "under the",
]

# Dollar amounts, percentages, thousands separators or spelled-out magnitudes
QUANTITATIVE_EVIDENCE = re.compile(
    r"\$\s?\d|\d+(?:\.\d+)?\s?%|\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand)\b",
    re.IGNORECASE,
)

SECTION_KEYWORDS = {
    "liability_assessment": [
        "liability", "negligence", "breach", "duty", "causation", "infringement", "claim",
        "evidence", "precedent", "defendant", "plaintiff", "willful", "statute",
        "standard of care", "burden of proof",
    ],
    "damage_calculation": [
        "damages", "compensation", "calculation", "quantum", "lost profits", "reasonable royalty",
        "price erosion", "actual damages", "statutory", "punitive", "treble", "mitigation",
        "revenue", "methodology", "$",
    ],
    "prior_art_analysis": [
        "prior art", "patent", "novelty", "obviousness", "validity", "claim", "reference",
        "anticipat", "§ 102", "§ 103", "filing date", "priority date", "freedom to operate",
        "invalid", "uspto",
    ],
    "competitive_landscape": [
        "competitor", "market share", "positioning", "competitive", "licensing", "market",
        "industry", "substitute", "barrier", "differentiation", "pricing", "customer",
        "advantage", "entrant", "porter",
    ],
    "risk_assessment": [
        "risk", "probability", "impact", "mitigation", "likelihood", "exposure", "severity",
        "contingency", "reputational", "regulatory", "uncertainty", "worst case", "scenario",
        "matrix", "tolerance",
    ],
    "strategic_recommendations": [
        "recommend", "strategy", "strategic", "implementation", "action", "priority", "timeline",
        "settlement", "negotiat", "resource", "milestone", "roadmap", "objective",
        "success metric", "stakeholder", "return on investment",
    ],
}
GENERIC_KEYWORDS = ["analysis", "assessment", "conclusion", "evidence", "finding", "issue"]


@dataclass
class QualityScore:
    """Quality score with detailed breakdown."""
    overall_score: float
    coherence_score: float
    groundedness_score: float
    completeness_score: float
    structure_score: float
    feedback: List[str]


@dataclass
class ValidationResult:
    """Validation result for a report."""
    overall_score: float
    passed: bool
    section_scores: Dict[str, float]
    issues: List[str]
    recommendations: List[str]


class QualityValidator:
    """
    Validates the quality of AI-generated legal analysis.

    Each section gets four component scores (coherence, groundedness,
    completeness, structure) combined into a weighted overall score, plus
    feedback strings that the agent feeds back into a regeneration prompt.
    """

    def __init__(self, min_quality_threshold: float = 0.7):
        """Initialize the quality validator."""
        self.min_quality_threshold = min_quality_threshold
        self.validation_history = []

    def validate_section(
        self,
        content: str,
        section_type: str,
        expected_elements: List[str]
    ) -> QualityScore:
        """Validate a single report section."""

        # Calculate individual scores
        coherence = self.calculate_coherence_score(content, section_type)
        groundedness = self.calculate_groundedness_score(content, section_type, expected_elements)
        completeness = self._calculate_completeness_score(content, expected_elements)
        structure = self._calculate_structure_score(content)

        # Calculate overall score (weighted average)
        overall = (
            coherence * 0.3 +
            groundedness * 0.3 +
            completeness * 0.25 +
            structure * 0.15
        )

        # Generate feedback
        feedback = []
        if coherence < 0.7:
            feedback.append("Improve logical flow and use more transition phrases")
        if groundedness < 0.7:
            feedback.append(f"Include more {section_type}-specific terminology and evidence")
        if completeness < 0.7:
            feedback.append(f"Address all expected elements: {', '.join(expected_elements)}")
        if structure < 0.7:
            feedback.append("Improve paragraph structure and organization")

        return QualityScore(
            overall_score=overall,
            coherence_score=coherence,
            groundedness_score=groundedness,
            completeness_score=completeness,
            structure_score=structure,
            feedback=feedback
        )

    def calculate_coherence_score(self, content: str, section_type: str) -> float:
        """
        Score coherence (0.0-1.0) from structure and logical flow.

        Components: multiple paragraphs (0.3 for three or more, 0.2 for two),
        logical connectors (up to 0.2, saturating at three distinct connectors),
        structured presentation (up to 0.2, saturating at two markers such as
        first/second/finally, numbered lists or headings) and content depth
        (up to 0.3, saturating at eight sentences).
        """
        text = content.strip()
        if not text:
            return 0.0
        lowered = text.lower()
        score = 0.0

        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) >= 3:
            score += 0.3
        elif len(paragraphs) == 2:
            score += 0.2

        connectors = {c for c in LOGICAL_CONNECTORS if re.search(rf"\b{re.escape(c)}\b", lowered)}
        score += 0.2 * min(len(connectors) / 3, 1.0)

        markers = sum(1 for pattern in STRUCTURE_MARKERS if re.search(pattern, lowered, re.MULTILINE))
        score += 0.2 * min(markers / 2, 1.0)

        sentences = self._split_sentences(text)
        score += 0.3 * min(len(sentences) / 8, 1.0)

        logger.debug(
            f"Coherence {section_type}: paragraphs={len(paragraphs)} connectors={len(connectors)} "
            f"markers={markers} sentences={len(sentences)} score={score:.2f}"
        )
        return round(min(score, 1.0), 4)

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split on sentence-ending punctuation or line breaks; keep fragments of two or more words."""
        parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        return [p.strip() for p in parts if len(p.split()) >= 2]

    def calculate_groundedness_score(
        self,
        content: str,
        section_type: str,
        expected_elements: List[str]
    ) -> float:
        """
        Score groundedness (0.0-1.0): domain terminology, evidence-based
        reasoning and coverage of the expected elements.

        Components: section keywords (up to 0.4, saturating at four distinct
        keywords), reasoning indicators such as "based on"/"because" or
        quantified evidence (up to 0.3, saturating at three) and expected
        elements coverage (up to 0.3, proportional). Without expected elements
        the keyword coverage stands in for the last component.
        """
        lowered = content.lower()
        if not lowered.strip():
            return 0.0
        score = 0.0

        keywords = SECTION_KEYWORDS.get(section_type, GENERIC_KEYWORDS)
        keyword_hits = [k for k in keywords if k in lowered]
        keyword_coverage = min(len(keyword_hits) / 4, 1.0)
        score += 0.4 * keyword_coverage

        reasoning_hits = [r for r in REASONING_INDICATORS if r in lowered]
        if QUANTITATIVE_EVIDENCE.search(content):
            reasoning_hits.append("quantified evidence")
        score += 0.3 * min(len(reasoning_hits) / 3, 1.0)

        if expected_elements:
            covered = sum(1 for element in expected_elements if element.lower() in lowered)
            score += 0.3 * covered / len(expected_elements)
        else:
            score += 0.3 * keyword_coverage

        logger.debug(
            f"Groundedness {section_type}: keywords={len(keyword_hits)} reasoning={len(reasoning_hits)} "
            f"expected={expected_elements} score={score:.2f}"
        )
        return round(min(score, 1.0), 4)

    def _calculate_completeness_score(self, content: str, expected_elements: List[str]) -> float:
        """Calculate how completely the content addresses requirements."""
        if not expected_elements:
            # If no specific elements expected, check general completeness
            word_count = len(content.split())
            if word_count >= 200:
                return 1.0
            elif word_count >= 100:
                return 0.7
            elif word_count >= 50:
                return 0.5
            else:
                return 0.3

        # Check coverage of expected elements
        content_lower = content.lower()
        covered_elements = sum(1 for element in expected_elements
                             if element.lower() in content_lower)

        coverage_ratio = covered_elements / len(expected_elements)

        # Also consider content length
        word_count = len(content.split())
        length_score = min(word_count / 200, 1.0)  # Expect at least 200 words

        # Combined score
        return (coverage_ratio * 0.7) + (length_score * 0.3)

    def _calculate_structure_score(self, content: str) -> float:
        """Calculate structural quality of the content."""
        score = 0.0

        # Check for paragraphs
        paragraphs = content.split('\n\n')
        if len(paragraphs) >= 3:
            score += 0.3
        elif len(paragraphs) >= 2:
            score += 0.2
        elif len(paragraphs) >= 1:
            score += 0.1

        # Check for lists or bullet points
        has_lists = any(marker in content for marker in ['•', '-', '*', '1.', '2.', '3.'])
        if has_lists:
            score += 0.2

        # Check for headers or emphasized text
        has_headers = any(line.isupper() or line.startswith('#')
                        for line in content.split('\n') if len(line.strip()) > 0)
        if has_headers:
            score += 0.1

        # Check sentence variety
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 10]
        if len(sentences) >= 3:
            sentence_lengths = [len(s.split()) for s in sentences]
            if len(set(sentence_lengths)) >= 3:  # Variety in sentence length
                score += 0.2

        # Check for conclusion indicators
        conclusion_indicators = ['conclusion', 'summary', 'therefore', 'in summary', 'overall']
        has_conclusion = any(indicator in content.lower() for indicator in conclusion_indicators)
        if has_conclusion:
            score += 0.2

        return min(score, 1.0)

    def validate_report(self, report: AnalysisReport) -> ValidationResult:
        """Validate a complete report."""
        section_scores = {}
        all_issues = []
        all_recommendations = []

        # Validate each section
        for section in report.sections:
            expected_elements = self._get_expected_elements_for_section(section.type)
            quality = self.validate_section(
                content=section.content,
                section_type=section.type,
                expected_elements=expected_elements
            )

            section_scores[section.type] = quality.overall_score

            # Collect issues and recommendations
            if quality.overall_score < self.min_quality_threshold:
                all_issues.append(f"{section.title}: Score {quality.overall_score:.2f} below threshold")
                all_recommendations.extend(quality.feedback)

        # Calculate overall score
        overall_score = statistics.mean(section_scores.values()) if section_scores else 0.0

        # Determine if report passes
        passed = overall_score >= self.min_quality_threshold

        # Store in history
        self.validation_history.append({
            "timestamp": report.timestamp,
            "overall_score": overall_score,
            "passed": passed
        })

        return ValidationResult(
            overall_score=overall_score,
            passed=passed,
            section_scores=section_scores,
            issues=all_issues,
            recommendations=all_recommendations[:5]  # Top 5 recommendations
        )

    def _get_expected_elements_for_section(self, section_type: str) -> List[str]:
        """Get expected elements for a section type."""
        elements_map = {
            "liability_assessment": ["liability", "breach", "duty", "causation"],
            "damage_calculation": ["damages", "calculation", "compensation", "quantum"],
            "prior_art_analysis": ["prior art", "patent", "novelty", "claims"],
            "competitive_landscape": ["competitors", "market", "positioning", "advantage"],
            "risk_assessment": ["risk", "probability", "impact", "mitigation"],
            "strategic_recommendations": ["recommendation", "strategy", "implementation", "timeline"]
        }
        return elements_map.get(section_type, ["analysis", "assessment"])

    def get_quality_metrics(self) -> Dict[str, Any]:
        """Get quality metrics from validation history."""
        if not self.validation_history:
            return {"error": "No validation history available"}

        recent = self.validation_history[-10:]  # Last 10 validations

        return {
            "total_validations": len(self.validation_history),
            "recent_average_score": statistics.mean([v["overall_score"] for v in recent]),
            "recent_pass_rate": sum(1 for v in recent if v["passed"]) / len(recent),
            "threshold": self.min_quality_threshold
        }