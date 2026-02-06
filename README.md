# 🛠️ MCP Forge Pro

A powerful Streamlit-based UI for generating production-ready **Model Context Protocol (MCP) servers** from REST API specifications.

Convert your OpenAPI/Swagger specs into fully functional MCP servers in just 3 steps, with built-in HTTP resilience, authentication handling, and multiple deployment options.

---

## ✨ Key Features

- **🔗 Full API Parsing** — Automatically extracts endpoints, parameters, and request bodies from OpenAPI 3.0 & Swagger 2.0 specs
- **🛡️ HTTP Resilience** — Built-in retry logic with exponential backoff (3 retries, 0.5s backoff factor) for reliable API calls
- **🔐 Auth Support** — Handles Bearer Token, API Key (header), and custom authentication automatically
- **📦 Pydantic Models** — Generates type-safe request/response models for all API parameters
- **⚙️ FastMCP Integration** — Wraps APIs as MCP tools—ready to use with Claude and other AI models
- **🚀 Multiple Deployments** — Local execution, Docker containers, Docker Compose, and Claude Desktop configs
- **🤖 Prompt Templates** — Auto-generate or customize prompt templates for each API tool
- **📥 One-Click Download** — Export complete server code and deployment configs in seconds
- **💾 Memory Optimized** — Efficient session state management for handling large API specifications

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

---

## 📋 How to Use

### Step 1: Import API Specification
- **Paste OpenAPI/Swagger** — Copy your OpenAPI 3.0 or Swagger 2.0 spec (JSON or YAML)
- **Or Import from WSDL** — SOAP/WSDL support (in progress)
- **Or Manual Entry** — Add endpoints one by one with full configuration

### Step 2: Design Prompts
- **Auto-Generate** — Use GPT-4 to generate prompt templates for your tools
- **Or Customize** — Write your own prompt templates with custom arguments

### Step 3: Generate & Deploy
- **Download Python Server** — FastMCP server code ready to run
- **Claude Desktop Config** — JSON config for `claude_desktop_config.json`
- **Docker** — Complete Dockerfile for containerization
- **Docker Compose** — Multi-service setup with environment variables

---

## 🏗️ Architecture

### Core Components

**app.py** — Single-file Streamlit application (791 lines)
- Schema parsing (OpenAPI 3.0 & Swagger 2.0)
- Session state management
- Multi-step wizard UI
- Jinja2-based code generation

**requirements.txt** — Project dependencies
- `streamlit` — UI framework
- `fastmcp` — MCP server framework
- `pydantic` — Type validation
- `requests` — HTTP client with retry strategy
- `jinja2` — Template engine
- `openai` — GPT-4 for prompt generation
- `pyyaml` — YAML spec support

### Key Functions

- **swagger_to_tools()** — Parses OpenAPI/Swagger specs with $ref resolution
- **_normalize_type()** — Converts OpenAPI types to Python annotations
- **_map_schema_to_type()** — Handles complex type mapping including arrays and objects
- **_extract_schema_fields()** — Extracts Pydantic field definitions from schemas
- **generate_mcp_code()** — Renders Jinja2 template with tool and prompt functions
- **auto_generate_prompts()** — Uses GPT-4 to generate prompt templates

### Generated Code Structure

The generated MCP server includes:
- Pydantic models for request validation
- HTTP session with urllib3 retry strategy
- FastMCP server initialization
- Tool decorators for each API endpoint
- Error handling with structured responses
- Authentication header injection

---

## 🔧 Configuration

### Environment Variables

Required environment variables depend on your API's authentication:

```bash
# Example for GitHub API
export GITHUB_TOKEN="your_token_here"

# Example for generic API Key
export API_KEY="your_key_here"
```

### Session State Variables

The app maintains these in `st.session_state`:
- `tools` — Selected API endpoints
- `prompts` — Prompt templates
- `models` — Pydantic model definitions
- `api_name` — MCP server name
- `step` — Current UI step (0-3)
- `swagger_text` — API spec input (cleared after load)
- `wsdl_text` — WSDL spec input (cleared after load)

---

## 🚢 Deployment

### Local Execution

```bash
pip install fastmcp requests pydantic
python myapi_server.py
```

### Docker

```bash
docker build -t myapi-mcp .
docker run -e API_KEY=your_key myapi-mcp
```

### Docker Compose

```bash
docker-compose up
```

Set environment variables in `.env` file:
```
GITHUB_TOKEN=your_token
API_KEY=your_key
```

### Claude Desktop

Copy the generated JSON config to:
- **macOS/Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

---

## 📊 Supported API Specifications

### OpenAPI 3.0
- Full specification support
- Complex schema resolution with `$ref`
- Request body extraction
- Query and path parameters

### Swagger 2.0
- Complete compatibility
- Schema definitions
- Security schemes (Bearer Token, API Key)
- Parameter handling

### WSDL (Coming Soon)
- SOAP service definitions
- Port type extraction
- Message binding support

---

## 🔄 HTTP Resilience

Generated servers include automatic retry logic:

```
✓ Total retries: 3
✓ Backoff factor: 0.5s (exponential)
✓ Retry status codes: 429, 500, 502, 503, 504
✓ Timeout per request: 15 seconds
✓ Connection pooling: Enabled
```

---

## 🧪 Testing

### Test with Petstore API

```bash
# Paste this into the app:
# https://petstore.swagger.io/v2/swagger.json

# Or use FakeRESTApi:
# https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json
```

### Validate Generated Code

The app validates:
- JSON/YAML parsing
- API endpoint extraction
- Pydantic model generation
- Code syntax and imports
- Download file generation

---

## 🐛 Known Limitations

- **WSDL Support** — Partially implemented; functions exist but need completion
- **Nested Models** — Complex nested objects flatten to `dict` type (enhancement in progress)
- **Content Types** — Assumes `application/json`; multipart/form-data support coming soon
- **Prompt Generation** — Requires OpenAI API key for auto-generation feature

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

1. **WSDL Parser** — Complete implementation of `wsdl_to_tools()` function
2. **Nested Models** — Support for recursive Pydantic model generation
3. **Content Type Support** — Multipart/form-data and URL-encoded handling
4. **Additional Auth Methods** — OAuth2, mTLS, custom headers
5. **UI Enhancements** — Preview generated code, spec validation UI
6. **Testing** — Unit tests for parsing functions, integration tests

### Getting Started with Development

```bash
# Create a feature branch
git checkout -b feature/your-feature

# Make changes
# Commit with clear messages
git add .
git commit -m "Add feature: description"

# Push and create a Pull Request
git push origin feature/your-feature
```

---

## 📝 License

This project is licensed under the MIT License — see LICENSE file for details.

---

## 📞 Support

### Troubleshooting

**Button is disabled** — Paste valid API spec text in the textarea

**Invalid specification error** — Check JSON/YAML syntax; use validator tools

**No endpoints found** — Verify `paths` field exists in OpenAPI/Swagger spec

**Memory issues with large specs** — Swagger text is auto-cleared after loading; system clears on Reset

### Contact

For issues, questions, or feature requests, open a GitHub issue or contact the maintainers.

---

## 🎯 Roadmap

- [ ] Complete WSDL/SOAP support
- [ ] Nested Pydantic model generation
- [ ] GraphQL schema support
- [ ] Real-time API spec validation UI
- [ ] Generated code preview before download
- [ ] Custom authentication method definitions
- [ ] Batch import multiple APIs
- [ ] Prompt template management UI
- [ ] Advanced HTTP client options (custom headers, timeouts)
- [ ] Analytics and usage tracking

---

**Built with ❤️ using Streamlit, FastMCP, and Pydantic**
