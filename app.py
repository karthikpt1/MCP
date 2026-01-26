import streamlit as st
import json
import os  
import re  
from jinja2 import Template

# --- SESSION STATE INITIALIZATION ---
if 'tools' not in st.session_state:
    st.session_state.tools = []
if 'prompts' not in st.session_state:
    st.session_state.prompts = []
if 'api_name' not in st.session_state:
    st.session_state.api_name = "MyAPI"
if 'step' not in st.session_state:
    st.session_state.step = 1

# --- JINJA2 GENERATOR ENGINE ---
def generate_mcp_code(api_name, tools, prompts):
    template_str = """from mcp.server.fastmcp import FastMCP
import requests
import os
import re

# Initialize FastMCP Server: {{ api_name }}
mcp = FastMCP("{{ api_name }}")

{% for tool in tools %}
@mcp.tool()
def {{ tool.name }}({% for arg, type in tool.args.items() %}{{ arg }}: {{ type }}{% if not loop.last %}, {% endif %}{% endfor %}):
    \"\"\"{{ tool.desc }}\"\"\"
    # 1. Collect arguments
    args_dict = { {% for arg in tool.args.keys() %}"{{ arg }}": {{ arg }}{% if not loop.last %}, {% endif %}{% endfor %} }
    
    # 2. Handle Path Parameters (e.g., /users/{id})
    base_url = "{{ tool.url }}"
    remaining_args = args_dict.copy()
    
    path_params = re.findall(r"{(.*?)}", base_url)
    for param in path_params:
        if param in remaining_args:
            placeholder = "{" + param + "}"
            base_url = base_url.replace(placeholder, str(remaining_args.pop(param)))

    # 3. Setup Auth
    headers = {}
    {% if tool.auth == 'Bearer Token' %}
    headers["Authorization"] = f"Bearer {os.environ.get('{{ tool.auth_val }}', 'YOUR_TOKEN_HERE')}"
    {% elif tool.auth == 'API Key (Header)' %}
    headers["X-API-KEY"] = os.environ.get('{{ tool.auth_val }}', 'YOUR_KEY_HERE')
    {% endif %}

    # 4. Execute Request
    try:
        response = requests.{{ tool.method.lower() }}(
            base_url, 
            {% if tool.method == 'GET' %}params=remaining_args{% else %}json=remaining_args{% endif %},
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
    return Template(template_str).render(api_name=api_name, tools=tools, prompts=prompts)

# --- STREAMLIT UI ---
st.set_page_config(page_title="MCP Forge Pro", layout="wide", page_icon="⚙️")

with st.sidebar:
    st.title("🛠️ MCP Forge")
    st.session_state.api_name = st.text_input("Server Name", st.session_state.api_name)
    st.markdown("---")
    if st.button("Reset Entire Project", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- STEP 1: TOOLS ---
if st.session_state.step == 1:
    st.header("1️⃣ Configure API Tools & Path Params")
    with st.form("tool_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Tool Name", "get_repo")
            url = st.text_input("Full URL", "https://api.github.com/repos/{owner}/{repo}")
            method = st.selectbox("HTTP Method", ["GET", "POST", "PUT", "DELETE"])
        with col2:
            auth = st.selectbox("Auth Mechanism", ["None", "Bearer Token", "API Key (Header)"])
            auth_val = st.text_input("Env Var Name", "GITHUB_TOKEN")
            args_raw = st.text_area("Arguments JSON", '{"owner": "str", "repo": "str"}')
        desc = st.text_area("Tool Description", "Fetches metadata for a specific GitHub repository.")
        if st.form_submit_button("➕ Add Tool"):
            try:
                st.session_state.tools.append({"name": name, "url": url, "method": method, "auth": auth, "auth_val": auth_val, "args": json.loads(args_raw), "desc": desc})
                st.success(f"Tool '{name}' added!")
            except Exception as e: st.error(f"Error: {e}")
    if st.session_state.tools:
        st.table(st.session_state.tools)
        if st.button("Next: Design Prompts ➡️"):
            st.session_state.step = 2
            st.rerun()

# --- STEP 2: PROMPTS ---
elif st.session_state.step == 2:
    st.header("2️⃣ Design Chained Prompts")
    with st.form("prompt_form", clear_on_submit=True):
        p_name = st.text_input("Prompt Name", "summarize_repo")
        p_args = st.text_input("Arguments", "owner, repo")
        p_text = st.text_area("Template", "Use the tool for {owner}/{repo} and summarize it.")
        if st.form_submit_button("➕ Add Prompt"):
            st.session_state.prompts.append({"name": p_name, "args": p_args, "text": p_text, "desc": "Prompt desc"})
    if st.session_state.prompts:
        st.table(st.session_state.prompts)
        c_back, c_next = st.columns(2)
        if c_back.button("⬅️ Back"):
            st.session_state.step = 1
            st.rerun()
        if c_next.button("Generate Code 🚀"):
            st.session_state.step = 3
            st.rerun()

# --- STEP 3: FINAL CODE & DYNAMIC DEPLOYMENT ---
elif st.session_state.step == 3:
    st.header("3️⃣ Final MCP Server Code")
    filename = f"{st.session_state.api_name.lower()}_server.py"
    full_code = generate_mcp_code(st.session_state.api_name, st.session_state.tools, st.session_state.prompts)
    
    st.code(full_code, language="python")
    st.download_button(label=f"💾 Download {filename}", data=full_code, file_name=filename)
    
    st.markdown("---")
    st.subheader("🚀 Deployment Instructions")
    
    required_secrets = list(set([t['auth_val'] for t in st.session_state.tools if t['auth'] != 'None']))
    
    t1, t2, t3, t4 = st.tabs(["Local Execution", "Claude Desktop Config", "Dockerfile", "Docker Compose"])
    
    with t1:
        st.write("### Run via Terminal")
        if required_secrets:
            st.info("Set your environment variables first:")
            for secret in required_secrets:
                st.code(f"export {secret}='your_key'  # Mac/Linux\nset {secret}=your_key     # Windows", language="bash")
        st.code(f"pip install fastmcp requests\nfastmcp run {filename}")
        
    with t2:
        st.write("### Claude Desktop Config")
        env_config = {secret: "YOUR_ACTUAL_TOKEN_HERE" for secret in required_secrets}
        config = {
            "mcpServers": {
                st.session_state.api_name.lower(): {
                    "command": "python",
                    "args": [os.path.abspath(filename)],
                    "env": env_config
                }
            }
        }
        st.json(config)
        
    with t3:
        st.write("### Dockerfile")
        dockerfile_content = f"""FROM python:3.11-slim\nWORKDIR /app\nRUN pip install --no-cache-dir fastmcp requests\nCOPY {filename} .\nCMD ["python", "{filename}"]"""
        st.code(dockerfile_content, language="dockerfile")
        st.download_button("💾 Download Dockerfile", dockerfile_content, "Dockerfile")
        st.markdown("**Build & Run Commands:**")
        st.code(f"docker build -t {st.session_state.api_name.lower()}-mcp .\ndocker run -i --rm {' '.join([f'-e {s}=your_key' for s in required_secrets])} {st.session_state.api_name.lower()}-mcp")

    with t4:
        st.write("### Docker Compose")
        st.info("Docker Compose is best for managing multiple environment variables easily.")
        
        # Generate YAML
        compose_content = f"""version: '3.8'
services:
  {st.session_state.api_name.lower()}-mcp:
    build: .
    image: {st.session_state.api_name.lower()}-mcp
    stdin_open: true # Equivalent to -i
    tty: true        # Equivalent to -t
    environment:
"""
        for secret in required_secrets:
            compose_content += f"      - {secret}=${{{secret}}}\n"
        
        st.code(compose_content, language="yaml")
        st.download_button("💾 Download docker-compose.yml", compose_content, "docker-compose.yml")
        
        st.markdown("**How to use:**")
        st.write("1. Put the `Dockerfile`, `docker-compose.yml`, and your Python script in the same folder.")
        st.write("2. Create a `.env` file in that folder and add your keys:")
        st.code("\n".join([f"{s}=your_actual_key_here" for s in required_secrets]), language="text")
        st.write("3. Run the command:")
        st.code("docker-compose up")