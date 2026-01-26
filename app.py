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
    # We use a copy to avoid sending path params in the body/query again
    remaining_args = args_dict.copy()
    
    path_params = re.findall(r"\{(.*?)\}", base_url)
    for param in path_params:
        if param in remaining_args:
            base_url = base_url.replace(f"{{ '{' }}{param}{{ '}' }}", str(remaining_args.pop(param)))

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
st.set_page_config(page_title="MCP Forge Pro", layout="wide")

# Sidebar for Global Settings
with st.sidebar:
    st.title("🛠️ MCP Forge")
    st.session_state.api_name = st.text_input("Server Name", st.session_state.api_name)
    st.markdown("---")
    if st.button("Reset Entire Project", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- STEP 1: TOOLS & PATH PARAMS ---
if st.session_state.step == 1:
    st.header("1️⃣ Configure API Tools & Path Params")
    st.info("💡 Tip: Use `{param_name}` in the URL for dynamic paths (e.g., `/user/{id}`). Make sure `id` is also in the Arguments JSON.")
    
    with st.form("tool_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Tool Name (Python function name)", "get_repo_details")
            url = st.text_input("Full URL", "https://api.github.com/repos/{owner}/{repo}")
            method = st.selectbox("HTTP Method", ["GET", "POST", "PUT", "DELETE"])
        with col2:
            auth = st.selectbox("Auth Mechanism", ["None", "Bearer Token", "API Key (Header)"])
            auth_val = st.text_input("Env Var Name (for the secret)", "GITHUB_TOKEN")
            args_raw = st.text_area("Arguments JSON (Key: Type)", '{"owner": "str", "repo": "str"}')
        
        desc = st.text_area("Tool Description (Visible to LLM)", "Fetches metadata for a specific GitHub repository.")
        
        if st.form_submit_button("➕ Add Tool"):
            try:
                st.session_state.tools.append({
                    "name": name, "url": url, "method": method, 
                    "auth": auth, "auth_val": auth_val, 
                    "args": json.loads(args_raw), "desc": desc
                })
                st.success(f"Tool '{name}' added successfully!")
            except Exception as e:
                st.error(f"Error parsing JSON Arguments: {e}")
    
    if st.session_state.tools:
        st.subheader("Current Tools")
        st.table(st.session_state.tools)
        if st.button("Next: Design Chained Prompts ➡️"):
            st.session_state.step = 2
            st.rerun()

# --- STEP 2: PROMPTS (CHAINING) ---
elif st.session_state.step == 2:
    st.header("2️⃣ Design Chained Prompts")
    st.info("Direct the LLM on how to use your tools. Chaining happens when your prompt template mentions tool names.")
    
    with st.form("prompt_form", clear_on_submit=True):
        p_name = st.text_input("Prompt Name", "summarize_repo")
        p_args = st.text_input("Prompt Arguments (e.g., owner, repo)", "owner, repo")
        
        # Chaining helper text
        tool_list = ", ".join([t['name'] for t in st.session_state.tools])
        st.caption(f"Available tools: {tool_list}")
        
        p_text = st.text_area("Prompt Instruction Template", "Use the get_repo_details tool for {owner}/{repo} and summarize the star count and description.")
        p_desc = st.text_input("Short Description", "Summarizes a GitHub repo's health.")
        
        if st.form_submit_button("➕ Add Prompt"):
            st.session_state.prompts.append({"name": p_name, "args": p_args, "text": p_text, "desc": p_desc})
            st.success("Prompt added!")

    if st.session_state.prompts:
        st.subheader("Current Prompts")
        st.table(st.session_state.prompts)
        col_prev, col_next = st.columns([1, 1])
        if col_prev.button("⬅️ Back"):
            st.session_state.step = 1
            st.rerun()
        if col_next.button("Generate Final Server Code 🚀"):
            st.session_state.step = 3
            st.rerun()

# --- STEP 3: FINAL CODE & DEPLOYMENT ---
elif st.session_state.step == 3:
    st.header("3️⃣ Final MCP Server Code")
    full_code = generate_mcp_code(st.session_state.api_name, st.session_state.tools, st.session_state.prompts)
    
    st.code(full_code, language="python")
    
    st.download_button(
        label=f"💾 Download {st.session_state.api_name}.py",
        data=full_code,
        file_name=f"{st.session_state.api_name.lower()}_server.py",
        mime="text/x-python"
    )
    
    st.markdown("---")
    st.subheader("🚀 Deployment Instructions")
    
    tab1, tab2, tab3 = st.tabs(["Local (FastMCP)", "Docker", "Claude Desktop"])
    
    with tab1:
        st.markdown("Run this in your terminal to start the server immediately:")
        st.code(f"pip install fastmcp requests\nfastmcp run {st.session_state.api_name.lower()}_server.py")
        
    with tab2:
        docker_code = f"""FROM python:3.11-slim
RUN pip install fastmcp requests
COPY {st.session_state.api_name.lower()}_server.py .
CMD ["python", "{st.session_state.api_name.lower()}_server.py"]"""
        st.code(docker_code, language="dockerfile")
        
    with tab3:
        st.write("Add this to your `claude_desktop_config.json`:")
        config_json = {
            "mcpServers": {
                st.session_state.api_name.lower(): {
                    "command": "python",
                    "args": [os.path.abspath(f"{st.session_state.api_name.lower()}_server.py")]
                }
            }
        }
        st.json(config_json)