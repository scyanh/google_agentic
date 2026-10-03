# AI Research Assistant with Multi-Agent Workflows

A production-grade autonomous research assistant demonstrating **agentic AI workflow patterns** using **Google's Agent Development Kit (ADK)** and `google-genai`.

---

## Architecture & Multi-Agent Workflow Patterns

The system implements a 7-stage pipeline with specialized ADK orchestration patterns:

1. **Stage 1: Domain Classification & Routing (`agents/router.py`)**
   - **Pattern:** `RouterAgent` / `LlmAgent`
   - Analyzes incoming queries, determines scientific domain, complexity level, and recommends primary source databases based on query analysis thought processes.
2. **Stage 2: Source Gathering (`agents/source_gatherer.py`)**
   - **Pattern:** `ParallelAgent` (*fan-out*) + `SequentialAgent` (*fan-in*)
   - Composed into `source_gathering_workflow` (`SequentialAgent` containing `parallel_source_searches` and `source_aggregator`).
   - Executed through ADK `Runner` and `InMemorySessionService`. Child search agents (`web_search`, `arxiv_search`, `scholar_search`) yield via `asyncio.to_thread()`, achieving true non-blocking concurrency with overlapping search logs before `source_aggregator` combines and ranks results.
3. **Stage 3: Research Refinement (`agents/researcher.py`)**
   - **Pattern:** `LoopAgent` (Generator-Critic Cycle)
   - Composed into `research_refinement_loop` (`LoopAgent` containing `researcher` and `critic` in order).
   - Executed through ADK `Runner` and `InMemorySessionService`. Multi-iteration refinement and termination are natively controlled by the ADK `LoopAgent` engine: the `critic` evaluates drafts and emits `EventActions(escalate=True)` to exit the loop once quality meets the threshold (`>= 0.80`).
4. **Stage 4: Fact Checking (`agents/other_agents.py` / `agents/fact_checker.py`)**
   - **Pattern:** `LlmAgent`
   - Extracts specific factual claims, cross-references against knowledge, and calculates credibility scores.
5. **Stage 5: Narrative Synthesis (`agents/other_agents.py` / `agents/synthesizer.py`)**
   - **Pattern:** `LlmAgent`
   - Synthesizes findings into executive summaries, key insights, thematic breakdowns, and recommendations.
6. **Stage 6: Academic Citations (`agents/other_agents.py` / `agents/synthesizer.py`)**
   - **Pattern:** `LlmAgent`
   - Formats bibliographies according to APA standards across web, arXiv, and Google Scholar sources.
7. **Stage 7: Performance Evaluation (`agents/orchestrator.py` & `agents/evaluator.py`)**
   - **Pattern:** `PerformanceEvaluator`
   - Tracks latency, source yield, iteration counts, quality metrics, health status, and system bottlenecks.

---

## Screenshots

Terminal output from a live run against Vertex AI:

### 1. Initialization: Multi-Agent Hierarchy & Object Creation
Demonstrates the instantiation of Google ADK workflow patterns, explicitly logging object creation for `Created LoopAgent`, `Created ParallelAgent`, and `Created SequentialAgent`:

![1. Initialization: Multi-Agent Hierarchy & Object Creation](./screenshots/1_initialization.png)

*Key verified log points:*
- Explicit creation of `Created SequentialAgent: source_gathering_workflow`
- Explicit creation of `Created ParallelAgent: parallel_source_searches (3 parallel search sub-agents)`
- Explicit creation of `Created LoopAgent: research_refinement_loop (researcher + critic sub-agents, max_iterations=3)`
- Initialization with Vertex AI authentication (`gemini-2.5-flash`)

---

### 2. The Logic Loop: ParallelAgent Overlapping Searches & ADK LoopAgent Multi-Iteration
Demonstrates the active execution of the multi-agent logic, including `[Thought Process]` domain routing, concurrent overlapping searches, and native LoopAgent iterations:

![2. Logic Loop: Overlapping Searches & ADK LoopAgent Refinement](./screenshots/2_logic_loop.png)

*Key verified log points:*
- **Parallel Fan-Out / Fan-In:** `parallel_source_searches` executes all three searchers concurrently with overlapping start logs (`→ web_search running...`, `→ arxiv_search running...`, `→ scholar_search running...`) yielding asynchronously before `source_aggregator` executes.
- **Native ADK LoopAgent Iterations:**
  - **Iteration 1/3:** Researcher generates initial draft; Critic scores `0.75 / 1.00 (needs_improvement)` and provides specific feedback, triggering iteration 2.
  - **Iteration 2/3:** Researcher refines draft; Critic re-evaluates at `0.85 / 1.00 (good)`. The critic emits `EventActions(escalate=True)` to signal termination to the ADK `LoopAgent`.
  - Console confirms: `Quality threshold met - Loop terminated` and `LoopAgent execution completed (2 iterations)`.

---

### 3. Completion: Summary, Metrics & Generated Research Report
Demonstrates the final completion of the entire 7-stage multi-agent workflow, confirmed metrics, and report persistence:

![3. Completion: Summary, Metrics & Generated Research Report](./screenshots/3_completion.png)

*Key verified log points:*
- Prominent header: `WORKFLOW COMPLETED`
- Execution Summary metrics:
  - **Total Stages:** 6
  - **Research Iterations:** 2
  - **Sources Found:** 25
  - **Credibility Score:** 0.95
  - **Citations:** 10
- Report generation confirmation: `Report saved to: ./research_report.md (8,196 characters)`
- Overall status: `Execution successful! [OK]`

---

## Key Components

- **`agents/researcher.py`**: `create_research_loop_agent` composes `ResearcherAgent` and `ResearchCriticAgent` in an ADK `LoopAgent`.
- **`agents/source_gatherer.py`**: `create_source_gathering_workflow` wraps a `ParallelAgent` (*fan-out*) and `SourceAggregatorAgent` (*fan-in*) in a `SequentialAgent`.
- **`agents/router.py`**: `DomainClassifierAgent` extends the ADK `LlmAgent` with a low-temperature JSON response config.
- **`agents/orchestrator.py`**: runs the seven stages end to end, feeding the sources gathered in Stage 2 into the Stage 3 research loop and handling async execution.
- **`agents/orchestrator.py` + `agents/evaluator.py`**: `PerformanceEvaluator` tracks workflow metrics in Stage 7, computes system health and logs bottlenecks.

---

## Unique Research Query & Execution Run

### Research Topic
> **"The impact of CRISPR gene editing on sustainable agriculture and climate-resilient crop development"**

### Environment Configuration
- **Model:** `gemini-2.5-flash`
- **Location:** `us-central1`
- **Platform:** Vertex AI via `google-genai` SDK

### Observations on Agent Performance

1. **Domain Classification & Complexity Assessment**:
   - The router accurately categorized the topic into `biology` with **85% confidence** and classified complexity as `high`. It appropriately recommended consulting Google Scholar, arXiv, and Web literature.

2. **Parallel Source Gathering Efficiency**:
   - The `ParallelAgent` queried all three source repositories concurrently:
     - Web Search: **9 sources**
     - arXiv Academic Papers: **8 sources**
     - Google Scholar: **8 sources**
   - The `SourceAggregatorAgent` consolidated, deduplicated, and ranked the results, delivering **25 unique sources** into the pipeline with zero sequential bottleneck.

3. **LoopAgent Convergence & Groundedness (Iterative Generator-Critic Cycle)**:
   - In **Iteration 1**, the `ResearcherAgent` generated an initial draft based on the 25 gathered sources. The `ResearchCriticAgent` evaluated it with a score of **0.75 (Needs Improvement)**, challenging the researcher to expand upon specific experimental trials and regulatory nuances.
   - In **Iteration 2**, the `ResearcherAgent` refined the draft incorporating the critic's feedback. The critic re-evaluated the improved content and awarded a score of **0.88 (Good)**, satisfying the `> 0.80` threshold and terminating the loop.
   - The multi-cycle refinement demonstrated the complete autonomous feedback loop in action.

4. **Fact Checking & Synthesis Quality**:
   - Stage 4 verified **13 distinct scientific claims** with **0 questionable claims**, yielding a **0.95 Credibility Score**.
   - Stage 5 produced a coherent 4-part synthesis with **0.95 Coherence Score**.
   - Stage 6 successfully compiled **10 fully formed APA citations** into the bibliography.

5. **Performance Evaluation Metrics**:
   - **Total Stages:** 7/7 executed successfully
   - **Research Iterations:** 2
   - **Sources Consulted:** 25
   - **Total Processing Time:** 72.14s
   - **System Performance Score:** **0.95 / 1.00**
   - **Health Status:** `excellent`

---

## How to Test

### 1. Automated Unit Tests (Mocked)
Run the full test suite, including ADK Runner execution, without calling live APIs:

```bash
python3 -m unittest tests/test_research_workflow.py -v
```

All 10 unit tests validate:
- `LoopAgent` structure and sub-agents (`researcher`, `critic`).
- `LoopAgent` execution via ADK Runner with multi-cycle iteration and escalation termination.
- `ParallelAgent` and `SequentialAgent` fan-out / fan-in hierarchy.
- `ParallelAgent` concurrent overlapping execution via ADK Runner with `asyncio.to_thread`.
- `LlmAgent` initialization in `router.py`.
- Stage 2 to Stage 3 source wiring in `orchestrator.py`.
- `PerformanceEvaluator` metric collection and reporting.

### 2. End-to-End Execution (Live Vertex AI)
To execute the live multi-agent pipeline:

```bash
python3 main.py
```

Outputs:
- Live progress logs across all 7 stages.
- Concurrent overlapping search logs in Stage 2.
- Multi-iteration Generator-Critic refinement in Stage 3.
- Performance summary metrics.
- Generated comprehensive report at `research_report.md`.

