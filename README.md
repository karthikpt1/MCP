# 🛠️ MCP Forge Pro

A powerful Streamlit-based UI for generating production-ready **Model Context Protocol (MCP) servers** from REST APIs.

Convert your OpenAPI/Swagger specifications into fully functional MCP servers in just 3 steps, with built-in HTTP resilience, comprehensive error handling, authentication support, and multiple deployment options.

---

## ✨ Key Features

- **🔗 Full API Parsing** — Automatically extracts endpoints, parameters, and request/response schemas from OpenAPI 3.0 & Swagger 2.0 specs
- **🛡️ HTTP Resilience** — Built-in retry logic with exponential backoff, automatic retry on failures (429, 5xx errors)
- **✅ Data Validation** — Content-type checking, JSON parsing verification, and Pydantic model validation
- **🔐 Auth Support** — Handles Bearer Token and API Key authentication with environment variable management
- **📦 Pydantic Models** — Generates type-safe request/response models for all API parameters
- **⚙️ FastMCP Integration** — Wraps APIs as MCP tools—ready to use with Claude and other AI models
- **🚀 Multiple Deployments** — Local execution, Docker containers, Docker Compose, and Claude Desktop configs
- **🤖 Prompt Templates** — Auto-generate with LLM or customize prompt templates for each API tool
- **📥 One-Click Download** — Export complete server code and deployment configurations instantly

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

### Your First MCP Server (3 Easy Steps)

1. **Step 1: Configure Tools** — Import OpenAPI/Swagger spec or manually define REST endpoints
2. **Step 2: Design Prompts** — Auto-generate with AI or write custom prompt templates
3. **Step 3: Generate Code** — Download production-ready MCP server and deployment files

---

## 📚 Supported API Specifications

### REST APIs
- **OpenAPI 3.0** — Full support: parameters, request bodies, response schemas, authentication
- **Swagger 2.0** — Complete Swagger 2.0 specification support with automatic model extraction
- **Authentication** — Bearer Token, API Key (Header), and environment variable management
- **Complex Types** — Nested objects, arrays, and Pydantic model auto-generation

## 🏗️ Generated Server Features

- **Session Management** — Connection pooling with automatic retry strategy
- **Error Handling** — Structured error responses with specific error types
- **Content Validation** — Content-type verification and JSON parsing checks
- **Status Code Handling** — Proper handling of 204 No Content and other edge cases
- **Environment Config** — Easy configuration via environment variables for secrets
- **Model Deduplication** — Automatic detection and reuse of shared Pydantic models

---

## 📝 License

MIT License — see LICENSE file for details.

---

**Built with ❤️ using Streamlit, FastMCP, and Pydantic**
