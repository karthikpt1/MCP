"""
OpenAPI 3.0 and Swagger 2.0 parser for REST APIs.
Extracts endpoints, parameters, authentication, and generates Pydantic models.
"""

import json
import yaml
from collections import OrderedDict
import hashlib


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


def _normalize_schema_for_comparison(fields):
    """
    Normalize schema fields to a canonical form for comparison.
    Returns a hash of the sorted field definitions.
    This allows identifying identical schemas regardless of naming.
    """
    if not fields:
        return None
    
    # Create a sorted representation of fields
    sorted_items = sorted(fields.items())
    canonical = json.dumps(sorted_items, sort_keys=True)
    return hashlib.md5(canonical.encode()).hexdigest()


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


def _extract_response_schema(responses, spec, is_openapi):
    """
    Extract response schema from OpenAPI/Swagger responses object.
    Returns the 200/OK response schema, or first successful response.
    
    Args:
        responses (dict): The responses object from path item
        spec (dict): Full OpenAPI/Swagger spec for resolving refs
        is_openapi (bool): True for OpenAPI 3.0, False for Swagger 2.0
    
    Returns:
        dict: Schema for successful response, or empty dict if not found
    """
    if not responses:
        return {}
    
    # Try 200 response first, then 201, then any 2xx
    for status_code in ['200', '201', '202', '204']:
        if status_code in responses:
            response_obj = responses[status_code]
            if is_openapi:
                # OpenAPI 3.0: responses[status].content.application/json.schema
                content = response_obj.get('content', {})
                if 'application/json' in content:
                    return content['application/json'].get('schema', {})
                # Fallback to any content type
                for content_type, content_obj in content.items():
                    return content_obj.get('schema', {})
            else:
                # Swagger 2.0: responses[status].schema
                return response_obj.get('schema', {})
    
    # If no 2xx found, return empty dict
    return {}


def swagger_to_tools(swagger_text):
    """
    Parse OpenAPI 3.0 or Swagger 2.0 specification and extract API endpoints as tools.
    
    Returns:
        tuple: (tools_list, models_dict) where tools_list contains API endpoint definitions
               and models_dict contains Pydantic model definitions
    
    Raises:
        ValueError: If required fields are missing or spec is invalid
    """
    try:
        spec = json.loads(swagger_text)
    except json.JSONDecodeError:
        spec = yaml.safe_load(swagger_text)
    
    if spec is None:
        return [], {}

    tools = []
    models = {}
    model_hash_map = {}  # Track: hash -> canonical model name
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
        
        # Validation: Check for required fields
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
            has_query_params = False

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
                    
                    # Track if we have query parameters (needed for generated code)
                    if p_in == "query":
                        has_query_params = True
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
                    # Normalize all field types to valid Python types
                    normalized_fields = {}
                    for field_name, field_type in body_fields.items():
                        normalized_fields[field_name] = _normalize_type(field_type) if isinstance(field_type, str) else field_type
                    
                    # Check if this schema already exists (deduplication)
                    schema_hash = _normalize_schema_for_comparison(normalized_fields)
                    if schema_hash in model_hash_map:
                        # Reuse existing model
                        body_model = model_hash_map[schema_hash]
                    else:
                        # Create new canonical model with resource-based name
                        # Extract resource name from tool name (e.g., "get_user" -> "User")
                        resource_name = tool_name.split('_')[-1].title() if '_' in tool_name else tool_name.title()
                        model_name = resource_name
                        
                        # Ensure unique name if collision
                        counter = 1
                        while model_name in models:
                            model_name = f"{resource_name}{counter}"
                            counter += 1
                        
                        models[model_name] = normalized_fields
                        model_hash_map[schema_hash] = model_name
                        body_model = model_name
                    
                    args["body"] = body_model
                else:
                    # Empty body_fields but has_body=True means there's a body schema
                    # Try to create a generic model
                    model_name = f"{tool_name.title().replace('_','')}Request"
                    models[model_name] = {"data": "dict"}
                    args["body"] = model_name
                    body_model = model_name

            # Extract response schema for typed responses
            response_schema = _extract_response_schema(details.get("responses", {}), spec, is_openapi)
            response_model = None
            response_fields = {}
            
            if response_schema:
                response_fields = _extract_schema_fields(response_schema, spec, is_openapi)
                if response_fields:
                    normalized_response_fields = {}
                    for field_name, field_type in response_fields.items():
                        normalized_response_fields[field_name] = _normalize_type(field_type) if isinstance(field_type, str) else field_type
                    
                    # Check if this schema already exists (deduplication)
                    response_hash = _normalize_schema_for_comparison(normalized_response_fields)
                    if response_hash in model_hash_map:
                        # Reuse existing model
                        response_model = model_hash_map[response_hash]
                    else:
                        # Create new canonical model
                        resource_name = tool_name.split('_')[-1].title() if '_' in tool_name else tool_name.title()
                        model_name = resource_name
                        
                        # Ensure unique name if collision
                        counter = 1
                        while model_name in models:
                            model_name = f"{resource_name}{counter}"
                            counter += 1
                        
                        models[model_name] = normalized_response_fields
                        model_hash_map[response_hash] = model_name
                        response_model = model_name
                else:
                    # Empty response fields but has schema - create generic response model
                    model_name = f"{tool_name.title().replace('_','')}Response"
                    models[model_name] = {"data": "dict"}
                    response_model = model_name

            tools.append({
                "name": tool_name,
                "url": base_url + path,
                "method": method.upper(),
                "auth": auth_type,
                "auth_val": auth_env,
                "args": dict(args),
                "body_model": body_model,
                "response_model": response_model,
                "has_file_fields": body_model and any(field_name == "file" for field_name in body_fields.keys()),
                "has_query_params": has_query_params,
                "desc": details.get("summary", f"{method.upper()} {path}")
            })

    return tools, models
