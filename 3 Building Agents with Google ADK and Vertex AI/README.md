# Betty's Bird Boutique - Customer Support Agent with Google ADK

A multi-tool, agentic AI customer support system for **Betty’s Bird Boutique**, developed using **Google's Agent Development Kit (ADK)** and **Gemini 2.5 Flash**.

---

## Features & Architecture

- **Root Agent (`bettys_bird_boutique_agent`)**:
  - Powered by `gemini-2.5-flash` with in-memory session management (`InMemorySessionService`).
  - Warm, avian-enthusiastic persona with strict guardrails:
    - **No Order Taking**: Directs customers to visit the physical store to make purchases and meet the flock.
    - **Strict Domain Boundaries**: Restricts conversations strictly to birds and Betty's Bird Boutique operations.
- **Product Database via MCP Toolbox (`tools.yaml`)**:
  - Connects to MySQL database (`betty`) through Google's Model Context Protocol (MCP) Database Toolbox.
  - Queries real-time prices for seeds, millet, pellets, bird feeders, bird baths, and cages via `get-product-price`.
  - Supports catalog listing with `list-products`.
- **Store Knowledge Base via Vertex AI Search Datastore (`datastore.py`)**:
  - Connects to Vertex AI Search Datastore (`google-cloud-discoveryengine`) to index and retrieve chunk-level information from store PDF documents:
    - `bettys-hours.pdf`: Store operating hours.
    - `bettys-history.pdf`: 1980 founding story with Betty & Bob Winger and their budgie Pip.
    - `bettys-staff.pdf`: Team bios (James, Maria, David, Chloe, Sarah, Benjamin) and Leo the Moluccan cockatoo mascot.
- **Avian Research Sub-Agent via Google Search Grounding (`search_agent.py`)**:
  - Specialized sub-agent `bird_web_search_agent` wrapped as an `AgentTool`.
  - Utilizes `google_search` to answer general questions on avian nutrition, species characteristics, and care.
- **Stand-Out Enhancement - Date Awareness Tool**:
  - Provides real-time date and day of the week (`get_current_date_and_day`) so the agent can accurately answer questions like *"Are you open today?"*.

---

## Quickstart & Local Testing

### 1. Environment Setup
Configure your Google Cloud and Database credentials in `.env`:
```bash
export $(grep -v '^#' .env | xargs)
```

### 2. Run Automated Test Suite
Verify all 22 Rubric verification tests:
```bash
python3 -m unittest tests/test_todos.py
```

### 3. Launch with ADK Web Previewer
To test conversational flows interactively:
```bash
# From the parent directory of starter
adk web starter
```

### 4. Rubric 5-Turn Conversation Sequence
1. **Store Hours**: *"When are you open on Thursday?"* (Uses `datastore_search_tool`)
2. **Founder History**: *"Who is Betty?"* (Uses `datastore_search_tool`)
3. **Pet Bird**: *"What kind of bird did she own?"* (Uses `datastore_search_tool`)
4. **Bird Diet**: *"What do they eat?"* (Uses `bird_web_search_agent` via Google Search)
5. **Product Pricing & Order Guardrail**: *"Can I buy that from you?"* (Uses `get-product-price`, declines online orders, and invites to store)
