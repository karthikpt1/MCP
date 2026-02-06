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
    st.session_state.step = 1
if 'swagger_selection' not in st.session_state:
    st.session_state.swagger_selection = {}

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

    tools = []
    models = {}
    base_url = ""
    security_schemes = {}

    is_openapi = "openapi" in spec

    if is_openapi:
        servers = spec.get("servers", [])
        if servers:
            base_url = servers[0].get("url", "")
        paths = spec.get("paths", {})
        security_schemes = spec.get("components", {}).get("securitySchemes", {})
    else:
        schemes = spec.get("schemes", ["https"])
        host = spec.get("host", "")
        base_path = spec.get("basePath", "")
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
                    else:
                        # Swagger 2.0: type is directly on parameter, not nested in schema
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

def auto_generate_prompts(tools):
    """
    Batch send all tools to the LLM and get multiple prompt templates for each.
    """
    client = OpenAI()

    instructions = [
        {
            "role": "system",
            "content": "You are an expert assistant that generates useful and safe prompt templates for API tools."
        }
    ]

    tool_descriptions = []
    for t in tools:
        args = ", ".join(t["args"].keys())
        tool_descriptions.append(
            f"Tool: {t['name']}\nDescription: {t['desc']}\nMethod: {t['method']}\nURL: {t['url']}\nArguments: {args}"
        )

    joined = "\n\n---\n\n".join(tool_descriptions)

    user_msg = f"""
    For each API tool below, generate three distinct prompt templates:
    1) Summarize output intent,
    2) Analyze possible errors and how to handle them,
    3) Compare results or give context to output.

    For each template, return only the text. Label them clearly.

    Tools:
    {joined}
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that generates API prompts."},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7,
        max_tokens=1500
    )

    text = response.choices[0].message.content.strip()

    all_prompts = []
    current_tool = None
    lines = text.split("\n")
    for line in lines:
        if line.startswith("Tool:"):
            current_tool = line.replace("Tool:", "").strip()
        elif line and current_tool:
            parts = line.split(":", 1)
            if len(parts) == 2:
                prompt_text = parts[1].strip()
                all_prompts.append({
                    "name": f"{current_tool}_auto",
                    "args": "",
                    "text": prompt_text,
                    "desc": f"Auto prompt for {current_tool}"
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
# --------- HTTP Resilience: Session with Retry Strategy ---------
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

_session = _create_session_with_retries()
# -------------------------------------------------------------------

# Initialize FastMCP Server: {{ api_name }}
mcp = FastMCP("{{ api_name }}")

{% for tool in tools %}
@mcp.tool()
def {{ tool.name }}({% for arg, type in tool.args.items() %}{{ arg }}: {{ type }}{% if not loop.last %}, {% endif %}{% endfor %}):
    \"\"\"{{ tool.desc }}\"\"\"

    args_dict = { {% for arg in tool.args.keys() %}"{{ arg }}": {{ arg }}{% if not loop.last %}, {% endif %}{% endfor %} }

    base_url = "{{ tool.url }}"
    remaining_args = args_dict.copy()

    path_params = re.findall(r"{(.*?)}", base_url)
    for param in path_params:
        if param in remaining_args:
            base_url = base_url.replace("{" + param + "}", str(remaining_args.pop(param)))

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
    body_data = remaining_args.pop("body")
    {% if tool.has_file_fields %}
    # For file uploads, use multipart/form-data instead of JSON
    payload = {{ tool.body_model }}(**body_data).dict() if isinstance(body_data, dict) else body_data.dict()
    # Remove file field from headers so requests can set proper Content-Type for multipart
    headers.pop('Content-Type', None)
    {% else %}
    payload = {{ tool.body_model }}(**body_data).dict() if isinstance(body_data, dict) else body_data.dict()
    {% endif %}
    {% endif %}

    # Send remaining args as query params for GET, or for other methods if they exist
    query_params = remaining_args if remaining_args else None

    try:
        # Only send json payload for POST/PUT/PATCH/DELETE, not for GET
        method_lower = "{{ tool.method }}".lower()
        request_kwargs = {
            "params": query_params,
            "headers": headers,
            "timeout": 15
        }
        {% if tool.has_file_fields %}
        # For file uploads, use files parameter (multipart/form-data)
        if method_lower in ["post", "put", "patch", "delete"] and payload is not None:
            request_kwargs["files"] = payload
        {% else %}
        # For regular JSON payloads, use json parameter
        if method_lower in ["post", "put", "patch", "delete"] and payload is not None:
            request_kwargs["json"] = payload
        {% endif %}
        
        response = _session.{{ tool.method.lower() }}(base_url, **request_kwargs)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e), "url_attempted": base_url}

{% endfor %}
{% for prompt in prompts %}
@mcp.prompt()
def {{ prompt.name }}({{ prompt.args }}):
    \"\"\"{{ prompt.desc }}\"\"\"
    return f\"\"\"{{ prompt.text }}\"\"\"

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

with st.sidebar:
    st.title("🛠️ MCP Forge")
    st.session_state.api_name = st.text_input("Server Name", st.session_state.api_name)
    st.markdown("---")
    if st.button("Reset Entire Project", type="primary", key="reset_project"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ---------------- STEP 1 ----------------
if st.session_state.step == 1:
    st.header("1️⃣ Configure API Tools")
    mode = st.radio("Tool Creation Mode", ["Import from OpenAPI / Swagger", "Import from SOAP / Wsdl", "Manual Entry"], horizontal=True)

    if mode == "Import from OpenAPI / Swagger":
        swagger_text = st.text_area("Paste OpenAPI / Swagger", height=300)
        if st.button("📥 Load APIs", key="load_swagger"):
            tools, models = swagger_to_tools(swagger_text)
            st.session_state.all_swagger_tools = tools
            st.session_state.models.update(models)
            st.session_state.swagger_selection = {t["name"]: False for t in tools}
            st.success(f"Loaded {len(tools)} API endpoints from Swagger")

        if "all_swagger_tools" in st.session_state and st.session_state.all_swagger_tools:
            st.markdown("### ✅ Select APIs to Add as Tools")
            for t in st.session_state.all_swagger_tools:
                label = f"**{t['method']}** `{t['url']}` — {t['desc']}"
                st.session_state.swagger_selection[t["name"]] = st.checkbox(label, value=st.session_state.swagger_selection.get(t["name"], False), key=f"cb_{t['name']}")

            if st.button("⚙️ Generate Selected Tools", key="generate_tools_selected"):
                selected_tools = [t for t in st.session_state.all_swagger_tools if st.session_state.swagger_selection.get(t["name"], False)]
                st.session_state.tools.extend(selected_tools)
                st.success(f"Added {len(selected_tools)} selected tools")

    if mode == "Import from SOAP / Wsdl":
        wsdl_text = st.text_area("Paste SOAP / WSDL Definition", height=300)
        if st.button("📥 Load APIs", key="load_wsdl"):
            tools, models = wsdl_to_tools(wsdl_text)
            st.session_state.all_wsdl_tools = tools
            st.session_state.models.update(models)
            st.session_state.swagger_selection = {t["name"]: False for t in tools}
            st.success(f"Loaded {len(tools)} API endpoints from Swagger")

        if "all_swagger_tools" in st.session_state and st.session_state.all_swagger_tools:
            st.markdown("### ✅ Select APIs to Add as Tools")
            for t in st.session_state.all_swagger_tools:
                label = f"**{t['method']}** `{t['url']}` — {t['desc']}"
                st.session_state.swagger_selection[t["name"]] = st.checkbox(label, value=st.session_state.swagger_selection.get(t["name"], False), key=f"cb_{t['name']}")

            if st.button("⚙️ Generate Selected Tools", key="generate_tools_selected"):
                selected_tools = [t for t in st.session_state.all_swagger_tools if st.session_state.swagger_selection.get(t["name"], False)]
                st.session_state.tools.extend(selected_tools)
                st.success(f"Added {len(selected_tools)} selected tools")

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
            if st.form_submit_button("➕ Add Tool"):
                st.session_state.tools.append({"name": name, "url": url, "method": method, "auth": auth, "auth_val": auth_val, "args": json.loads(args_raw), "body_model": None, "desc": desc})

    if st.session_state.tools:
        st.subheader("✅ Current Tools")
        st.table(st.session_state.tools)
        if st.button("Next ➡️", key="next_step1"):
            st.session_state.step = 2
            st.rerun()

# ---------------- STEP 2 ----------------
elif st.session_state.step == 2:
    st.header("2️⃣ Design Prompts")

    if st.button("🤖 Auto-Generate Diverse Prompts from Tools"):
        with st.spinner("Generating prompts using LLM..."):
            auto_prompts = auto_generate_prompts(st.session_state.tools)
            st.session_state.prompts.extend(auto_prompts)
        st.success(f"Generated {len(auto_prompts)} prompt templates!")

    with st.form("prompt_form", clear_on_submit=True):
        name = st.text_input("Prompt Name", "summarize")
        args = st.text_input("Arguments", "id")
        text = st.text_area("Prompt Template", "Summarize the result")
        if st.form_submit_button("➕ Add Prompt"):
            st.session_state.prompts.append({"name": name, "args": args, "text": text, "desc": "Prompt"})

    if st.session_state.prompts:
        st.table(st.session_state.prompts)
        if st.button("Generate Code 🚀", key="generate_code"):
            st.session_state.step = 3
            st.rerun()

# ---------------- STEP 3 ----------------
elif st.session_state.step == 3:
    st.header("3️⃣ Final MCP Server Code")

    filename = f"{st.session_state.api_name.lower()}_server.py"
    code = generate_mcp_code(st.session_state.api_name, st.session_state.tools, st.session_state.prompts, st.session_state.models)

    st.code(code, language="python")
    st.download_button("💾 Download Python Server", code, filename)

    secrets = list(set(t["auth_val"] for t in st.session_state.tools if t["auth"] != "None"))

    t1, t2, t3, t4 = st.tabs(["Local Execution", "Claude Desktop", "Dockerfile", "Docker Compose"])

    with t1:
        st.code("pip install fastmcp requests pydantic\npython " + filename)

    with t2:
        st.json({"mcpServers": {st.session_state.api_name.lower(): {"command": "python", "args": [filename], "env": {s: "YOUR_TOKEN" for s in secrets}}}})

    with t3:
        dockerfile = f"""FROM python:3.11-slim
WORKDIR /app
RUN pip install fastmcp requests pydantic
COPY {filename} .
CMD ["python", "{filename}"]"""
        st.code(dockerfile, "dockerfile")
        st.download_button("💾 Download Dockerfile", dockerfile, "Dockerfile")

    with t4:
        compose = "version: '3.8'\nservices:\n  mcp:\n    build: .\n    environment:\n"
        for s in secrets:
            compose += f"      - {s}=${{{s}}}\n"
        st.code(compose, "yaml")
        st.download_button("💾 Download docker-compose.yml", compose, "docker-compose.yml")
