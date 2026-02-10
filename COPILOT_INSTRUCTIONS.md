# MCP Forge Pro – Copilot Development Guide

## Project Overview

**MCP Forge Pro** is a Streamlit-based UI for generating production-ready Model Context Protocol (MCP) servers code from REST APIs and SOAP web services. The tool automates FastMCP server code generation with built-in HTTP resilience, authentication support, and multiple deployment options.

**Current Status**: Fully modularized with separated concerns (parsers, generators, UI)

---

## Architecture & File Organization

### Directory Structure
```
MCP/
├── app.py (487 lines) - Streamlit UI orchestration
├── requirements.txt - Project dependencies
├── README.md - User documentation
├── parsers/
│   ├── __init__.py - Export swagger_to_tools, wsdl_to_tools
│   ├── openapi_parser.py (328 lines) - REST API parsing
│   └── wsdl_parser.py (226 lines) - SOAP/WSDL parsing
├── generators/
│   ├── __init__.py - Export code generation functions
│   ├── code_generator.py (406 lines) - FastMCP code generation
│   └── prompt_generator.py (174 lines) - LLM-powered prompts
└── petstore/ - Test data
```

### Core Modules

#### **parsers/openapi_parser.py**
- `swagger_to_tools(swagger_text)` - Parse OpenAPI 3.0 & Swagger 2.0 specs
  - Detects format via `"openapi"` key
  - Validates required fields (host, schemes, basePath for Swagger 2.0)
  - Extracts endpoints, parameters, request bodies, security schemes
  - Returns: (tools_list, models_dict)
- Helper functions:
  - `_normalize_type()` - Convert schema types to Python types
  - `_map_schema_to_type()` - Recursively resolve $ref pointers
  - `_extract_schema_fields()` - Extract Pydantic model fields

#### **parsers/wsdl_parser.py**
- `wsdl_to_tools(wsdl_text)` - Parse WSDL 1.1 XML specs
  - Handles SOAP 1.1 and 1.2
  - Supports document/literal and RPC styles
  - Namespace-aware XML parsing
  - Returns: (tools_list, models_dict)

#### **generators/code_generator.py**
Three public functions with clear separation:

1. **`generate_rest_mcp_code(api_name, tools, prompts, models)`**
   - Generates FastMCP server code for REST APIs only
   - Line 58
   - Clean template without SOAP conditionals
   - Includes helpers: `_create_session_with_retries()`, `_extract_path_params()`, `_to_dict()`
   - Supports: GET, POST, PUT, DELETE, PATCH
   - Auth: Bearer Token, API Key (Header)

2. **`generate_soap_mcp_code(api_name, tools, prompts, models)`**
   - Generates FastMCP server code for SOAP services only
   - Line 209
   - Clean template without REST conditionals
   - Includes helpers: `_generate_soap_request()`, `_call_soap_operation()`
   - XML parsing with namespace awareness
   - Supports: SOAP 1.1/1.2, document/literal & RPC styles

3. **`generate_mcp_code(api_name, tools, prompts, models)` [DISPATCHER]**
   - Auto-detects tool type (REST vs SOAP)
   - Line 382
   - Detection: checks for `soap_action` field
   - Routes to appropriate specialized generator
   - Backward compatible with existing code

#### **generators/prompt_generator.py**
- `auto_generate_prompts(tools, api_key, provider)` - LLM-powered prompt templates
  - Supports OpenAI (gpt-4o) and Groq (llama-3.1-8b-instant)
  - Generates one prompt per tool with MCP-compliant formatting
  - Validates prompt name matches tool name for auto-linking

#### **app.py - Streamlit UI**
- 487 lines of UI code only (no function definitions)
- Session state management
- 4-step wizard:
  - **Step 0**: Home screen with features overview
  - **Step 1**: Configure API Tools (import or manual entry)
  - **Step 2**: Design Prompts (auto-generate or manual)
  - **Step 3**: Generate & Deploy (download with tabs for Local/Docker/Claude Desktop)
- Imports from modularized components:
  ```python
  from parsers import swagger_to_tools, wsdl_to_tools
  from generators import generate_mcp_code, auto_generate_prompts
  ```

---

## Key Data Structures

### Tool Definition (dict)
```python
{
    "name": "get_user",                    # Function name
    "url": "https://api.example.com/users/{id}",
    "method": "GET",                       # GET, POST, PUT, DELETE, PATCH
    "auth": "Bearer Token",                # None, Bearer Token, API Key (Header)
    "auth_val": "API_TOKEN",               # Environment variable name
    "args": {"id": "str", "limit": "int"}, # {param: type}
    "body_model": "GetUserRequest",        # Pydantic model name or None
    "has_file_fields": False,              # True if uploads needed
    "desc": "Fetch user by ID"             # Description
    # SOAP-specific:
    "soap_action": "http://...",           # Optional: SOAP action URI
    "soap_style": "document"               # Optional: document|rpc
}
```

### Pydantic Model Definition (dict)
```python
{
    "GetUserRequest": {
        "id": "int",
        "name": "str",
        "email": "str | None"              # Optional fields use Union
    },
    "ListUsersResponse": {
        "users": "list[User]",
        "total": "int"
    }
}
```

### Prompt Definition (dict)
```python
{
    "name": "summarize",                   # Must match tool name
    "args": "id,limit",                    # Comma-separated
    "text": "Summarize {id} with {limit} records",
    "desc": "Summarize operation results"
}
```

---

## Critical Patterns & Conventions

### 1. OpenAPI/Swagger Parsing
- **Dual Format Support**: Detect via `"openapi"` key presence
- **Schema Resolution**: Recursively resolve `$ref` pointers:
  - OpenAPI 3.0: `#/components/schemas/ModelName`
  - Swagger 2.0: `#/definitions/ModelName`
- **Type Mapping**: JSON schema → Python annotations
  - `integer` → `int`, `number` → `float`, `array` → `list[ItemType]`
  - References return model names, nested objects return `dict`
- **Validation**: Check required fields before processing
  - Swagger 2.0: host, schemes, basePath
  - OpenAPI 3.0: servers array with URL

### 2. WSDL/SOAP Parsing
- **Namespace Handling**: Register and use XML namespaces
- **Style Support**: Both document/literal and RPC styles
- **Message Extraction**: Map ports → operations → messages → types
- **Type Fields**: Extract from complexType sequences and global elements
- **Body Model Assignment**: Use element reference for document/literal

### 3. Code Generation
- **Template Context**: Pass only used models to Jinja2 (filter step)
- **Path Parameters**: Regex `{(.*?)}` extracts params, replaced with str()
- **Query vs Body Params**:
  - GET: All non-path params as `params=`
  - POST/PUT/DELETE: Body params as `json=`, query-only as `params=`
- **Auth Headers**: Generated conditionally:
  - Bearer: `Authorization: Bearer {env_var}`
  - API Key: `X-API-KEY: {env_var}`
- **HTTP Resilience**: urllib3.Retry with 3 retries, exponential backoff
  - Retry codes: [429, 500, 502, 503, 504]
  - Retry methods: GET, POST, PUT, DELETE, PATCH

### 4. Session State Management (app.py)
- Initialize ALL state keys in if-blocks (prevent KeyErrors)
- `tools`, `prompts`, `models` are mutable lists/dicts
- `swagger_selection`, `all_swagger_tools` track import state
- Use `st.rerun()` for step transitions
- Forms use `clear_on_submit=True` for auto-reset

### 5. MCP Prompt Compliance
- **Name Matching**: Prompt name MUST exactly match tool name (enables auto-linking)
- **Placeholder Usage**: Only use `{placeholder}` for arguments that exist
- **No Placeholders for Empty Args**: If tool has no arguments, no `{}` in text

---

## Development Workflow

### Adding New Parser (e.g., GraphQL)
1. Create `parsers/graphql_parser.py`
2. Implement `graphql_to_tools(schema_text)` → (tools, models)
3. Export in `parsers/__init__.py`
4. Add import and button in `app.py` Step 1
5. No changes needed to generators (tool format is universal)

### Adding New Code Generator (e.g., for gRPC)
1. Create new generator function in `generators/code_generator.py`
2. Follow naming: `generate_<type>_mcp_code(api_name, tools, prompts, models)`
3. Export in `generators/__init__.py`
4. Update dispatcher `generate_mcp_code()` to detect type
5. UI automatically uses dispatcher (no changes needed)

### Adding New Auth Method
1. Add detection in appropriate parser (swagger_to_tools or wsdl_to_tools)
2. Add conditional in REST or SOAP template:
   ```jinja2
   {% if tool.auth == 'OAuth 2.0' %}
   # OAuth logic
   {% endif %}
   ```
3. Document in tool's "auth" field

### Testing Generated Code
1. Generate code via UI
2. Copy tool name and environment variables
3. Set env vars: `export API_TOKEN='...'`
4. Install deps: `pip install fastmcp requests`
5. Run: `python3 {server_name}_server.py`

---

## Type System & Validation

### Python Type Annotations (in Pydantic models)
- **Basic**: `str`, `int`, `float`, `bool`
- **Collections**: `list[str]`, `dict[str, int]`
- **Optional**: `str | None` or `Optional[str]`
- **Union**: `str | int`
- **References**: Model name (e.g., `User` for custom Pydantic models)
- **Generic**: Pydantic's `BaseModel` for all custom types

### Validation Rules
- Empty schema properties → `{"data": "dict"}` placeholder model
- Bare objects without properties → `dict` type
- Unresolved $refs → fallback to last path segment as model name

---

## Common Issues & Solutions

### Issue: "Missing required field in Swagger spec"
- **Cause**: Swagger 2.0 requires `host`, `schemes`, `basePath`
- **Solution**: Validate spec before parsing; show helpful error message

### Issue: Namespace errors in WSDL parsing
- **Cause**: Unregistered XML namespaces in XPath queries
- **Solution**: Register all namespaces before finding elements
- **Pattern**: `ET.register_namespace(prefix, uri)` then find with `{uri}element`

### Issue: Path params not substituting in generated code
- **Cause**: Parameter name not in args dict or regex mismatch
- **Solution**: Regex finds `{name}`, loop checks `if name in remaining`

### Issue: SOAP operation fails with "No Body element"
- **Cause**: Namespace prefix not stripped from operation name
- **Solution**: Use `split(':')[-1]` or regex to extract local name

---

## Testing Checklist

- [ ] All imports work: `from parsers import ...; from generators import ...`
- [ ] Streamlit UI loads: `streamlit run app.py`
- [ ] REST code generation produces valid Python
- [ ] SOAP code generation produces valid Python
- [ ] Dispatcher auto-detects REST vs SOAP correctly
- [ ] Generated code can be compiled: `python3 -m py_compile {file}`
- [ ] Pydantic models serialize/deserialize correctly
- [ ] Path parameters substitute correctly in URLs
- [ ] Authentication headers generated when present
- [ ] HTTP retry strategy mounts on both http:// and https://

---

## Extension Points

### Parser Extension
- Location: `parsers/` directory
- Interface: `to_tools(spec_text) → (tools: list, models: dict)`
- Example: `swagger_to_tools()`, `wsdl_to_tools()`

### Generator Extension
- Location: `generators/code_generator.py`
- Interface: `generate_<type>_mcp_code(api_name, tools, prompts, models) → str`
- Dispatcher: Update detection logic in `generate_mcp_code()`

### UI Extension
- Location: `app.py`
- Patterns: Use session state, `st.rerun()` for transitions
- Forms: Always use `clear_on_submit=True`

---

## Dependencies

Core requirements (see `requirements.txt`):
- `streamlit` - Web UI framework
- `pyyaml` - YAML parsing for Swagger specs
- `jinja2` - Code template rendering
- `requests` - HTTP client for generated code
- `pydantic` - Type validation and model generation
- `fastmcp` - MCP framework (runtime dependency for generated servers)
- `openai` / `groq` - LLM providers for prompt generation (optional)

---

## Key Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| [app.py](app.py) | 487 | Streamlit UI orchestration |
| [parsers/openapi_parser.py](parsers/openapi_parser.py) | 328 | OpenAPI/Swagger parsing |
| [parsers/wsdl_parser.py](parsers/wsdl_parser.py) | 226 | WSDL/SOAP parsing |
| [generators/code_generator.py](generators/code_generator.py) | 406 | REST & SOAP code generation |
| [generators/prompt_generator.py](generators/prompt_generator.py) | 174 | LLM prompt generation |

---

## Running Locally

```bash
# Setup
pip install -r requirements.txt

# Run UI
streamlit run app.py

# Verify modular imports
python3 -c "from parsers import swagger_to_tools, wsdl_to_tools; from generators import generate_mcp_code, generate_rest_mcp_code, generate_soap_mcp_code; print('✅ All imports OK')"

# Check syntax
python3 -m py_compile app.py parsers/*.py generators/*.py
```

---

## Performance Considerations

- **Large Specs**: Parsing 1000+ endpoints may take 1-2 seconds
- **Code Generation**: Template rendering scales with tool count (linear)
- **Memory**: Models dict stores all schemas (optimize by filtering early)
- **Session State**: Use `st.session_state.clear()` cautiously (resets entire UI)

---

## Backward Compatibility

- ✅ `generate_mcp_code()` still works as entry point (dispatcher function)
- ✅ app.py imports unchanged (uses dispatcher)
- ✅ Tool/Prompt/Model structures are stable
- ⚠️ Direct imports of internal helpers may break (use public API)

