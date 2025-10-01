"""
Tool processing utilities
"""

import json
import re
import time
from typing import Dict, List, Optional, Any

from app.core.config import settings


def content_to_string(content: Any) -> str:
    """Convert content from various formats to string (following app.py pattern)"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(parts)
    return ""


def generate_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """Generate tool injection prompt with enhanced formatting"""
    if not tools:
        return ""

    tool_definitions = []
    for tool in tools:
        if tool.get("type") != "function":
            continue

        function_spec = tool.get("function", {}) or {}
        function_name = function_spec.get("name", "unknown")
        function_description = function_spec.get("description", "")
        parameters = function_spec.get("parameters", {}) or {}

        # Create structured tool definition
        tool_info = [f"## {function_name}", f"**Purpose**: {function_description}"]

        # Add parameter details
        parameter_properties = parameters.get("properties", {}) or {}
        required_parameters = set(parameters.get("required", []) or [])

        if parameter_properties:
            tool_info.append("**Parameters**:")
            for param_name, param_details in parameter_properties.items():
                param_type = (param_details or {}).get("type", "any")
                param_desc = (param_details or {}).get("description", "")
                requirement_flag = "**Required**" if param_name in required_parameters else "*Optional*"
                tool_info.append(f"- `{param_name}` ({param_type}) - {requirement_flag}: {param_desc}")

        tool_definitions.append("\n".join(tool_info))

    if not tool_definitions:
        return ""

    # Build comprehensive tool prompt
    prompt_template = (
        "\n\n# AVAILABLE FUNCTIONS\n" + "\n\n---\n".join(tool_definitions) + "\n\n# USAGE INSTRUCTIONS\n"
        "When you need to execute a function, respond ONLY with a JSON object containing tool_calls:\n"
        "```json\n"
        "{\n"
        '  "tool_calls": [\n'
        "    {\n"
        '      "id": "call_xxx",\n'
        '      "type": "function",\n'
        '      "function": {\n'
        '        "name": "function_name",\n'
        '        "arguments": "{\\"param1\\": \\"value1\\"}"\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
        "Important: No explanatory text before or after the JSON. The 'arguments' field must be a JSON string, not an object.\n"
    )

    return prompt_template


def process_messages_with_tools(
    messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, tool_choice: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """Process messages and inject tool prompts"""
    processed: List[Dict[str, Any]] = []

    if tools and settings.TOOL_SUPPORT and (tool_choice != "none"):
        tools_prompt = generate_tool_prompt(tools)
        has_system = any(m.get("role") == "system" for m in messages)

        if has_system:
            for m in messages:
                if m.get("role") == "system":
                    mm = dict(m)
                    content = content_to_string(mm.get("content", ""))
                    mm["content"] = content + tools_prompt
                    processed.append(mm)
                else:
                    processed.append(m)
        else:
            processed = [{"role": "system", "content": "你是一个有用的助手。" + tools_prompt}] + messages

        # Add tool choice hints
        if tool_choice in ("required", "auto"):
            if processed and processed[-1].get("role") == "user":
                last = dict(processed[-1])
                content = content_to_string(last.get("content", ""))
                last["content"] = content + "\n\n请根据需要使用提供的工具函数。"
                processed[-1] = last
        elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
            fname = (tool_choice.get("function") or {}).get("name")
            if fname and processed and processed[-1].get("role") == "user":
                last = dict(processed[-1])
                content = content_to_string(last.get("content", ""))
                last["content"] = content + f"\n\n请使用 {fname} 函数来处理这个请求。"
                processed[-1] = last
    else:
        processed = list(messages)

    # Handle tool/function messages
    final_msgs: List[Dict[str, Any]] = []
    for m in processed:
        role = m.get("role")
        if role in ("tool", "function"):
            tool_name = m.get("name", "unknown")
            tool_content = content_to_string(m.get("content", ""))
            if isinstance(tool_content, dict):
                tool_content = json.dumps(tool_content, ensure_ascii=False)

            # 确保内容不为空且不包含 None
            content = f"工具 {tool_name} 返回结果:\n```json\n{tool_content}\n```"
            if not content.strip():
                content = f"工具 {tool_name} 执行完成"

            final_msgs.append(
                {
                    "role": "assistant",
                    "content": content,
                }
            )
        else:
            # For regular messages, ensure content is string format
            final_msg = dict(m)
            content = content_to_string(final_msg.get("content", ""))
            final_msg["content"] = content
            final_msgs.append(final_msg)

    return final_msgs


# Tool Extraction Patterns
TOOL_CALL_FENCE_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
# 注意：TOOL_CALL_INLINE_PATTERN 已被移除，因为它会导致过度匹配
# 现在在 remove_tool_json_content 函数中使用基于括号平衡的方法
FUNCTION_CALL_PATTERN = re.compile(r"调用函数\s*[：:]\s*([\w\-\.]+)\s*(?:参数|arguments)[：:]\s*(\{.*?\})", re.DOTALL)


def extract_tool_invocations(text: str) -> Optional[List[Dict[str, Any]]]:
    """Extract tool invocations from response text"""
    if not text:
        return None

    # Limit scan size for performance
    scannable_text = text[: settings.SCAN_LIMIT]

    # Attempt 1: Extract from JSON code blocks
    json_blocks = TOOL_CALL_FENCE_PATTERN.findall(scannable_text)
    for json_block in json_blocks:
        try:
            parsed_data = json.loads(json_block)
            tool_calls = parsed_data.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                # Ensure arguments field is a string
                for tc in tool_calls:
                    if "function" in tc:
                        func = tc["function"]
                        if "arguments" in func:
                            if isinstance(func["arguments"], dict):
                                # Convert dict to JSON string
                                func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
                            elif not isinstance(func["arguments"], str):
                                func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
                return tool_calls
        except (json.JSONDecodeError, AttributeError):
            continue

    # Attempt 2: Extract inline JSON objects using bracket balance method
    # 查找包含 "tool_calls" 的 JSON 对象
    i = 0
    while i < len(scannable_text):
        if scannable_text[i] == '{':
            # 尝试找到匹配的右括号
            brace_count = 1
            j = i + 1
            in_string = False
            escape_next = False
            
            while j < len(scannable_text) and brace_count > 0:
                if escape_next:
                    escape_next = False
                elif scannable_text[j] == '\\':
                    escape_next = True
                elif scannable_text[j] == '"' and not escape_next:
                    in_string = not in_string
                elif not in_string:
                    if scannable_text[j] == '{':
                        brace_count += 1
                    elif scannable_text[j] == '}':
                        brace_count -= 1
                j += 1
            
            if brace_count == 0:
                # 找到了完整的 JSON 对象
                json_str = scannable_text[i:j]
                try:
                    parsed_data = json.loads(json_str)
                    tool_calls = parsed_data.get("tool_calls")
                    if tool_calls and isinstance(tool_calls, list):
                        # Ensure arguments field is a string
                        for tc in tool_calls:
                            if "function" in tc:
                                func = tc["function"]
                                if "arguments" in func:
                                    if isinstance(func["arguments"], dict):
                                        # Convert dict to JSON string
                                        func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
                                    elif not isinstance(func["arguments"], str):
                                        func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
                        return tool_calls
                except (json.JSONDecodeError, AttributeError):
                    pass
            
            i += 1
        else:
            i += 1

    # Attempt 3: Parse natural language function calls
    natural_lang_match = FUNCTION_CALL_PATTERN.search(scannable_text)
    if natural_lang_match:
        function_name = natural_lang_match.group(1).strip()
        arguments_str = natural_lang_match.group(2).strip()
        try:
            # Validate JSON format
            json.loads(arguments_str)
            return [
                {
                    "id": f"call_{int(time.time() * 1000000)}",
                    "type": "function",
                    "function": {"name": function_name, "arguments": arguments_str},
                }
            ]
        except json.JSONDecodeError:
            return None

    return None


def remove_tool_json_content(text: str) -> str:
    """Remove tool JSON content from response text - using bracket balance method"""
    
    def remove_tool_call_block(match: re.Match) -> str:
        json_content = match.group(1)
        try:
            parsed_data = json.loads(json_content)
            if "tool_calls" in parsed_data:
                return ""
        except (json.JSONDecodeError, AttributeError):
            pass
        return match.group(0)
    
    # Step 1: Remove fenced tool JSON blocks
    cleaned_text = TOOL_CALL_FENCE_PATTERN.sub(remove_tool_call_block, text)
    
    # Step 2: Remove inline tool JSON - 使用基于括号平衡的智能方法
    # 查找所有可能的 JSON 对象并精确删除包含 tool_calls 的对象
    result = []
    i = 0
    while i < len(cleaned_text):
        if cleaned_text[i] == '{':
            # 尝试找到匹配的右括号
            brace_count = 1
            j = i + 1
            in_string = False
            escape_next = False
            
            while j < len(cleaned_text) and brace_count > 0:
                if escape_next:
                    escape_next = False
                elif cleaned_text[j] == '\\':
                    escape_next = True
                elif cleaned_text[j] == '"' and not escape_next:
                    in_string = not in_string
                elif not in_string:
                    if cleaned_text[j] == '{':
                        brace_count += 1
                    elif cleaned_text[j] == '}':
                        brace_count -= 1
                j += 1
            
            if brace_count == 0:
                # 找到了完整的 JSON 对象
                json_str = cleaned_text[i:j]
                try:
                    parsed = json.loads(json_str)
                    if "tool_calls" in parsed:
                        # 这是一个工具调用，跳过它
                        i = j
                        continue
                except:
                    pass
            
            # 不是工具调用或无法解析，保留这个字符
            result.append(cleaned_text[i])
            i += 1
        else:
            result.append(cleaned_text[i])
            i += 1
    
    return ''.join(result).strip()
