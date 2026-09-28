# Legal Intelligence AI System - Project

Welcome to the Legal Intelligence AI System project! You've been hired as the Lead AI Architect at LexiMind Solutions to fix a broken AI system that analyzes legal cases.

## Project Overview

The engineering team has built the infrastructure, but the AI agents don't know how to think, analyze, or communicate. Your mission is to complete 8 TODOs to make the system intelligent.

### What's Working ✅
- FastAPI server and endpoints
- Data models and validation
- Logging and monitoring
- Basic infrastructure

### What's Broken ❌
- Can't connect to Vertex AI (TODO 1)
- Can't generate content (TODO 2)
- Can't create complete reports (TODO 3)
- No quality validation (TODOs 4-5)
- Agents have no personalities (TODOs 6-8)

## Project Structure

```
project/
├── starter/              # Your working directory (broken code)
│   ├── main.py          # FastAPI application
│   ├── src/
│   │   ├── core/        # Core system components
│   │   │   ├── agent_system.py    # TODOs 1-3: AI integration
│   │   │   └── quality_validator.py # TODOs 4-5: Quality scoring
│   │   ├── prompts/     # Agent personas
│   │   │   └── personas.py         # TODOs 6-8: Expert personas
│   │   ├── models/      # Data models (working)
│   │   └── utils/       # Utilities (working)
│   ├── tests/           # Test suite
│   └── test_scenarios.json # Sample legal cases
│
└── solution/            # Reference implementation (don't peek!)
```

## The 8 TODOs

### TODO 1: Initialize Vertex AI (agent_system.py)
Connect to Google's Vertex AI to enable AI capabilities.

### TODO 2: Generate Section Content (agent_system.py)
Implement content generation with retry logic and token tracking.

### TODO 3: Generate Complete Report (agent_system.py)
Orchestrate multiple agents to create comprehensive legal analysis.

### TODO 4: Coherence Scoring (quality_validator.py)
Build an algorithm to score logical flow and structure.

### TODO 5: Groundedness Scoring (quality_validator.py)
Build an algorithm to score technical accuracy and relevance.

### TODO 6: Business Analyst Persona (personas.py)
Create a quantitative analysis expert persona.

### TODO 7: Market Researcher Persona (personas.py)
Create a competitive intelligence expert persona.

### TODO 8: Strategic Consultant Persona (personas.py)
Create a strategic planning expert persona.

## Getting Started

### Prerequisites

1. **Google Cloud Project** with Vertex AI API enabled
2. **Python 3.9+**
3. **Access to Google Cloud Console** (web interface)

### Setup Instructions

1. **Set up Google Cloud Project**:
     - Creating/selecting a project
     - Enabling APIs via Console
     - Creating service accounts
     - Downloading JSON keys
   - No command-line tools needed!

2. **Navigate to the starter directory**:
```bash
cd project/starter
```

4. **Configure your environment**:
   - Create a `.env` file (copy from `.env.example`)
   - Add your Project ID from Google Cloud Console
   - Place your service account JSON key in the project
   - Update `GOOGLE_APPLICATION_CREDENTIALS` in `.env`

5. **Test your setup**:
```bash
# First, test your Google Cloud configuration
python test_setup.py

# Once setup test passes, run the project tests (will fail initially)
python tests/test_todos.py
```

## Working on the Project

### Step-by-Step Approach

1. **Start with TODO 1**: Get Vertex AI connection working first
2. **Then TODOs 2-3**: Implement content generation and report assembly
3. **Then TODOs 4-5**: Add quality validation algorithms
4. **Finally TODOs 6-8**: Create the expert personas

### Running the System

1. **Start the server**:
```bash
python main.py
```

2. **Open the API documentation**:
Navigate to `http://localhost:8000/docs`

3. **Test with sample scenario**:
```bash
# POST to /analyze endpoint with test_scenarios.json data
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d @test_scenarios.json
```

### Testing Your Implementation

Run tests for specific TODOs:
```bash
# Test all TODOs
python tests/test_todos.py

# Test specific TODO (example)
python -m unittest tests.test_todos.TestTODO1_VertexAIInitialization
```

## Tips for Success

### For TODO 1 (Vertex AI)
- Use `vertexai.init(project=..., location=...)`
- Create `GenerativeModel(model_name)`
- Test with a simple prompt
- Handle exceptions gracefully

### For TODO 2 (Content Generation)
- Build prompt with `self._build_prompt()`
- Use `self.model.generate_content()`
- Implement retry with exponential backoff
- Track tokens from `response.usage_metadata`

### For TODO 3 (Complete Report)
- Define section sequence with personas
- Pass previous sections for context
- Validate quality and retry if needed
- Assemble all sections into report

### For TODOs 4-5 (Quality Scoring)
- Score from 0.0 to 1.0
- Check multiple quality indicators
- Weight different components
- Return combined score

### For TODOs 6-8 (Personas)
- Minimum 150 words each
- Include role, expertise, style, frameworks
- Make them distinct and specialized
- Focus on legal/business expertise

## Validation Checklist

Before submitting, ensure:

- [ ] All tests pass (`python tests/test_todos.py`)
- [ ] Server starts without errors
- [ ] Can generate reports via API
- [ ] Quality scores are > 0.7
- [ ] Each persona is distinct and complete

## Common Issues

### "PROJECT_ID not set"
- Check your `.env` file has `PROJECT_ID=your-project-id`
- Make sure `.env` is in the correct directory
- Verify the project ID matches your Google Cloud Console

### "Not authenticated"
- Ensure your service account JSON key file exists
- Check `GOOGLE_APPLICATION_CREDENTIALS` path in `.env`
- Verify the service account has proper roles (Vertex AI User)
- Run `python test_setup.py` to diagnose authentication issues

### "Vertex AI not enabled"
- Go to Google Cloud Console → APIs & Services
- Search for "Vertex AI API" and click Enable
- Wait 2-3 minutes for the API to activate
- Also enable Cloud Storage and Logging APIs

### Tests failing
- Start with TODO 1 and work sequentially
- Check test output for specific failure reasons
- Ensure all dependencies are installed
- Run `python test_setup.py` first to verify setup

## Resources

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Gemini API Reference](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Support

If you get stuck:
1. Review the test file for hints
2. Check the error messages carefully
3. Refer to the course exercises for similar patterns
4. Remember: The infrastructure works, you're just adding the intelligence!

Good luck, Lead AI Architect! 🚀