# MCP Forge Pro – AI Coding Instructions

## Project Overview
**MCP Forge Pro** is a Streamlit-based UI for generating Model Context Protocol (MCP) servers. It allows users to define API tools and prompt templates, then generates production-ready FastMCP Python code with built-in resilience and multiple deployment options.

**Key Architecture:**
- **Frontend:** Streamlit web UI with multi-step wizard (3 steps: Tools → Prompts → Code Generation)
- **Core Logic:** Code generator using Jinja2 templates to produce FastMCP server code
- **Data Model:** Pydantic v2 BaseModels (`ToolSpec`, `PromptSpec`) with strict validation (regex patterns for naming)
- **Deployment:** Supports local execution, Claude Desktop config, Docker, and Docker Compose output

## Critical Patterns & Conventions

### 1. Pydantic Validation-First Design
- All user inputs flow through `ToolSpec` and `PromptSpec` models before storage
- Tool names and prompt names must match `^[a-zA-Z_][a-zA-Z0-9_]*$` (Python identifier rules)
- **Pattern:** Use `Field(..., pattern=r"...")` to enforce constraints at definition time
- Keep validation errors user-facing; catch and display via `st.error()`

### 2. Streamlit Session State Management
- `st.session_state` holds mutable state: `tools` (list), `prompts` (list), `api_name` (str), `step` (int)
- Initialize all state keys in the `if "key" not in st.session_state` block to prevent KeyErrors
- Forms use `clear_on_submit=True` to auto-reset input fields after successful submission
- Use `st.rerun()` to trigger full page re-render when step changes

### 3. Code Generation via Jinja2 Templates
- Template literal uses triple-quoted raw string `r'''...'''` to prevent Python string escape issues
- Template context: `api_name`, `tools` list, `prompts` list
- **Path parameter handling:** Regex extracts `{param}` from URL, then replaces with positional args
- **Query vs. body args:** GET requests use `params=`, POST/PUT/DELETE use `json=`
- **Auth headers:** Generated conditionally based on `tool.auth` value ("Bearer Token", "API Key (Header)", "None")

### 4. HTTP Resilience in Generated Code
- Generated servers include `requests.Session()` with `Retry` strategy (3 retries, backoff 0.5s)
- Status codes [429, 500, 502, 503, 504] trigger retry logic
- All external requests wrapped in try-except; errors returned as `{"error": str(e), "url_attempted": ...}`

### 5. Multi-Step Wizard UI Pattern
- Step progression controlled by `st.session_state.step` (1, 2, or 3)
- Each step: form for data entry → display table of accumulated items → buttons for navigation
- Buttons trigger `st.rerun()` to re-render with updated step value

### 6. Deployment Configuration Patterns
- **Env var extraction:** Collect unique `auth_env` values from all tools; these are required for deployment
- **Claude Desktop config:** JSON structure with MCP server entry; format keys: `command`, `args`, `env`
- **Docker:** Base image `python:3.11-slim`; install dependencies in single RUN command for layer efficiency
- **Docker Compose:** Use `${VAR_NAME}` substitution; `.env` file holds secrets at runtime

## Developer Workflow

### Running Locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Launches UI on `http://localhost:8501`

### Testing Generated Code
1. Configure tools & prompts in UI
2. Download generated `{server_name}_server.py`
3. Set required env vars: `export GITHUB_TOKEN=...`
4. Run: `pip install fastmcp requests && python {server_name}_server.py`

### Common Extension Points
- **Adding tool auth methods:** Update `ToolSpec.auth` Literal options; add conditional header generation in template
- **Modifying generated server behavior:** Edit Jinja2 template in `generate_mcp_code()` function
- **New deployment target:** Add new tab in Step 3; follow existing pattern for code generation and download button

## Key Files & Responsibilities
- [app.py](app.py) – Entire application; Pydantic models (top), UI flow (bottom), code generator (middle)
- [requirements.txt](requirements.txt) – `streamlit`, `jinja2`, `requests` (dependencies for app + generated code)

## Known Design Decisions
- **Single-file structure:** Entire app in `app.py` for simplicity; could be refactored into modules if feature set expands beyond 300 lines per component
- **Jinja2 over f-strings:** Enables safe, reusable code templates with conditional logic
- **Python 3.11 base image:** Balance of modern stdlib features and community support
