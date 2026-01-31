import streamlit as st
import json
import os
import re
import yaml
from collections import OrderedDict
from jinja2 import Template

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

def swagger_to_tools(swagger_text):
    try:
        spec = json.loads(swagger_text)
    except json.JSONDecodeError:
        spec = yaml.safe_load(swagger_text)

    tools = []
    models = {}
    base_url = ""
    security_schemes = {}

    # -------- Detect OpenAPI vs Swagger --------
    is_openapi = "openapi" in spec

    # -------- Base URL --------
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

    # -------- Auto-detect Auth --------
    auth_type = "None"
    auth_env = ""

    for name, scheme in security_schemes.items():
        if scheme.get("type") == "http" and scheme.get("scheme") == "bearer":
            auth_type = "Bearer Token"
            auth_env = name.upper() + "_TOKEN"
        elif scheme.get("type") == "apiKey":
            auth_type = "API Key (Header)"
            auth_env = scheme.get("name", name).upper()

    # -------- Parse Paths --------
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

            
            # -------- Parameters --------
            body_fields = {}
            has_body = False

            for param in details.get("parameters", []):
                p_name = param.get("name")
                p_in = param.get("in")

                # Path, query, or header parameters → normal args
                if p_in in ["path", "query", "header"]:
                    args[p_name] = "str"

                # Swagger 2.0 formData or body → Pydantic model
                elif p_in in ["formData", "body"]:
                    has_body = True
                    if p_in == "body":
                        schema = param.get("schema", {}).get("properties", {})
                        for k in schema.keys():
                            body_fields[k] = "str"
                    else:
                        # formData parameters
                        body_fields[p_name] = "str"

            # -------- Create Pydantic model for Swagger 2.0 --------
            if has_body and body_fields:
                model_name = f"{tool_name.title().replace('_','')}Request"
                models[model_name] = body_fields
                args["body"] = model_name
                body_model = model_name


            # -------- Request Body → Pydantic --------
            if is_openapi and "requestBody" in details:
                content = details["requestBody"].get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    model_name = f"{tool_name.title().replace('_','')}Request"

                    fields = {}
                    for k, v in schema.get("properties", {}).items():
                        fields[k] = "str"

                    if fields:
                        models[model_name] = fields
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
                "desc": details.get("summary", f"{method.upper()} {path}")
            })

    return tools, models

# ------------------------------------------------------------------
# JINJA2 MCP CODE GENERATOR (WITH PYDANTIC)
# ------------------------------------------------------------------

def generate_mcp_code(api_name, tools, prompts, models):
    template_str = """from mcp.server.fastmcp import FastMCP
import requests
import os
import re
from pydantic import BaseModel

# ------------------ Pydantic Models ------------------
{% for model, fields in models.items() %}
class {{ model }}(BaseModel):
{% for name, type in fields.items() %}
    {{ name }}: {{ type }}
{% endfor %}

{% endfor %}
# -----------------------------------------------------

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
    {% if tool.auth == 'Bearer Token' %}
    headers["Authorization"] = f"Bearer {os.environ.get('{{ tool.auth_val }}', 'YOUR_TOKEN_HERE')}"
    {% elif tool.auth == 'API Key (Header)' %}
    headers["X-API-KEY"] = os.environ.get('{{ tool.auth_val }}', 'YOUR_KEY_HERE')
    {% endif %}

    payload = None
    {% if tool.body_model %}
    payload = remaining_args.pop("body").dict()
    {% endif %}

    try:
        response = requests.{{ tool.method.lower() }}(
            base_url,
            params=remaining_args if "{{ tool.method }}" == "GET" else None,
            json=payload if payload else remaining_args,
            headers=headers,
            timeout=15
        )
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
        models=models
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

    mode = st.radio(
        "Tool Creation Mode",
        ["Manual Entry", "Import from OpenAPI / Swagger"],
        horizontal=True
    )

    # -------- Swagger Import with Checkboxes --------
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

            with st.container():
                for t in st.session_state.all_swagger_tools:
                    label = f"**{t['method']}** `{t['url']}` — {t['desc']}"
                    st.session_state.swagger_selection[t["name"]] = st.checkbox(
                        label,
                        value=st.session_state.swagger_selection.get(t["name"], False),
                        key=f"cb_{t['name']}"
                    )

            if st.button("⚙️ Generate Selected Tools", key="generate_tools_selected"):
                selected_tools = [
                    t for t in st.session_state.all_swagger_tools
                    if st.session_state.swagger_selection.get(t["name"], False)
                ]
                st.session_state.tools.extend(selected_tools)
                st.success(f"Added {len(selected_tools)} selected tools")

    # -------- Manual Entry --------
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
                st.session_state.tools.append({
                    "name": name,
                    "url": url,
                    "method": method,
                    "auth": auth,
                    "auth_val": auth_val,
                    "args": json.loads(args_raw),
                    "body_model": None,
                    "desc": desc
                })

    # -------- Shared Display for Tools --------
    if st.session_state.tools:
        st.subheader("✅ Current Tools")
        st.table(st.session_state.tools)
        if st.button("Next ➡️", key="next_step1"):
            st.session_state.step = 2
            st.rerun()

# ---------------- STEP 2 ----------------
elif st.session_state.step == 2:
    st.header("2️⃣ Design Prompts")

    with st.form("prompt_form", clear_on_submit=True):
        name = st.text_input("Prompt Name", "summarize")
        args = st.text_input("Arguments", "id")
        text = st.text_area("Prompt Template", "Summarize the result")
        if st.form_submit_button("➕ Add Prompt"):
            st.session_state.prompts.append({
                "name": name,
                "args": args,
                "text": text,
                "desc": "Prompt"
            })

    if st.session_state.prompts:
        st.table(st.session_state.prompts)
        if st.button("Generate Code 🚀", key="generate_code"):
            st.session_state.step = 3
            st.rerun()

# ---------------- STEP 3 ----------------
elif st.session_state.step == 3:
    st.header("3️⃣ Final MCP Server Code")

    filename = f"{st.session_state.api_name.lower()}_server.py"
    code = generate_mcp_code(
        st.session_state.api_name,
        st.session_state.tools,
        st.session_state.prompts,
        st.session_state.models
    )

    st.code(code, language="python")
    st.download_button("💾 Download Python Server", code, filename)

    secrets = list(set(t["auth_val"] for t in st.session_state.tools if t["auth"] != "None"))

    t1, t2, t3, t4 = st.tabs(
        ["Local Execution", "Claude Desktop", "Dockerfile", "Docker Compose"]
    )

    with t1:
        st.code("pip install fastmcp requests pydantic\npython " + filename)

    with t2:
        st.json({
            "mcpServers": {
                st.session_state.api_name.lower(): {
                    "command": "python",
                    "args": [filename],
                    "env": {s: "YOUR_TOKEN" for s in secrets}
                }
            }
        })

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
