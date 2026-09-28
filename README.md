# Google Agentic AI Engineer: Projects

My projects for Udacity's **Google Agentic AI Engineer** Nanodegree (nd906). Across four courses they go from prompt engineering with Gemini to production-style multi-agent systems built with the **Google Agent Development Kit (ADK)** on **Vertex AI**.

Each project has its own README with architecture, setup steps and screenshots of it running.

| # | Project | What it is | Key techniques |
|---|---|---|---|
| 1 | [Legal Intelligence AI System](1%20Prompting%20for%20Effective%20LLM%20Reasoning%20with%20Gemini) | A FastAPI service where expert personas analyze a legal case and write a scored report | Persona prompting, multi-agent report generation, retry logic, coherence and groundedness scoring |
| 2 | [AI Research Assistant](2%20Agentic%20Workflows%20with%20Google%20ADK) | A 7-stage research pipeline that routes a question, searches sources in parallel, refines drafts and cites them | `ParallelAgent` fan-out/fan-in, `LoopAgent` generator-critic loop, routing, fact checking |
| 3 | [Betty's Bird Boutique Support Agent](3%20Building%20Agents%20with%20Google%20ADK%20and%20Vertex%20AI) | A customer support agent that answers from a product database, store documents and the web | MCP Toolbox for MySQL, Vertex AI Search datastore, Google Search sub-agent as `AgentTool`, guardrails |
| 4 | [Multi-Agent Banking System](4%20Multi-Agent%20Systems%20with%20Google%20ADK%20and%20Vertex%20AI) | A manager agent that routes to isolated deposit and loan agents, plus a loan approval pipeline | A2A protocol, agent isolation, `SequentialAgent` and `ParallelAgent` orchestration, custom agents, MCP Toolbox |

## Highlights

**1. Legal Intelligence AI System.** Specialized personas (legal, business and risk analysts) each write a section of a legal case analysis. A validator then scores the report for coherence and groundedness. It runs on Vertex AI with `gemini-2.5-flash` behind a FastAPI API, and all 21 tests pass.

**2. AI Research Assistant.** A router classifies the question's domain and complexity. Web, arXiv and Scholar searches then run concurrently in a `ParallelAgent`, and a researcher and critic iterate in a `LoopAgent` until the draft meets a quality bar. The pipeline ends with fact checking, synthesis, APA citations and latency and quality metrics.

**3. Betty's Bird Boutique.** A support agent with a warm persona and strict limits: it stays on topic and doesn't take orders. It reads live prices from MySQL through MCP Toolbox, answers store questions from PDFs indexed in Vertex AI Search, and delegates general bird care questions to a Google Search sub-agent. A date tool lets it answer "are you open today?", and all 22 rubric tests pass.

**4. Multi-Agent Banking System.** Three agents run as separate services that talk over A2A, so each one can only reach its own data. The loan agent runs an approval pipeline in stages: it gathers data, checks policy from documents in GCS, reviews the customer profile and equity in parallel (including an A2A balance check against the deposit agent), and writes a final report with a privacy guardrail.

## Stack

Python · Google ADK · Gemini 2.5 (Flash and Pro) · Vertex AI · Vertex AI Search · MCP Toolbox · A2A · Cloud SQL (MySQL) · Cloud Storage · FastAPI

## Repository layout

```
1 Prompting for Effective LLM Reasoning with Gemini/   Project 1 (Project Starter Code/)
2 Agentic Workflows with Google ADK/                   Project 2 (project-starter/)
3 Building Agents with Google ADK and Vertex AI/       Project 3 (project/) and lesson exercises
4 Multi-Agent Systems with Google ADK and Vertex AI/   Project 4 (project/) and lesson exercises
```

The `lesson-*` folders and project starter code come from Udacity's course materials, which are © Udacity and licensed under their own [LICENSE.md](4%20Multi-Agent%20Systems%20with%20Google%20ADK%20and%20Vertex%20AI/LICENSE.md). Credentials are never committed: the projects read them from environment variables or a local `.env` file.
