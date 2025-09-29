# EvoAI Agent — LangGraph + LLM (with deterministic fallback)

This version wires the agent as a real **LangGraph** with optional **LLM** nodes.

## Two ways to run

### A) Deterministic (no LLM; easiest for grading)
```bash
python -m tests.run_langgraph
```

### B) Real LLM (OpenAI)
```bash
# Power the LLM nodes
set OPENAI_API_KEY=sk-...         # (Windows PowerShell: $env:OPENAI_API_KEY='sk-...')
# Optional: choose model
set OPENAI_MODEL=gpt-4o-mini
# Ensure fallback is OFF
set USE_MOCK_LLM=                 # unset or empty

python -m tests.run_langgraph
```

## Project layout
- `/src/graph_langgraph.py` — Router → ToolSelector → PolicyGuard → Responder as LangGraph nodes
- `/src/tools.py` — mocked tools (search, size, ETA, order lookup, cancel with strict 60-min policy)
- `/prompts/system.md` — system prompt
- `/tests/run_langgraph.py` — runs the 4 required prompts; prints trace JSON + reply
- `/data` — products & orders

## Determinism
- If `USE_MOCK_LLM` is set (or `OPENAI_API_KEY` is absent), nodes fall back to the deterministic logic used in v2.
- When `OPENAI_API_KEY` is present and `USE_MOCK_LLM` is not set, the router and responder call the LLM.

## Install
```bash
pip install -r requirements.txt
```

