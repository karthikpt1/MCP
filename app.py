import streamlit as st
import json
import os
import re
import yaml
from collections import OrderedDict
from jinja2 import Template
import openai  # for auto prompt generation

# --- SESSION STATE INITIALIZATION ---
if 'tools' not in st.session_state:
    st.session_state.tools = []
if 'prompts' not in st.session_state:
    st.session_state.prompts = []
if 'models' not in st.session_state:
    st.session_state.models = {}
if 'api_name' not in st.session_state:
    st.session_state.api_name = "MyAPI"
if 'step' not in st.session_state:
    st.session_state.step = 0
if 'swagger_selection' not in st.session_state:
    st.session_state.swagger_selection = {}
if 'swagger_text' not in st.session_state:
    st.session_state.swagger_text = ""
if 'wsdl_text' not in st.session_state:
    st.session_state.wsdl_text = ""

# ------------------------------------------------------------------
# SWAGGER / OPENAPI PARSER WITH AUTH + PYDANTIC
# ------------------------------------------------------------------

def _normalize_type(type_str):
    """
    Convert OpenAPI/Swagger type strings to valid Python type annotations.
    Maps raw type names like 'string', 'integer', 'file' to Python equivalents.
    """
    if not type_str:
        return "str"
    
    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "file": "str",
        "array": "list",
        "object": "dict",
    }
    
    return type_map.get(type_str, type_str)

def _map_schema_to_type(schema, spec, is_openapi):
    """
    Map OpenAPI/Swagger schema to Python type annotation string.
    Handles basic types, refs, arrays, and nested objects.
    """
    if not schema:
        return "str"
    
    # Handle $ref references - resolve and get type of resolved schema
    if "$ref" in schema:
        ref_path = schema["$ref"]
        resolved_schema = _resolve_schema_ref(ref_path, spec, is_openapi)
        if resolved_schema:
            return _map_schema_to_type(resolved_schema, spec, is_openapi)
        
        # Extract model name from ref path
        parts = ref_path.split("/")
        if parts[-1]:
            return parts[-1]
        return "dict"
    
    schema_type = schema.get("type", "str")
    schema_format = schema.get("format", "")
    
    if schema_type == "array":
        item_type = _map_schema_to_type(schema.get("items", {}), spec, is_openapi)
        return f"list[{item_type}]"
    elif schema_type == "object":
        # For objects with properties, they'll be handled as separate models
        # For now, return dict as placeholder
        return "dict"
    elif schema_type in ["string", "integer", "number", "boolean", "file"]:
        # Use the normalizer for all known types
        return _normalize_type(schema_type)
    else:
        # Default fallback for any unrecognized type
        return _normalize_type(schema_type)

def _extract_schema_fields(schema, spec, is_openapi):
    """
    Recursively extract fields from schema properties.
    Returns dict of {field_name: python_type_string}
    Handles $ref references by resolving them first.
    """
    if not schema:
        return {}
    
    # Handle $ref at schema level - resolve and extract from resolved schema
    if "$ref" in schema:
        ref_path = schema["$ref"]
        resolved_schema = _resolve_schema_ref(ref_path, spec, is_openapi)
        if resolved_schema:
            return _extract_schema_fields(resolved_schema, spec, is_openapi)
        return {}
    
    fields = {}
    properties = schema.get("properties", {})
    
    # If no properties but type is object, check if this is a bare object that needs inline fields
    if not properties and schema.get("type") == "object":
        # This is an empty object schema with no properties defined
        return {}
    
    for prop_name, prop_schema in properties.items():
        field_type = _map_schema_to_type(prop_schema, spec, is_openapi)
        # Normalize the type before storing
        normalized_type = _normalize_type(field_type) if isinstance(field_type, str) and field_type in ["string", "integer", "number", "boolean", "file", "array", "object"] else field_type
        fields[prop_name] = normalized_type
    
    return fields

def _resolve_schema_ref(ref_path, spec, is_openapi):
    """
    Resolve $ref reference paths to actual schema definitions.
    OpenAPI 3.0: #/components/schemas/ModelName
    Swagger 2.0: #/definitions/ModelName
    """
    if not ref_path.startswith("#/"):
        return None
    
    parts = ref_path.lstrip("#/").split("/")
    current = spec
    
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    
    return current if isinstance(current, dict) else None

def swagger_to_tools(swagger_text):
    try:
        spec = json.loads(swagger_text)
    except json.JSONDecodeError:
        spec = yaml.safe_load(swagger_text)
    
    if spec is None:
        return [], {}

    tools = []
    models = {}
    base_url = ""
    security_schemes = {}

    is_openapi = "openapi" in spec

    # --- VALIDATION: Check required fields ---
    if is_openapi:
        # OpenAPI 3.0 requires servers field
        servers = spec.get("servers", [])
        if not servers or len(servers) == 0:
            raise ValueError(
                "❌ **OpenAPI spec missing 'servers' field**\n\n"
                "OpenAPI 3.0 requires at least one server. Example:\n"
                "```json\n"
                '"servers": [{"url": "https://api.example.com/v1"}]\n'
                "```\n\n"
                "See: https://swagger.io/specification/#servers-object"
            )
        base_url = servers[0].get("url", "")
        if not base_url:
            raise ValueError(
                "❌ **First server object has empty 'url'**\n\n"
                "Provide a valid server URL. Example:\n"
                "```json\n"
                '"servers": [{"url": "https://api.example.com/v1"}]\n'
                "```"
            )
        paths = spec.get("paths", {})
        security_schemes = spec.get("components", {}).get("securitySchemes", {})
    else:
        # Swagger 2.0 requires host, schemes, basePath
        host = spec.get("host", "")
        schemes = spec.get("schemes", [])
        base_path = spec.get("basePath", "")
        
        # Validation: Check for required fields (Issue #4)
        if not host:
            raise ValueError(
                "❌ **Swagger spec missing required 'host' field**\n\n"
                "Add the 'host' field to your Swagger spec. Example:\n"
                "```json\n"
                '"host": "api.example.com",\n'
                '"schemes": ["https"],\n'
                '"basePath": "/v2.0"\n'
                "```\n\n"
                "See: https://swagger.io/specification/v2/#fixed-fields"
            )
        if not schemes or len(schemes) == 0:
            raise ValueError(
                "❌ **Swagger spec missing 'schemes' field**\n\n"
                "Specify the protocol scheme. Example:\n"
                "```json\n"
                '"schemes": ["https"]\n'
                "```"
            )
        if "basePath" not in spec:
            raise ValueError(
                "❌ **Swagger spec missing 'basePath' field**\n\n"
                "Add the base path for your API. Example:\n"
                "```json\n"
                '"basePath": "/v2.0"\n'
                "```\n\n"
                "If your API has no version path, use: `\"basePath\": \"/\"`"
            )
        
        # Construct base_url with validation 
        base_url = f"{schemes[0]}://{host}{base_path}"
        paths = spec.get("paths", {})
        security_schemes = spec.get("securityDefinitions", {})

    auth_type = "None"
    auth_env = ""

    for name, scheme in security_schemes.items():
        if scheme.get("type") == "http" and scheme.get("scheme") == "bearer":
            auth_type = "Bearer Token"
            auth_env = name.upper() + "_TOKEN"
        elif scheme.get("type") == "apiKey":
            auth_type = "API Key (Header)"
            auth_env = scheme.get("name", name).upper()

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "delete", "patch"]:
                continue

            tool_name = details.get(
                "operationId",
                f"{method}_{path.strip('/').replace('/', '_').replace('{','').replace('}','')}"
            )

            args = OrderedDict()
            body_model = None
            body_fields = {}
            has_body = False

            # Parse parameters (Swagger 2.0 + OpenAPI 3.0 params)
            for param in details.get("parameters", []):
                p_name = param.get("name")
                p_in = param.get("in")

                if p_in in ["path", "query", "header"]:
                    # Extract type from param schema or direct type field
                    param_schema = param.get("schema", {})
                    if param_schema:
                        param_type = _map_schema_to_type(param_schema, spec, is_openapi)
                    elif param.get("type") == "array" and "items" in param:
                        # Swagger 2.0: array parameter with items at parameter level
                        param_type = _map_schema_to_type(param, spec, is_openapi=False)
                    else:
                        # Swagger 2.0: non-array type directly on parameter
                        raw_type = param.get("type", "str")
                        param_type = _normalize_type(raw_type)
                    args[p_name] = param_type
                elif p_in == "body":
                    # Swagger 2.0: body parameter with schema
                    has_body = True
                    body_schema = param.get("schema", {})
                    body_fields = _extract_schema_fields(body_schema, spec, is_openapi)
                elif p_in == "formData":
                    # Swagger 2.0: form data parameters
                    has_body = True
                    if param.get("type") == "array" and "items" in param:
                        # Array field with items at parameter level
                        param_type = _map_schema_to_type(param, spec, is_openapi=False)
                    else:
                        raw_type = param.get("type", "str")
                        param_type = _normalize_type(raw_type)
                    body_fields[p_name] = param_type

            # OpenAPI 3.0: requestBody
            if is_openapi and "requestBody" in details:
                has_body = True
                request_body = details["requestBody"]
                content = request_body.get("content", {})
                
                # Prefer application/json, fallback to first available
                schema = None
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                else:
                    first_content = next(iter(content.values()), {})
                    schema = first_content.get("schema", {})
                
                body_fields = _extract_schema_fields(schema, spec, is_openapi)

            # Create Pydantic model if body exists
            # Include model even if body_fields is empty - it's still a request body
            if has_body:
                if body_fields:
                    # Has fields - create proper Pydantic model
                    # Normalize all field types to valid Python types
                    normalized_fields = {}
                    for field_name, field_type in body_fields.items():
                        normalized_fields[field_name] = _normalize_type(field_type) if isinstance(field_type, str) else field_type
                    
                    model_name = f"{tool_name.title().replace('_','')}Request"
                    models[model_name] = normalized_fields
                    args["body"] = model_name
                    body_model = model_name
                else:
                    # Empty body_fields but has_body=True means there's a body schema
                    # Try to create a generic model
                    model_name = f"{tool_name.title().replace('_','')}Request"
                    # Create a generic dict-like model with a single data field
                    models[model_name] = {"data": "dict"}
                    args["body"] = model_name
                    body_model = model_name

            tools.append({
                "name": tool_name,
                "url": base_url + path,
                "method": method.upper(),
                "auth": auth_type,
                "auth_val": auth_env,
                "args": dict(args),
                "body_model": body_model,
                "has_file_fields": body_model and any(field_name == "file" for field_name in body_fields.keys()),
                "desc": details.get("summary", f"{method.upper()} {path}")
            })

    return tools, models

# ------------------------------------------------------------------
# LLM PROMPT GENERATION
# ------------------------------------------------------------------

from openai import OpenAI

def auto_generate_prompts(tools, api_key=None, provider="openai"):
    """
    Generate MCP-compliant prompt templates for API tools.
    One prompt per tool with specific arguments matching the tool's parameters.
    Supports both OpenAI and Groq providers.
    """
    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=api_key)
        model = "llama-3.1-8b-instant"
    else:
        if api_key:
            client = OpenAI(api_key=api_key)
        else:
            client = OpenAI()
        model = "gpt-4o"

    tool_descriptions = []
    for t in tools:
        args = ", ".join(t["args"].keys())
        tool_descriptions.append(
            f"Tool: {t['name']}\nDescription: {t['desc']}\nMethod: {t['method']}\nURL: {t['url']}\nArguments: {args}"
        )

    joined = "\n\n---\n\n".join(tool_descriptions)

    user_msg = f"""
You are an expert at creating MCP (Model Context Protocol) prompt templates for API tools.

For EACH API tool below, generate exactly ONE prompt template following MCP standards.

CRITICAL: The Prompt Name MUST be EXACTLY the same as the tool name for auto-linking in MCP.

Format requirement:
1. Prompt Name: MUST be identical to the tool name (this enables MCP auto-linking)
2. Prompt Arguments: Extract relevant arguments from the tool's parameter list (comma-separated)
3. Prompt Text: Write a clear, actionable instruction that uses {{{{argument_placeholders}}}} to reference the arguments

MCP Prompt Format:
- Name: [ToolName] - MUST EXACTLY match the tool name
- Arguments: [Extracted from tool args, comma-separated]
- Description: [One-line description of what the prompt does]
- Text: [Template that can use {{{{arg_name}}}} placeholders]

For example, if a tool is "GetUser" with arguments (id, limit, sort):
- Name: GetUser (EXACTLY the tool name)
- Arguments: id, limit, sort
- Description: Fetch user details by ID
- Text: "Query user with ID {{{{id}}}} and retrieve up to {{{{limit}}}} records, sorted by {{{{sort}}}}"

Tools:
{joined}

Generate exactly one complete MCP prompt template per tool. Format each as:
---
Tool: [tool_name]
Name: [tool_name] (MUST BE IDENTICAL)
Arguments: [arg1, arg2, ...]
Description: [description]
Text: [template text with placeholders]
---
    """

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that generates MCP-compliant prompts for API tools."},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7,
        max_tokens=1200
    )

    text = response.choices[0].message.content.strip()

    all_prompts = []
    current_tool = None
    current_prompt = {
        "name": "",
        "args": "",
        "text": "",
        "desc": ""
    }
    
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and separators
        if not line or line == "---":
            # If we have a complete prompt, save it
            if current_prompt["name"] and current_prompt["text"]:
                # Force prompt name to match tool name for MCP auto-linking
                if current_tool:
                    current_prompt["name"] = current_tool
                # Clean up prompt text: replace {{ with { and }} with }
                cleaned_text = current_prompt["text"].replace("{{", "{").replace("}}", "}")
                # Remove surrounding quotes if present
                cleaned_text = cleaned_text.strip('"\'')
                all_prompts.append({
                    "name": current_prompt["name"],
                    "args": current_prompt["args"],
                    "text": cleaned_text,
                    "desc": current_prompt["desc"]
                })
                current_prompt = {
                    "name": "",
                    "args": "",
                    "text": "",
                    "desc": ""
                }
            continue
        
        # Parse MCP format lines
        if line.lower().startswith("tool:"):
            current_tool = line.replace("Tool:", "").replace("tool:", "").strip()
        elif line.lower().startswith("name:"):
            current_prompt["name"] = line.replace("Name:", "").replace("name:", "").strip()
        elif line.lower().startswith("arguments:"):
            current_prompt["args"] = line.replace("Arguments:", "").replace("arguments:", "").strip()
        elif line.lower().startswith("description:"):
            current_prompt["desc"] = line.replace("Description:", "").replace("description:", "").strip()
        elif line.lower().startswith("text:"):
            # Capture text after "Text:" and continue on next lines
            current_prompt["text"] = line.replace("Text:", "").replace("text:", "").strip()
        elif current_prompt["name"] and line and not line.lower().startswith(("tool:", "name:", "arguments:", "description:")):
            # Continue capturing multi-line text
            if current_prompt["text"]:
                current_prompt["text"] += " " + line
            else:
                current_prompt["text"] = line
    
    # Don't forget the last prompt
    if current_prompt["name"] and current_prompt["text"]:
        # Clean up prompt text: replace {{ with { and }} with }
        cleaned_text = current_prompt["text"].replace("{{", "{").replace("}}", "}")
        # Remove surrounding quotes if present
        cleaned_text = cleaned_text.strip('"\'')
        all_prompts.append({
            "name": current_prompt["name"],
            "args": current_prompt["args"],
            "text": cleaned_text,
            "desc": current_prompt["desc"]
        })
    
    return all_prompts


# ------------------------------------------------------------------
# HELPER: Check if a model has file fields
# ------------------------------------------------------------------

def _model_has_file_fields(model_name, models):
    """Check if a Pydantic model has any file-type fields."""
    if model_name not in models:
        return False
    fields = models[model_name]
    return any(field_type == "str" and field_name == "file" for field_name, field_type in fields.items())


# ------------------------------------------------------------------
# MCP CODE GENERATOR
# ------------------------------------------------------------------

def generate_mcp_code(api_name, tools, prompts, models):
    # Filter models to only include those used by selected tools
    used_models = {}
    for tool in tools:
        if tool.get("body_model"):
            model_name = tool["body_model"]
            if model_name in models:
                used_models[model_name] = models[model_name]
    
    template_str = """from mcp.server.fastmcp import FastMCP
import requests
import os
import re
from pydantic import BaseModel
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ------------------ Pydantic Models ------------------
{% for model, fields in models.items() %}
class {{ model }}(BaseModel):
{% for name, type in fields.items() %}
    {{ name }}: {{ type }}
{% endfor %}

{% endfor %}
# --------- HTTP Resilience & Helper Functions ---------
def _create_session_with_retries():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def _extract_path_params(base_url, args):
    \"\"\"Extract and substitute path parameters from URL.\"\"\"
    remaining = args.copy()
    path_params = re.findall(r"{(.*?)}", base_url)
    for param in path_params:
        if param in remaining:
            base_url = base_url.replace("{" + param + "}", str(remaining.pop(param)))
    return base_url, remaining

def _to_dict(obj):
    \"\"\"Convert Pydantic model or dict to dict.\"\"\"
    if hasattr(obj, 'dict') and callable(obj.dict):
        return obj.dict()
    elif isinstance(obj, dict):
        return obj
    return obj

_session = _create_session_with_retries()
# -------------------------------------------------------------------

# Initialize FastMCP Server: {{ api_name }}
mcp = FastMCP("{{ api_name }}")

{% for tool in tools %}
@mcp.tool()
def {{ tool.name }}({% for arg, type in tool.args.items() %}{{ arg }}: {{ type }}{% if not loop.last %}, {% endif %}{% endfor %}):
    \"\"\"{{ tool.desc }}\"\"\"

    args_dict = { {% for arg in tool.args.keys() %}"{{ arg }}": {{ arg }}{% if not loop.last %}, {% endif %}{% endfor %} }

    base_url, remaining_args = _extract_path_params("{{ tool.url }}", args_dict)

    headers = {}
    {% if tool.auth and tool.auth != 'None' %}
    {% if tool.auth == 'Bearer Token' %}
    headers["Authorization"] = f"Bearer {os.environ.get('{{ tool.auth_val }}', 'YOUR_TOKEN_HERE')}"
    {% elif tool.auth == 'API Key (Header)' %}
    headers["X-API-KEY"] = os.environ.get('{{ tool.auth_val }}', 'YOUR_KEY_HERE')
    {% endif %}
    {% endif %}

    payload = None
    {% if tool.body_model %}
    body_data = remaining_args.pop("body", None)
    if body_data:
        payload = _to_dict(body_data)
    {% endif %}

    query_params = remaining_args if remaining_args else None

    try:
        method_lower = "{{ tool.method }}".lower()
        request_kwargs = {
            "params": query_params,
            "headers": headers,
            "timeout": 15
        }
        
        if method_lower in ["post", "put", "patch", "delete"] and payload is not None:
            {% if tool.has_file_fields %}
            request_kwargs["files"] = payload
            {% else %}
            request_kwargs["json"] = payload
            {% endif %}
        
        response = _session.{{ tool.method.lower() }}(base_url, **request_kwargs)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e), "url_attempted": base_url}

{% endfor %}
# --------- MCP Prompts ---------
{% for prompt in prompts %}
@mcp.prompt()
def {{ prompt.name }}_prompt():
    \"\"\"{{ prompt.desc }}\"\"\"
    return {
        "name": "{{ prompt.name }}",
        "arguments": [{% for arg in prompt.args.split(', ') if arg %}"{{ arg.strip() }}"{% if not loop.last %}, {% endif %}{% endfor %}],
        "description": "{{ prompt.desc }}",
        "text": "{{ prompt.text }}"
    }

{% endfor %}
if __name__ == "__main__":
    mcp.run()
"""
    return Template(template_str).render(
        api_name=api_name,
        tools=tools,
        prompts=prompts,
        models=used_models
    )

# ------------------------------------------------------------------
# STREAMLIT UI
# ------------------------------------------------------------------

st.set_page_config(page_title="MCP Forge Pro", layout="wide", page_icon="⚙️")

# ===== SIDEBAR NAVIGATION =====
with st.sidebar:
    st.title("🛠️ MCP Forge")
    st.markdown("---")
    
    if st.button("🏠 Home", use_container_width=True, key="btn_home", type="secondary"):
        # Clean everything when returning home
        st.session_state.tools = []
        st.session_state.prompts = []
        st.session_state.models = {}
        st.session_state.api_name = "MyAPI"
        st.session_state.swagger_selection = {}
        st.session_state.swagger_text = ""
        st.session_state.wsdl_text = ""
        st.session_state.step = 0
        st.rerun()
    
    if st.button("⚡ Quick Start", use_container_width=True, key="quickstart", type="primary", disabled=st.session_state.step > 0):
        # Clean slate
        st.session_state.tools = []
        st.session_state.prompts = []
        st.session_state.models = {}
        st.session_state.api_name = "MyAPI"
        st.session_state.swagger_selection = {}
        st.session_state.swagger_text = ""
        st.session_state.wsdl_text = ""
        st.session_state.step = 1
        st.rerun()
    
    # Reset button only enabled from step 1 onwards
    if st.session_state.step >= 1:
        if st.button("🔄 Reset", use_container_width=True, key="reset_project", type="secondary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.step = 1
            st.rerun()
    
    st.markdown("---")

# ============ STEP 0: HOME SCREEN ============
if st.session_state.step == 0:
    st.title("🚀 Welcome to MCP Forge Pro")
    st.markdown("""
    ### Convert REST APIs into MCP Servers in 3 Steps
    
    **MCP Forge Pro** automates the generation of production-ready Model Context Protocol (MCP) servers 
    from your REST APIs. No more manual coding—just paste your OpenAPI/Swagger spec and let the tool handle the rest.
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📡", "APIs Supported", "OpenAPI 3.0 & Swagger 2.0")
    with col2:
        st.metric("🚢", "Deploy Anywhere", "Local, Docker, Claude Desktop")
    
    st.markdown("---")
    
    st.subheader("📋 How It Works")
    
    step1, step2, step3 = st.columns(3)
    
    with step1:
        st.markdown("""
        ### Step 1: Import API
        
        - Paste your OpenAPI/Swagger spec
        - Or manually add individual endpoints
        - Select which APIs to include
        """)
    
    with step2:
        st.markdown("""
        ### Step 2: Design Prompts ✅
        
        - Auto-generate prompt templates with LLM
        - Or write custom prompts
        - Edit and refine each prompt template
        
        *Choose OpenAI or Groq for generation*
        """)
    
    with step3:
        st.markdown("""
        ### Step 3: Generate & Deploy
        
        - Get production-ready Python code
        - Choose deployment: Local, Docker, or Claude Desktop
        - Download & run instantly
        """)
    
    st.markdown("---")
    
    st.subheader("✨ Key Features")
    
    features = {
        "🔗 Full API Parsing": "Automatically extracts endpoints, parameters, and request bodies from OpenAPI/Swagger specs",
        "🛡️ HTTP Resilience": "Built-in retry logic with exponential backoff for reliable API calls",
        "🔐 Auth Support": "Handles Bearer Token, API Key, and header authentication automatically",
        "📦 Pydantic Models": "Generates type-safe request/response models for all API parameters",
        "⚙️ FastMCP Integration": "Wraps APIs as MCP tools—ready to use with Claude and other AI models",
        "🚀 Multiple Deployments": "Local execution, Docker containers, Docker Compose, and Claude Desktop configs",
        "🤖 Prompt Templates": "Auto-generate or customize prompt templates for each API tool",
        "📥 One-Click Download": "Export complete server code and deployment configs in seconds"
    }
    
    for feature, description in features.items():
        st.markdown(f"**{feature}** — {description}")
    
    st.markdown("---")
    st.markdown("### 🎯 Ready to Get Started?")
    
    st.info("ℹ️ Use the Quick Start button in the header to begin.")

# ---------------- STEP 1 ----------------
elif st.session_state.step == 1:
    st.header("1️⃣ Configure API Tools")
    
    st.caption("💡 **Tips:** Keep your server name short (e.g., 'github', 'slack') - it'll be used for file naming and deployment")
    st.session_state.api_name = st.text_input("MCP Server Name", st.session_state.api_name)
    
    st.markdown("---")
    
    mode = st.radio("Tool Creation Mode", ["Import from OpenAPI / Swagger", "Import from SOAP / Wsdl", "Manual Entry"], horizontal=True)

    if mode == "Import from OpenAPI / Swagger":
        # Only show text area if APIs haven't been loaded yet
        if "all_swagger_tools" not in st.session_state or not st.session_state.all_swagger_tools:
            st.session_state.swagger_text = st.text_area("Paste OpenAPI / Swagger", height=300, value=st.session_state.swagger_text)
            
            # Disable button if text area is empty
            if st.button("📥 Load APIs", key="load_swagger", type="primary", disabled=not st.session_state.swagger_text.strip()):
                try:
                    tools, models = swagger_to_tools(st.session_state.swagger_text)
                    if not tools:
                        st.warning("⚠️ No API endpoints found in the Swagger/OpenAPI spec. Please check the file and make sure it contains valid paths.")
                    else:
                        st.session_state.all_swagger_tools = tools
                        st.session_state.models.update(models)
                        st.session_state.swagger_selection = {t["name"]: False for t in tools}
                        st.session_state.swagger_text = ""  # Clear to free memory
                        st.success(f"✅ Loaded {len(tools)} API endpoints from Swagger")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Invalid Swagger/OpenAPI specification: {str(e)}\n\nPlease paste a valid OpenAPI 3.0 or Swagger 2.0 JSON/YAML file.")
        
        if "all_swagger_tools" in st.session_state and st.session_state.all_swagger_tools:
            st.info("✅ APIs loaded successfully! Select the ones you want to add below.")
            st.markdown("### ✅ Select APIs to Add as Tools")
            for idx, t in enumerate(st.session_state.all_swagger_tools):
                label = f"**{t['method']}** `{t['url']}` — {t['desc']}"
                st.session_state.swagger_selection[t["name"]] = st.checkbox(label, value=st.session_state.swagger_selection.get(t["name"], False), key=f"cb_swagger_{idx}_{t['name']}")

            if st.button("⚙️ Generate Selected Tools", key="generate_tools_selected", type="primary"):
                selected_tools = [t for t in st.session_state.all_swagger_tools if st.session_state.swagger_selection.get(t["name"], False)]
                # Only add tools that aren't already in the tools list
                existing_tool_names = {t["name"] for t in st.session_state.tools}
                new_tools = [t for t in selected_tools if t["name"] not in existing_tool_names]
                st.session_state.tools.extend(new_tools)
                if new_tools:
                    st.success(f"Added {len(new_tools)} new tools")
                if len(selected_tools) > len(new_tools):
                    st.info(f"⚠️ {len(selected_tools) - len(new_tools)} tool(s) were already added")

    if mode == "Import from SOAP / Wsdl":
        st.session_state.wsdl_text = st.text_area("Paste SOAP / WSDL Definition", height=300, value=st.session_state.wsdl_text)
        
        # Disable button if text area is empty
        if st.button("📥 Load APIs", key="load_wsdl", type="primary", disabled=not st.session_state.wsdl_text.strip()):
            try:
                tools, models = wsdl_to_tools(st.session_state.wsdl_text)
                if not tools:
                    st.warning("⚠️ No API endpoints found in the WSDL spec. Please check the file and make sure it contains valid service definitions.")
                else:
                    st.session_state.all_wsdl_tools = tools
                    st.session_state.models.update(models)
                    st.session_state.swagger_selection = {t["name"]: False for t in tools}
                    st.session_state.wsdl_text = ""  # Clear to free memory
                    st.success(f"✅ Loaded {len(tools)} API endpoints from WSDL")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Invalid WSDL specification: {str(e)}\n\nPlease paste a valid WSDL XML file.")
            st.info("✅ APIs loaded successfully! Select the ones you want to add below.")
            st.markdown("### ✅ Select APIs to Add as Tools")
            for idx, t in enumerate(st.session_state.all_wsdl_tools):
                label = f"**{t['method']}** `{t['url']}` — {t['desc']}"
                st.session_state.swagger_selection[t["name"]] = st.checkbox(label, value=st.session_state.swagger_selection.get(t["name"], False), key=f"cb_wsdl_{idx}_{t['name']}")

            if st.button("⚙️ Generate Selected Tools WSDL", key="generate_tools_wsdl", type="primary"):
                selected_tools = [t for t in st.session_state.all_wsdl_tools if st.session_state.swagger_selection.get(t["name"], False)]
                # Only add tools that aren't already in the tools list
                existing_tool_names = {t["name"] for t in st.session_state.tools}
                new_tools = [t for t in selected_tools if t["name"] not in existing_tool_names]
                st.session_state.tools.extend(new_tools)
                if new_tools:
                    st.success(f"Added {len(new_tools)} new tools")
                if len(selected_tools) > len(new_tools):
                    st.info(f"⚠️ {len(selected_tools) - len(new_tools)} tool(s) were already added")

    elif mode == "Manual Entry":
        with st.form("tool_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Tool Name", "get_repo")
                url = st.text_input("Full URL", "https://api.github.com/repos/{owner}/{repo}")
                method = st.selectbox("HTTP Method", ["GET", "POST", "PUT", "DELETE"])
            with col2:
                auth = st.selectbox("Auth Mechanism", ["None", "Bearer Token", "API Key (Header)"])
                auth_val = st.text_input("Env Var Name", "API_TOKEN")
                args_raw = st.text_area("Arguments JSON", '{"owner": "str"}')
            desc = st.text_area("Tool Description", "Description")
            if st.form_submit_button("➕ Add Tool", type="primary"):
                st.session_state.tools.append({"name": name, "url": url, "method": method, "auth": auth, "auth_val": auth_val, "args": json.loads(args_raw), "body_model": None, "desc": desc})

    if st.session_state.tools:
        st.subheader("✅ Current Tools")
        for idx, tool in enumerate(st.session_state.tools):
            with st.expander(f"⚙️ {tool['name']} | {tool['method']} {tool['url']}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.tools[idx]["name"] = st.text_input(
                        "Tool Name",
                        value=tool["name"],
                        key=f"edit_tool_name_{idx}"
                    )
                    st.session_state.tools[idx]["url"] = st.text_input(
                        "Full URL",
                        value=tool["url"],
                        key=f"edit_tool_url_{idx}"
                    )
                    st.session_state.tools[idx]["method"] = st.selectbox(
                        "HTTP Method",
                        ["GET", "POST", "PUT", "DELETE"],
                        index=["GET", "POST", "PUT", "DELETE"].index(tool["method"]),
                        key=f"edit_tool_method_{idx}"
                    )
                with col2:
                    st.session_state.tools[idx]["auth"] = st.selectbox(
                        "Auth Mechanism",
                        ["None", "Bearer Token", "API Key (Header)"],
                        index=["None", "Bearer Token", "API Key (Header)"].index(tool["auth"]),
                        key=f"edit_tool_auth_{idx}"
                    )
                    st.session_state.tools[idx]["auth_val"] = st.text_input(
                        "Env Var Name",
                        value=tool["auth_val"],
                        key=f"edit_tool_auth_val_{idx}"
                    )
                
                st.session_state.tools[idx]["desc"] = st.text_area(
                    "Tool Description",
                    value=tool["desc"],
                    height=100,
                    key=f"edit_tool_desc_{idx}"
                )
                
                if st.button("🗑️ Delete Tool", key=f"delete_tool_{idx}", type="secondary"):
                    st.session_state.tools.pop(idx)
                    st.rerun()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back", key="back_step1", type="secondary"):
                st.session_state.step = 0
                st.rerun()
        with col2:
            if st.button("Next ➡️", key="next_step1", type="primary"):
                st.session_state.step = 2
                st.rerun()

# ---------------- STEP 2 ----------------
elif st.session_state.step == 2:
    st.header("2️⃣ Design Prompts")

    st.info("💡 Choose your LLM provider for prompt generation. Groq is free and fast!")
    
    col1, col2, col3 = st.columns([1.5, 1.5, 1])
    with col1:
        provider = st.selectbox("LLM Provider", ["openai", "groq"], format_func=lambda x: "🤖 OpenAI (GPT-4o)" if x == "openai" else "⚡ Groq (Mixtral)")
    with col2:
        api_key = st.text_input(
            "API Key",
            type="password",
            placeholder="sk-... (OpenAI) or gsk-... (Groq)"
        )
    with col3:
        if st.button("🤖 Generate", type="primary"):
            if not api_key:
                st.error("Please enter your API key.")
            else:
                with st.spinner("Generating prompts using LLM..."):
                    try:
                        auto_prompts = auto_generate_prompts(
                            st.session_state.tools,
                            api_key=api_key,
                            provider=provider
                        )
                        st.session_state.prompts.extend(auto_prompts)
                        st.success(f"Generated {len(auto_prompts)} prompt templates!")
                    except Exception as e:
                        error_msg = str(e)
                        if "insufficient_quota" in error_msg or "429" in error_msg:
                            st.error("❌ Quota Exceeded\n\nCheck your API account billing and try again.")
                        elif "authentication" in error_msg.lower() or "api" in error_msg.lower():
                            st.error(f"❌ Authentication Error\n\nCheck that your API key is correct:\n{error_msg}")
                        else:
                            st.error(f"Error generating prompts: {error_msg}")

    with st.form("prompt_form", clear_on_submit=True):
        name = st.text_input("Prompt Name", "summarize")
        args = st.text_input("Arguments", "id")
        text = st.text_area("Prompt Template", "Summarize the result")
        if st.form_submit_button("➕ Add Prompt", type="primary"):
            st.session_state.prompts.append({"name": name, "args": args, "text": text, "desc": "Prompt"})

    if st.session_state.prompts:
        st.subheader("📋 Prompts List")
        for idx, prompt in enumerate(st.session_state.prompts):
            preview_text = prompt['text'][:80].replace('\n', ' ') + ('...' if len(prompt['text']) > 80 else '')
            with st.expander(f"✏️ {prompt['name']} | {preview_text}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.prompts[idx]["name"] = st.text_input(
                        "Prompt Name",
                        value=prompt["name"],
                        key=f"edit_name_{idx}"
                    )
                    st.session_state.prompts[idx]["args"] = st.text_input(
                        "Arguments",
                        value=prompt["args"],
                        key=f"edit_args_{idx}"
                    )
                with col2:
                    st.session_state.prompts[idx]["desc"] = st.text_input(
                        "Description",
                        value=prompt.get("desc", ""),
                        key=f"edit_desc_{idx}"
                    )
                
                st.session_state.prompts[idx]["text"] = st.text_area(
                    "Prompt Template",
                    value=prompt["text"],
                    height=150,
                    key=f"edit_text_{idx}"
                )
                
                if st.button("🗑️ Delete", key=f"delete_{idx}", type="secondary"):
                    st.session_state.prompts.pop(idx)
                    st.rerun()
    
    # Navigation buttons always available
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", key="back_step2", use_container_width=True, type="secondary"):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("Generate Code 🚀", key="generate_code", use_container_width=True, type="primary"):
            st.session_state.step = 3
            st.rerun()

# ---------------- STEP 3 ----------------
elif st.session_state.step == 3:
    st.header("3️⃣ Final MCP Server Code")

    filename = f"{st.session_state.api_name.lower()}_server.py"
    code = generate_mcp_code(st.session_state.api_name, st.session_state.tools, st.session_state.prompts, st.session_state.models)

    st.code(code, language="python")
    st.download_button("💾 Download Python Server", code, filename, type="primary")

    secrets = list(set(t["auth_val"] for t in st.session_state.tools if t["auth"] != "None"))

    t1, t2, t3, t4 = st.tabs(["Local Execution", "Claude Desktop", "Dockerfile", "Docker Compose"])

    with t1:
        local_cmd = f"""# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux or: venv\\Scripts\\activate (Windows)

# Install dependencies
pip install fastmcp requests pydantic urllib3

# Set authentication (if needed)"""
        if secrets:
            for s in secrets:
                local_cmd += f"\nexport {s}='your-token-here'"
        local_cmd += f"\n\n# Run the MCP server\npython3 {filename}"
        st.code(local_cmd)

    with t2:
        st.markdown("**File location:** `~/.config/Claude/claude_desktop_config.json` (or `%APPDATA%\\\\Claude\\\\claude_desktop_config.json` on Windows)")
        claude_config = {"mcpServers": {st.session_state.api_name.lower(): {"command": "python3", "args": [filename], "env": {s: "YOUR_ACTUAL_TOKEN" for s in secrets} if secrets else {}}}}
        st.json(claude_config)
        st.info("💡 Replace 'YOUR_ACTUAL_TOKEN' values with your real credentials before using in Claude Desktop.")

    with t3:
        env_vars = ""
        if secrets:
            env_vars = "\n".join([f"ENV {s}=YOUR_TOKEN_{i}" for i, s in enumerate(secrets)])
            env_vars = "\n" + env_vars + "\n"
        dockerfile = f"""FROM python:3.11-slim
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastmcp requests pydantic urllib3

# Copy server file
COPY {filename} .
{env_vars if env_vars else ""}
# Run with python3 explicitly
CMD ["python3", "{filename}"]"""
        st.code(dockerfile, "dockerfile")
        st.download_button("💾 Download Dockerfile", dockerfile, "Dockerfile", type="primary")

    with t4:
        compose = f"""version: '3.8'
services:
  mcp:
    build: .
    container_name: {st.session_state.api_name.lower()}_server
    environment:"""
        if secrets:
            for s in secrets:
                compose += f"\n      - {s}=${{{s}}}"
        else:
            compose += "\n      {}"
        compose += "\n    restart: unless-stopped"
        st.code(compose, "yaml")
        st.download_button("💾 Download docker-compose.yml", compose, "docker-compose.yml", type="primary")
        
        st.markdown("### .env file (create in same directory):")
        env_content = ""
        if secrets:
            env_content = "\n".join([f"{s}=your_actual_token_here" for s in secrets])
        else:
            env_content = "# No authentication required"
        st.code(env_content, "bash")
        st.markdown("**Run with:** `docker-compose up -d`")
    
    st.markdown("---")
    st.subheader("🔄 Modify Your Configuration")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("← Reconfigure Tools", use_container_width=True, key="back_to_tools", type="secondary"):
            st.session_state.step = 1
            st.rerun()
    
    with col2:
        if st.button("← Back to Prompts", use_container_width=True, key="back_step3", type="secondary"):
            st.session_state.step = 2
            st.rerun()
    
    with col3:
        pass  # Placeholder for alignment
