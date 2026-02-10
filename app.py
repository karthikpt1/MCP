"""
MCP Forge Pro - Streamlit UI
A Streamlit-based UI for generating Model Context Protocol (MCP) servers
from OpenAPI/Swagger specifications.
"""
import streamlit as st
import json
from parsers import swagger_to_tools
from generators import generate_mcp_code, auto_generate_prompts

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = 0
if "api_name" not in st.session_state:
    st.session_state.api_name = "MyAPI"
if "tools" not in st.session_state:
    st.session_state.tools = []
if "prompts" not in st.session_state:
    st.session_state.prompts = []
if "models" not in st.session_state:
    st.session_state.models = {}
if "swagger_text" not in st.session_state:
    st.session_state.swagger_text = ""
if "swagger_selection" not in st.session_state:
    st.session_state.swagger_selection = {}
if "all_swagger_tools" not in st.session_state:
    st.session_state.all_swagger_tools = []

# Page configuration
st.set_page_config(page_title="MCP Forge Pro", layout="wide", page_icon="⚙️")

# ===== SIDEBAR NAVIGATION =====
with st.sidebar:
    st.title("🛠️ MCP Forge")
    st.markdown("---")
    
    if st.button("🏠 Home", use_container_width=True, key="btn_home", type="secondary"):
        st.session_state.tools = []
        st.session_state.prompts = []
        st.session_state.models = {}
        st.session_state.api_name = "MyAPI"
        st.session_state.swagger_selection = {}
        st.session_state.swagger_text = ""
        st.session_state.step = 0
        st.rerun()
    
    if st.button("⚡ Quick Start", use_container_width=True, key="quickstart", type="primary", disabled=st.session_state.step > 0):
        st.session_state.tools = []
        st.session_state.prompts = []
        st.session_state.models = {}
        st.session_state.api_name = "MyAPI"
        st.session_state.swagger_selection = {}
        st.session_state.swagger_text = ""
        st.session_state.step = 1
        st.rerun()
    
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
    
    st.info("ℹ️ Use the Quick Start button in the sidebar to begin.")

# ============ STEP 1: CONFIGURE TOOLS ============
elif st.session_state.step == 1:
    st.header("1️⃣ Configure API Tools")
    
    st.caption("💡 **Tips:** Keep your server name short (e.g., 'github', 'slack') - it'll be used for file naming and deployment")
    st.session_state.api_name = st.text_input("MCP Server Name", st.session_state.api_name)
    
    st.markdown("---")
    
    mode = st.radio("Tool Creation Mode", ["Import from OpenAPI / Swagger", "Manual Entry"], horizontal=True)

    if mode == "Import from OpenAPI / Swagger":
        if "all_swagger_tools" not in st.session_state or not st.session_state.all_swagger_tools:
            st.session_state.swagger_text = st.text_area("Paste OpenAPI / Swagger", height=300, value=st.session_state.swagger_text)
            
            if st.button("📥 Load APIs", key="load_swagger", type="primary", disabled=not st.session_state.swagger_text.strip()):
                try:
                    tools, models = swagger_to_tools(st.session_state.swagger_text)
                    if not tools:
                        st.warning("⚠️ No API endpoints found in the Swagger/OpenAPI spec. Please check the file and make sure it contains valid paths.")
                    else:
                        st.session_state.all_swagger_tools = tools
                        st.session_state.models.update(models)
                        st.session_state.swagger_selection = {t["name"]: False for t in tools}
                        st.session_state.swagger_text = ""
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
                st.session_state.tools.append({"name": name, "url": url, "method": method, "auth": auth, "auth_val": auth_val, "args": json.loads(args_raw), "body_model": None, "response_model": None, "desc": desc})

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

# ============ STEP 2: DESIGN PROMPTS ============
elif st.session_state.step == 2:
    st.header("2️⃣ Design Prompts")

    st.info("💡 Choose your LLM provider for prompt generation. Groq is free and fast!")
    
    col1, col2, col3 = st.columns([1.5, 1.5, 1])
    with col1:
        provider = st.selectbox("LLM Provider", ["openai", "groq"], format_func=lambda x: "🤖 OpenAI" if x == "openai" else "⚡ Groq")
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
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", key="back_step2", use_container_width=True, type="secondary"):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("Generate Code 🚀", key="generate_code", use_container_width=True, type="primary"):
            st.session_state.step = 3
            st.rerun()

# ============ STEP 3: GENERATE CODE ============
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
        if st.button("← Reconfigure Prompts", use_container_width=True, key="back_to_prompts", type="secondary"):
            st.session_state.step = 2
            st.rerun()
    
    with col3:
        if st.button("🏠 Start Over", use_container_width=True, key="start_over", type="secondary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.step = 0
            st.rerun()
