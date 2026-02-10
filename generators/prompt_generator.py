"""
Prompt generation module for MCP servers.
Generates MCP-compliant prompt templates using LLM APIs.
"""

from openai import OpenAI


def auto_generate_prompts(tools, api_key=None, provider="openai"):
    """
    Generate MCP-compliant prompt templates for API tools using LLM.
    One prompt per tool with specific arguments matching the tool's parameters.
    Supports both OpenAI and Groq providers.
    
    Args:
        tools (list): List of tool definitions with name, args, desc, etc.
        api_key (str): API key for the LLM provider
        provider (str): "openai" or "groq"
    
    Returns:
        list: List of prompt templates with name, args, text, desc fields
    """
    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=api_key)
        model = "llama-3.1-8b-instant"
    else:
        if api_key:
            client = OpenAI(api_key=api_key)
        else:
            client = OpenAI()
        model = "gpt-4o"

    tool_descriptions = []
    for t in tools:
        args = ", ".join(t["args"].keys()) if t["args"] else "none"
        tool_descriptions.append(
            f"Tool: {t['name']}\nDescription: {t['desc']}\nMethod: {t['method']}\nURL: {t['url']}\nArguments: {args}"
        )

    joined = "\n\n---\n\n".join(tool_descriptions)

    user_msg = f"""
You are an expert at creating MCP (Model Context Protocol) prompt templates for API tools.

For EACH API tool below, generate exactly ONE prompt template following MCP standards.

CRITICAL RULES:
1. Prompt Name MUST be EXACTLY the same as the tool name
2. If tool has NO arguments (Arguments: none), do NOT use any {{{{placeholders}}}} in the text
3. If tool HAS arguments, use {{{{argument_name}}}} placeholders

Format requirement:
1. Prompt Name: MUST be identical to the tool name (this enables MCP auto-linking)
2. Prompt Arguments: Extract relevant arguments from the tool's parameter list (comma-separated, or empty if "none")
3. Prompt Text: Write a clear instruction. ONLY use {{{{placeholder}}}} if that argument exists in the tool!

MCP Prompt Format:
- Name: [ToolName] - MUST EXACTLY match the tool name
- Arguments: [Extracted from tool args, or leave EMPTY if tool has no arguments]
- Description: [One-line description]
- Text: [Template with NO placeholders if tool has no arguments]

EXAMPLES:

Example 1 - Tool WITH arguments "GetUser" (id, limit):
- Name: GetUser
- Arguments: id, limit
- Description: Fetch user details
- Text: "Query user with ID {{{{id}}}} and retrieve {{{{limit}}}} records"

Example 2 - Tool with NO arguments "ListAllContinents" ():
- Name: ListAllContinents
- Arguments: (EMPTY)
- Description: List all continents
- Text: "Retrieve the complete list of continents"

Tools:
{joined}

Generate exactly one complete MCP prompt template per tool. Format each as:
---
Tool: [tool_name]
Name: [tool_name] (MUST BE IDENTICAL)
Arguments: [arg1, arg2, ...] or EMPTY if no arguments
Description: [description]
Text: [template text with placeholders ONLY for arguments that exist]
---
    """

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that generates MCP-compliant prompts for API tools. IMPORTANT: Only use {{{{placeholders}}}} for arguments that actually exist in the tool."},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7,
        max_tokens=1200
    )

    text = response.choices[0].message.content.strip()

    all_prompts = []
    current_tool = None
    current_prompt = {
        "name": "",
        "args": "",
        "text": "",
        "desc": ""
    }
    
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and separators
        if not line or line == "---":
            # If we have a complete prompt, save it
            if current_prompt["name"] and current_prompt["text"]:
                # Force prompt name to match tool name for MCP auto-linking
                if current_tool:
                    current_prompt["name"] = current_tool
                # Clean up prompt text: replace {{ with { and }} with }
                cleaned_text = current_prompt["text"].replace("{{", "{").replace("}}", "}")
                # Remove surrounding quotes if present
                cleaned_text = cleaned_text.strip('"\'')
                all_prompts.append({
                    "name": current_prompt["name"],
                    "args": current_prompt["args"],
                    "text": cleaned_text,
                    "desc": current_prompt["desc"]
                })
                current_prompt = {
                    "name": "",
                    "args": "",
                    "text": "",
                    "desc": ""
                }
            continue
        
        # Parse MCP format lines
        if line.lower().startswith("tool:"):
            current_tool = line.replace("Tool:", "").replace("tool:", "").strip()
        elif line.lower().startswith("name:"):
            current_prompt["name"] = line.replace("Name:", "").replace("name:", "").strip()
        elif line.lower().startswith("arguments:"):
            current_prompt["args"] = line.replace("Arguments:", "").replace("arguments:", "").strip()
        elif line.lower().startswith("description:"):
            current_prompt["desc"] = line.replace("Description:", "").replace("description:", "").strip()
        elif line.lower().startswith("text:"):
            # Capture text after "Text:" and continue on next lines
            current_prompt["text"] = line.replace("Text:", "").replace("text:", "").strip()
        elif current_prompt["name"] and line and not line.lower().startswith(("tool:", "name:", "arguments:", "description:")):
            # Continue capturing multi-line text
            if current_prompt["text"]:
                current_prompt["text"] += " " + line
            else:
                current_prompt["text"] = line
    
    # Don't forget the last prompt
    if current_prompt["name"] and current_prompt["text"]:
        # Clean up prompt text: replace {{ with { and }} with }
        cleaned_text = current_prompt["text"].replace("{{", "{").replace("}}", "}")
        # Remove surrounding quotes if present
        cleaned_text = cleaned_text.strip('"\'')
        all_prompts.append({
            "name": current_prompt["name"],
            "args": current_prompt["args"],
            "text": cleaned_text,
            "desc": current_prompt["desc"]
        })
    
    return all_prompts
