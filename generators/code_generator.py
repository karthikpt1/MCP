"""
Code generation module for MCP servers.
Generates FastMCP Python server code from tool and prompt definitions.
"""

import requests
from jinja2 import Template


def _create_session_with_retries():
    """
    Create a requests Session with exponential backoff retry strategy.
    Retries on connection errors and specified HTTP status codes.
    """
    session = requests.Session()
    from urllib3.util.retry import Retry
    from requests.adapters import HTTPAdapter
    
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
    """
    Extract path parameters from URL template and substitute them.
    Returns tuple of (final_url, remaining_args).
    Path params like {id} are replaced with values from args dict.
    """
    import re
    remaining = args.copy()
    path_params = re.findall(r"{(.*?)}", base_url)
    for param in path_params:
        if param in remaining:
            base_url = base_url.replace("{" + param + "}", str(remaining.pop(param)))
    return base_url, remaining


def _get_model_aliases(tools):
    """
    Identify tools that share the same model and generate alias assignments.
    Returns dict mapping tool to (canonical_model, alias_name) tuple.
    
    Example:
        CreateUserRequest and UpdateUserRequest both reference User model
        Returns aliases for both pointing to the canonical User class
    """
    model_usage = {}  # model_name -> [tool_names]
    aliases = {}  # tool_name -> (canonical_model, alias_for_tool)
    
    # Count which models are used by which tools
    for tool in tools:
        body_model = tool.get("body_model")
        response_model = tool.get("response_model")
        
        if body_model:
            if body_model not in model_usage:
                model_usage[body_model] = []
            model_usage[body_model].append((tool["name"], "request"))
        
        if response_model:
            if response_model not in model_usage:
                model_usage[response_model] = []
            model_usage[response_model].append((tool["name"], "response"))
    
    # Generate aliases for models used by multiple tools
    for model_name, usages in model_usage.items():
        if len(usages) > 1:
            # Multiple tools use this model - create aliases
            for tool_name, usage_type in usages:
                alias_name = f"{tool_name.title().replace('_','')}{'Request' if usage_type == 'request' else 'Response'}"
                aliases[alias_name] = model_name
    
    return aliases


def _to_dict(obj):
    """
    Convert Pydantic model or dict to plain dictionary.
    Handles both Pydantic models (with .dict() method) and regular dicts.
    """
    if hasattr(obj, 'dict') and callable(obj.dict):
        return obj.dict()
    elif isinstance(obj, dict):
        return obj
    return obj


def generate_rest_mcp_code(api_name, tools, prompts, models):
    """
    Generate FastMCP server code for REST APIs only.
    
    Args:
        api_name (str): Name of the MCP server
        tools (list): List of REST tool definitions
        prompts (list): List of prompt templates
        models (dict): Dictionary of Pydantic model definitions
    
    Returns:
        str: Complete Python source code for FastMCP REST server
    """
    used_models = {}
    for tool in tools:
        # Include request models
        if tool.get("body_model"):
            model_name = tool["body_model"]
            if model_name in models:
                used_models[model_name] = models[model_name]
        # Include response models for typed responses
        if tool.get("response_model"):
            model_name = tool["response_model"]
            if model_name in models:
                used_models[model_name] = models[model_name]
    
    # Get model aliases for deduplication
    model_aliases = _get_model_aliases(tools)
    
    template_str = """from mcp.server.fastmcp import FastMCP
import requests
import re
import os
from pydantic import BaseModel, ValidationError
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ------------------ Pydantic Models ------------------
{% for model, fields in models.items() %}
class {{ model }}(BaseModel):
    \"\"\"Pydantic model for {{ model }}\"\"\"
{% if fields %}
{% for name, type in fields.items() %}
    {{ name }}: {{ type }}
{% endfor %}
{% else %}
    pass
{% endif %}

{% endfor %}
# --------- Model Aliases (Reuse canonical models) ---------
{% for alias_name, canonical_model in aliases.items() %}
{{ alias_name }} = {{ canonical_model }}
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

    {% if tool.body_model %}
    payload = remaining_args.pop("body", None)
    {% endif %}

    try:
        request_kwargs = {
            "headers": headers,
            "timeout": 15
        }
        
        {% if tool.has_query_params %}
        if remaining_args:
            request_kwargs["params"] = remaining_args
        {% endif %}
        
        {% if tool.body_model %}
        if payload is not None:
            payload_dict = _to_dict(payload)
            {% if tool.has_file_fields %}
            request_kwargs["files"] = payload_dict
            {% else %}
            request_kwargs["json"] = payload_dict
            {% endif %}
        {% endif %}
        
        response = _session.{{ tool.method.lower() }}(base_url, **request_kwargs)
        response.raise_for_status()
        
        # Handle empty response (204 No Content is valid for some endpoints)
        if response.status_code == 204 or not response.text or response.text.strip() == "":
            return {"ok": True, "data": None, "message": "No content"}
        
        # Check content-type before parsing JSON
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            return {
                "ok": False,
                "error": {
                    "type": "INVALID_CONTENT_TYPE",
                    "details": f"Expected JSON but got: {content_type}",
                    "response_text": response.text[:500]
                }
            }
        
        try:
            response_data = response.json()
        except ValueError as json_error:
            return {
                "ok": False,
                "error": {
                    "type": "JSON_PARSE_ERROR",
                    "details": str(json_error),
                    "response_text": response.text[:500]
                }
            }
        
        # Validate and structure response with Pydantic model
        {% if tool.response_model %}
        try:
            # Ensure response_data is a dict
            if not isinstance(response_data, dict):
                return {
                    "ok": False,
                    "error": {
                        "type": "VALIDATION_ERROR",
                        "details": "Response data must be a JSON object",
                        "actual_type": type(response_data).__name__
                    }
                }
            
            validated_response = {{ tool.response_model }}(**response_data)
            return {"ok": True, "data": validated_response.model_dump()}
        except ValidationError as ve:
            # Validation failed - return structured error
            return {
                "ok": False,
                "error": {
                    "type": "VALIDATION_ERROR",
                    "details": str(ve),
                    "response_data": response_data
                }
            }
        except TypeError as te:
            return {
                "ok": False,
                "error": {
                    "type": "MODEL_INSTANTIATION_ERROR",
                    "details": str(te),
                    "response_data": response_data
                }
            }
        {% else %}
        # No response model - validate that response is a dict
        if not isinstance(response_data, dict):
            return {
                "ok": False,
                "error": {
                    "type": "VALIDATION_ERROR",
                    "details": "Response data must be a JSON object",
                    "actual_type": type(response_data).__name__
                }
            }
        return {"ok": True, "data": response_data}
        {% endif %}
    except Exception as e:
        if hasattr(e, 'response') and e.response is not None:
            return {
                "ok": False,
                "error": {
                    "type": "HTTP_ERROR",
                    "details": {
                        "status_code": e.response.status_code,
                        "body": e.response.text[:500]
                    }
                }
            }
        else:
            return {
                "ok": False,
                "error": {
                    "type": "EXCEPTION",
                    "details": str(e),
                    "url_attempted": base_url
                }
            }

{% endfor %}
# --------- MCP Prompts ---------
{% for prompt in prompts %}
@mcp.prompt()
def {{ prompt.name }}_prompt():
    \"\"\"{{ prompt.desc }}\"\"\"
    return {
        "name": "{{ prompt.name }}",
        "arguments": [{% if prompt.args %}{{ prompt.args.split(',')|map('trim')|map('tojson')|join(', ') }}{% endif %}],
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
        models=used_models,
        aliases=model_aliases
    )




def generate_mcp_code(api_name, tools, prompts, models):
    """
    Generate FastMCP server code for REST APIs only.
    
    Args:
        api_name (str): Name of the MCP server
        tools (list): List of REST tool definitions
        prompts (list): List of prompt templates
        models (dict): Dictionary of Pydantic model definitions
    
    Returns:
        str: Complete Python source code for FastMCP REST server
    """
    if not tools:
        return ""
    
    return generate_rest_mcp_code(api_name, tools, prompts, models)
