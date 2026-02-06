# MCP Forge Pro – AI Coding Instructions

## Project Overview
**MCP Forge Pro** is a Streamlit-based UI for generating Model Context Protocol (MCP) servers. It allows users to define API tools (via manual entry or OpenAPI/Swagger import) and prompt templates, then generates production-ready FastMCP Python code with built-in HTTP resilience and multiple deployment options.

**Key Architecture:**
- **Frontend:** Streamlit web UI with multi-step wizard (3 steps: Tools → Prompts → Code Generation)
- **API Parsing:** Dual support for OpenAPI 3.0 and Swagger 2.0 specifications with schema extraction
- **Core Logic:** Code generator using Jinja2 templates to produce FastMCP server code with `requests.Session()` retry strategy
- **Pydantic Models:** Auto-generated from API schemas; only models for selected tools included in output
- **Deployment:** Supports local execution, Claude Desktop config, Docker, and Docker Compose output

## Critical Patterns & Conventions

### 1. OpenAPI/Swagger Parsing with Type Extraction
- **Dual Format Support:** Detects OpenAPI 3.0 vs Swagger 2.0 via presence of `"openapi"` key
- **Schema Resolution:** `_resolve_schema_ref()` recursively resolves `$ref` pointers to actual definitions:
  - OpenAPI 3.0: `#/components/schemas/ModelName`
  - Swagger 2.0: `#/definitions/ModelName`
- **Type Mapping:** `_map_schema_to_type()` converts JSON schemas to Python type annotations:
  - `integer` → `int`, `number` → `float`, `boolean` → `bool`, `array` → `list[ItemType]`
  - References return model names (e.g., `"User"` from `$ref`), nested objects return `dict`
- **Request Body Extraction:**
  - OpenAPI 3.0: Parses `requestBody.content.application/json.schema` with fallback to other content types
  - Swagger 2.0: Extracts from `parameters[].in="body"` or `in="formData"` parameters
  - Empty schemas generate generic `{"data": "dict"}` model to preserve body parameter presence

### 2. Streamlit Session State Management
- `st.session_state` holds mutable state: `tools` (list), `prompts` (list), `models` (dict), `api_name` (str), `step` (int), `swagger_selection` (dict)
- Initialize all state keys in the `if "key" not in st.session_state` block to prevent KeyErrors
- `models` dict stores all Pydantic field definitions extracted from API specs: `{ModelName: {field: type}}`
- Forms use `clear_on_submit=True` to auto-reset input fields after successful submission
- Use `st.rerun()` to trigger full page re-render when step changes

### 3. Code Generation via Jinja2 Templates
- **Template Context:** Passes `api_name`, `tools` list, `prompts` list, and `models` (filtered to only used models)
- **Path Parameter Handling:** Regex `{(.*?)}` extracts path params from URL, then replaces placeholders with `str()` converted values
- **Query vs Body Params:**
  - GET: All non-path params sent as `params=remaining_args`
  - POST/PUT/DELETE/PATCH: Body params sent as `json=payload`, query params only when no body
- **Body Model Instantiation:** `{{ tool.body_model }}(**body_data).dict()` creates Pydantic instance from dict before serializing
- **Auth Headers:** Generated conditionally:
  - Bearer Token: `Authorization: Bearer {env_var}`
  - API Key (Header): `X-API-KEY: {env_var}`
- **Model Filtering:** `generate_mcp_code()` filters `models` dict to only include those referenced by selected tools via `body_model` field

### 4. HTTP Resilience in Generated Code
- **Retry Strategy:** `urllib3.Retry` with 3 total retries, 0.5s backoff factor, exponential backoff on retry
- **Retry Status Codes:** [429, 500, 502, 503, 504] trigger automatic retry
- **Allowed Methods:** GET, POST, PUT, DELETE, PATCH configured to retry
- **Session Pooling:** `requests.Session()` with mounted `HTTPAdapter` on both `http://` and `https://`
- **Error Handling:** All requests wrapped in try-except; failures return `{"error": str(e), "url_attempted": base_url}`

### 5. Multi-Step Wizard UI Pattern
- **Step 1 - Configure Tools:** Manual entry OR import from OpenAPI/Swagger/WSDL with checkbox selection
  - Manual Entry: Form with Tool Name, Full URL, HTTP Method, Auth Mechanism, Env Var Name, Arguments JSON, Description
  - OpenAPI/Swagger: Paste spec → Load APIs button → Checkboxes for endpoint selection → Generate Selected Tools button
  - Tools table displays after adding (shows name, url, method, auth, args, body_model, desc)
- **Step 2 - Design Prompts:** Auto-generate button (calls GPT-4 via OpenAI API) OR manual form entry
  - Auto-generate produces 3 prompt templates per tool (summarize, error analysis, context comparison)
  - Manual: Form with Prompt Name, Arguments, Prompt Template text, Description
  - Prompts table displays for review
- **Step 3 - Code Generation:** Display generated Python code with download button
  - Four deployment tabs: Local Execution, Claude Desktop, Dockerfile, Docker Compose
  - Extracts unique auth_env values for environment variable instructions
  - All code dynamically generated based on selected tools and prompts only

### 6. Deployment Configuration Patterns
- **Env var extraction:** Collect unique `auth_val` values from all tools; these are required for deployment
- **Claude Desktop config:** JSON structure with MCP server entry; format keys: `command`, `args`, `env`
- **Docker:** Base image `python:3.11-slim`; install dependencies with pip install
- **Docker Compose:** Use `${VAR_NAME}` substitution; `.env` file holds secrets at runtime

## Code Structure & Key Functions

### Schema Parsing Functions
- **`_resolve_schema_ref(ref_path, spec, is_openapi)`:** Resolves `$ref` pointers by navigating spec JSON tree. Returns None if ref path doesn't start with `#/` or path doesn't exist.
- **`_map_schema_to_type(schema, spec, is_openapi)`:** Maps JSON schema types to Python annotations. Recursively resolves `$ref` references. Returns type string like `"int"`, `"list[str]"`, `"User"` (model name).
- **`_extract_schema_fields(schema, spec, is_openapi)`:** Extracts object properties into dict `{field_name: python_type_string}`. Handles $ref recursively; returns empty dict for bare objects with no properties.

### Tool Parsing
- **`swagger_to_tools(swagger_text)`:** Main parser; returns `(tools_list, models_dict)`. 
  - Detects OpenAPI 3.0 vs Swagger 2.0 by checking for `"openapi"` key
  - Extracts base_url from `servers[0].url` (OAS3) or `schemes/host/basePath` (Swagger)
  - Parses security schemes (Bearer Token, API Key)
  - For each path/method: extracts operationId, parameters (path/query/header/body/formData), requestBody (OAS3 only)
  - Creates Pydantic models for body parameters; assigns `body_model` name to tool

### Code Generation
- **`generate_mcp_code(api_name, tools, prompts, models)`:** Returns Python source string for FastMCP server
  - Filters `models` dict to only include those referenced by selected tools' `body_model` fields
  - Uses Jinja2 Template to render tool functions with proper parameter handling
  - Generates session with retry strategy at module level
  - Returns complete runnable Python code

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
4. Run: `pip install fastmcp requests urllib3 && python {server_name}_server.py`

### Common Extension Points
- **Adding tool auth methods:** Update `swagger_to_tools()` security scheme detection; add conditional header generation in Jinja2 template
- **Modifying generated server behavior:** Edit Jinja2 template string in `generate_mcp_code()` function
- **Improving schema extraction:** Enhance `_extract_schema_fields()` to handle nested objects and array types
- **New deployment target:** Add new tab in Step 3; follow existing pattern for code generation and download button

## Key Files & Responsibilities
- [app.py](app.py) – Entire application in single file (562 lines): schema parsers (top), LLM prompt generator (middle), code generator (middle), Streamlit UI flow (bottom)
- [requirements.txt](requirements.txt) – Dependencies: `streamlit`, `pyyaml`, `jinja2`, `requests`, `pydantic`, `fastmcp` (for generated code validation)

## Known Design Decisions & Limitations
- **Single-file structure:** Entire app in `app.py` for simplicity; could be refactored into modules if feature set expands beyond 600 lines per component
- **Jinja2 over f-strings:** Enables safe, reusable code templates with conditional logic and loops
- **Python 3.11 base image:** Balance of modern stdlib features and community support
- **Empty object handling:** When a request body has no defined properties, generates generic `{data: dict}` model to preserve type hints
- **WSDL support not yet implemented:** UI has WSDL mode but `wsdl_to_tools()` function is undefined; needs implementation
- **No nested model generation:** Complex nested objects are flattened to `dict` type; future enhancement could recursively generate nested Pydantic models
- **JSON only:** Generated code assumes `application/json` content type; `application/x-www-form-urlencoded` and multipart not yet supported
