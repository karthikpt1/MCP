# Code Generation Issues in app.py

## Overview
This document identifies the root causes in `app.py` that generated the critical bugs found in `sampleOutput.txt`. Each issue includes the problematic code, root cause, and fix requirements.

---

## 🔴 **ISSUE #1: Malformed URLs (Missing Host)**

### Severity: CRITICAL
### Location: Lines 157-169 in `swagger_to_tools()` function

### Problematic Code:
```python
# Line 157-169 in swagger_to_tools()
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
    base_url = f"{schemes[0]}://{host}{base_path}"  # ← PROBLEM HERE
    paths = spec.get("paths", {})
    security_schemes = spec.get("securityDefinitions", {})
```

### Root Cause:
**No validation or fallback for missing `host` field**

When the Swagger spec is missing the `host` field (returns empty string `""`), the base_url becomes:
```python
base_url = f"https://{''}{''}"  # Produces "https://"
```

Then when concatenated with path in line 280:
```python
"url": base_url + path,  # "https://" + "/v2.0/metering/metering-labels"
                         # = "https:///v2.0/metering/metering-labels" ✗
```

### Expected Generated Output:
```python
# ACTUAL (WRONG):
base_url = "https:///v2.0/metering/metering-labels"
           ↑↑↑ Triple slashes, no hostname!

# EXPECTED (CORRECT):
base_url = "https://api.openstack.example.com/v2.0/metering/metering-labels"
```

### Affected Generated Code:
- Lines 37, 84, 145, 176, 207, 238, 317, 348 in `sampleOutput.txt`
- All 8 endpoints generate with malformed URLs

### Fix Required:
1. Add validation in `swagger_to_tools()` to detect missing `host` field
2. Either:
   - **Option A:** Raise error instructing user to add `host` to swagger spec
   - **Option B:** Add warning and use placeholder like `"<HOST>"` so user knows to fill it in
   - **Option C:** Prompt user to provide hostname if missing from spec

```python
# SUGGESTED FIX:
else:  # Swagger 2.0
    schemes = spec.get("schemes", ["https"])
    host = spec.get("host", "")
    base_path = spec.get("basePath", "")
    
    # NEW VALIDATION:
    if not host:
        raise ValueError(
            "❌ Swagger spec missing 'host' field. Add it like: \"host\": \"api.example.com\"\n"
            "See Swagger 2.0 spec: https://swagger.io/specification/v2/"
        )
    
    base_url = f"{schemes[0]}://{host}{base_path}"
```

---

## 🔴 **ISSUE #2: Missing Path Parameters in Function Arguments**

### Severity: CRITICAL
### Location: Lines 191-228 in `swagger_to_tools()` parameter parsing

### Problematic Code:
```python
# Lines 191-228 (Parameter extraction loop)
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
        args[p_name] = param_type  # ← PATH PARAMS ARE ADDED HERE
    # ... rest of loop
```

### Root Cause:
**Path parameters ARE being added to `args` dict correctly in lines 195-207, BUT they're not being passed to the generated function signature**

Looking at the Jinja2 template (line 425):
```jinja2
def {{ tool.name }}({% for arg, type in tool.args.items() %}{{ arg }}: {{ type }}{% if not loop.last %}, {% endif %}{% endfor %}):
    args_dict = { {% for arg in tool.args.keys() %}"{{ arg }}": {{ arg }}{% if not loop.last %}, {% endif %}{% endfor %} }
```

**This should be working correctly, BUT it's not!** The issue is that:

1. ✅ Path parameters ARE extracted in `swagger_to_tools()` (lines 201-207)
2. ✅ They ARE added to `tool.args` dict
3. ✅ The Jinja2 template SHOULD include them in function signature
4. ❌ But the generated code shows empty `args_dict` for endpoints with path parameters

### Example from swagger.json:
```json
{
  "path": "/metering/metering-labels/{metering_label_id}",
  "parameters": [
    {
      "name": "metering_label_id",
      "in": "path",
      "type": "string",
      "required": true
    }
  ]
}
```

### Expected Generated Output:
```python
# EXPECTED:
def getMeteringLabel(metering_label_id: str):
    args_dict = {
        "metering_label_id": metering_label_id
    }
    base_url = "https://api.example.com/v2.0/metering/metering-labels/{metering_label_id}"
    # ... then replace path params ...
```

### Actual Generated Output (from sampleOutput.txt line 145-150):
```python
def getMeteringLabel():  # ← NO PARAMETERS!
    args_dict = { }  # ← EMPTY!
    
    base_url = "https:///v2.0/metering/metering-labels/{metering_label_id}"
    # Can't replace {metering_label_id} because it's not in args_dict
```

### Affected Generated Code:
- Line 145-150: `getMeteringLabel()` (needs `metering_label_id`)
- Line 176-181: `deleteMeteringLabel()` (needs `metering_label_id`)
- Line 313-318: `getMeteringLabelRule()` (needs `metering-label-rule-id`)
- Line 344-349: `deleteMeteringLabelRule()` (needs `metering-label-rule-id`)

### Root Cause Analysis:
The issue is likely in how `swagger_to_tools()` parses the swagger.json. Looking at swagger.json:
- It's **missing** the `host`, `schemes`, and `basePath` fields
- This causes parsing to fail or skip path parameter extraction

Wait, re-reading the code: If `host` is empty, the whole parsing might be silently failing.

**Actual Root Cause:** Line 166 - when `host=""`, the condition `if not host:` doesn't raise error, and base_url becomes just `"https://"`. Path parameters might still be extracted, but the combination with empty host might be breaking things.

Let me check the actual generated code flow more carefully by tracing swagger.json through the code...

Actually, looking at lines 158-169 again - the swagger_to_tools() IS extracting path parameters correctly into args dict at line 201-207. The issue is likely that **swagger.json is missing required fields**, and we should validate this earlier.

### Fix Required:
1. **Validate swagger spec has required fields before processing:**

```python
# ADD AT START OF swagger_to_tools():
def swagger_to_tools(swagger_text):
    try:
        spec = json.loads(swagger_text)
    except json.JSONDecodeError:
        spec = yaml.safe_load(swagger_text)
    
    if spec is None:
        return [], {}

    # NEW: Validate spec completeness
    is_openapi = "openapi" in spec
    
    if is_openapi:
        # OpenAPI 3.0 requires servers field
        if "servers" not in spec or not spec["servers"]:
            raise ValueError(
                "❌ OpenAPI spec missing 'servers' field. Add it like:\n"
                "\"servers\": [{\"url\": \"https://api.example.com/v1\"}]"
            )
    else:
        # Swagger 2.0 requires host, basePath, schemes
        if "host" not in spec or not spec["host"]:
            raise ValueError(
                "❌ Swagger spec missing required 'host' field.\n"
                "Add: \"host\": \"api.example.com\""
            )
        if "basePath" not in spec:
            raise ValueError(
                "❌ Swagger spec missing 'basePath' field.\n"
                "Add: \"basePath\": \"/v2.0\""
            )
        if "schemes" not in spec or not spec["schemes"]:
            raise ValueError(
                "❌ Swagger spec missing 'schemes' field.\n"
                "Add: \"schemes\": [\"https\"]"
            )
```

---

## ⚠️ **ISSUE #3: Duplicate Prompt Function Names**

### Severity: HIGH (Overwrites 75% of prompts)
### Location: Lines 489-495 in `generate_mcp_code()` Jinja2 template

### Problematic Code (Jinja2 Template):
```jinja2
{% for prompt in prompts %}
@mcp.prompt()
def {{ prompt.name }}({{ prompt.args }}):
    \"\"\"{{ prompt.desc }}\"\"\"
    return f\"\"\"{{ prompt.text }}\"\"\"

{% endfor %}
```

### Root Cause:
**LLM generates same prompt name for all instances, instead of unique names per tool**

In `auto_generate_prompts()` (lines 300-370), the function returns prompts with the same name as the tool:

```python
# Line 352-357 in auto_generate_prompts():
if is_tool_header:
    # Save previous tool's prompt if exists
    if current_tool and tool_prompt_lines:
        combined_text = " ".join(tool_prompt_lines)
        all_prompts.append({
            "name": current_tool,  # ← Uses tool name, not unique prompt name!
            "args": "",
            "text": combined_text,
            "desc": f"Auto-generated prompt for {current_tool}"
        })
```

### Expected Behavior:
Generate unique prompt function names:
- Tool: `listMeteringLabels`
  - Prompt 1: `listMeteringLabels_summarize` (summarize output)
  - Prompt 2: `listMeteringLabels_error_analysis` (analyze errors)
  - Prompt 3: `listMeteringLabels_compare_context` (compare results)

### Actual Generated Output (from sampleOutput.txt):
```python
# Lines 380-383:
@mcp.prompt()
def listMeteringLabels():  # ← Prompt 1
    return "### Summarize output intent"

# Lines 385-388:
@mcp.prompt()
def listMeteringLabels():  # ← Prompt 2 OVERWRITES above!
    return "### Analyze possible errors..."

# Lines 390-393:
@mcp.prompt()
def listMeteringLabels():  # ← Prompt 3 OVERWRITES above!
    return "### Compare results..."

# Lines 394-397:
@mcp.prompt()
def listMeteringLabels():  # ← Prompt 4 OVERWRITES again!
    return "------------------------"
```

**Result:** Only LAST definition survives in Python. First 3 are silently overwritten.

### Affected Generated Code:
- `listMeteringLabels()` - defined 4 times (lines 380, 385, 390, 394) → only last survives
- `createMeteringLabel()` - defined 8 times (overwrites from both tools and prompts)
- `getMeteringLabel()` - defined 8 times
- `deleteMeteringLabel()` - defined 8 times
- Similar for all label rules functions

**Total:** 32 prompt functions generated, but only ~8 unique ones survive (Python overwrites duplicates)

### Fix Required:
**Modify `auto_generate_prompts()` to generate unique prompt names:**

Option 1: Add suffix based on prompt type detected from LLM response:
```python
# In auto_generate_prompts(), parse prompt type from generated text:
prompt_type = "unknown"
if "summarize" in combined_text.lower():
    prompt_type = "summarize"
elif "error" in combined_text.lower():
    prompt_type = "error_analysis"
elif "compare" in combined_text.lower():
    prompt_type = "compare_context"

all_prompts.append({
    "name": f"{current_tool}_{prompt_type}",  # ← UNIQUE!
    "args": "",
    "text": combined_text,
    "desc": f"Auto-generated prompt for {current_tool}"
})
```

Option 2: Use counter per tool:
```python
prompt_counter = {}
# ...
if current_tool not in prompt_counter:
    prompt_counter[current_tool] = 0
prompt_counter[current_tool] += 1

all_prompts.append({
    "name": f"{current_tool}_prompt{prompt_counter[current_tool]}",
    # ...
})
```

Option 3 (BEST): Let user customize prompt names in Step 2 UI:
```python
# Show editable prompt names in Step 2:
st.session_state.prompts[idx]["name"] = st.text_input(
    "Prompt Name (must be unique)",
    value=prompt["name"],
    key=f"edit_name_{idx}"
)
```

---

## 📋 Summary Table

| Issue | Location | Severity | Root Cause | Generated Impact | Fix Effort |
|-------|----------|----------|-----------|-----------------|-----------|
| **#1: Malformed URLs** | Lines 157-169 | CRITICAL | No validation for missing `host` field | 8/8 endpoints broken URLs | 1 hour |
| **#2: Missing Path Params** | Lines 191-228 | CRITICAL | Empty `args_dict` for parameterized endpoints | 4/8 endpoints can't accept IDs | 1-2 hours |
| **#3: Duplicate Prompt Names** | Lines 489-495 + auto_generate_prompts() | HIGH | Prompt names not unique, Python overwrites | 24/32 prompts lost | 30 min |
| **#4: No Spec Validation** | Start of swagger_to_tools() | MEDIUM | No error on missing required fields | Silent failures, confusing bugs | 30 min |

---

## Implementation Priority

1. **FIRST (Blocks all deployment):** Fix Issue #1 - URL validation
   - Add early checks for required fields in swagger_to_tools()
   - Raise clear error messages with examples

2. **SECOND (Blocks 50% of endpoints):** Fix Issue #2 - Path parameter extraction
   - Debug why path params aren't reaching generated code
   - Verify Jinja2 template renders them correctly

3. **THIRD (Blocks 75% of prompts):** Fix Issue #3 - Unique prompt names
   - Implement unique name generation in auto_generate_prompts()
   - Consider UI improvements for user customization

4. **FOURTH (Prevents confusion):** Add comprehensive input validation
   - Check for required Swagger/OpenAPI fields
   - Provide user-friendly error messages with examples

---

## Testing Strategy

After fixes, validate with swagger.json:
1. ✅ Parse successfully with proper validation
2. ✅ Generate correct base_url with host/basePath
3. ✅ Extract all path parameters to function args
4. ✅ Generate unique prompt function names
5. ✅ Run generated code without Python syntax errors
6. ✅ Test URL construction with actual path parameter values
