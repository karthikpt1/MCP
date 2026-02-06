# 🛠️ MCP Forge Pro

A powerful Streamlit-based UI for generating production-ready **Model Context Protocol (MCP) servers** from REST API specifications.

Convert your OpenAPI/Swagger specs into fully functional MCP servers in just 3 steps, with built-in HTTP resilience, authentication handling, and multiple deployment options.

---

## ✨ Key Features

- **🔗 Full API Parsing** — Automatically extracts endpoints, parameters, and request bodies from OpenAPI 3.0 & Swagger 2.0 specs
- **🛡️ HTTP Resilience** — Built-in retry logic with exponential backoff for reliable API calls
- **🔐 Auth Support** — Handles Bearer Token, API Key, and custom authentication automatically
- **📦 Pydantic Models** — Generates type-safe request/response models for all API parameters
- **⚙️ FastMCP Integration** — Wraps APIs as MCP tools—ready to use with Claude and other AI models
- **🚀 Multiple Deployments** — Local execution, Docker containers, Docker Compose, and Claude Desktop configs
- **🤖 Prompt Templates** — Auto-generate or customize prompt templates for each API tool
- **📥 One-Click Download** — Export complete server code and deployment configs in seconds

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip or conda
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/MCP.git
   cd MCP
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   streamlit run app.py
   ```

5. **Open in browser**
   - Local: `http://localhost:8501`
   - Network: Check terminal output for network URL

### Your First MCP Server

1. **Step 1: Import API** — Paste your OpenAPI/Swagger spec
2. **Step 2: Design Prompts** — Auto-generate or write custom prompts
3. **Step 3: Download** — Get your MCP server code ready to deploy

---

## 📝 License

MIT License — see LICENSE file for details.

---

**Built with ❤️ using Streamlit, FastMCP, and Pydantic**
