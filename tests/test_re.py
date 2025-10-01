"""测试和修复正则表达式问题"""

import json
import re

# 原始的正则表达式（来自 tools.py）
TOOL_CALL_FENCE_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
TOOL_CALL_INLINE_PATTERN_OLD = re.compile(r"(\{[^{}]{0,10000}\"tool_calls\".*?\})", re.DOTALL)

# 改进的正则表达式
# 方案1：更精确的匹配 - 只匹配包含 tool_calls 的完整 JSON 对象
TOOL_CALL_INLINE_PATTERN_NEW = re.compile(
    r'\{(?:[^{}]|\{[^{}]*\})*"tool_calls"\s*:\s*\[[^\]]*\](?:[^{}]|\{[^{}]*\})*\}',
    re.MULTILINE
)

def remove_tool_json_content_old(text: str) -> str:
    """原始的移除工具JSON内容函数"""
    
    def remove_tool_call_block(match: re.Match) -> str:
        json_content = match.group(1)
        try:
            parsed_data = json.loads(json_content)
            if "tool_calls" in parsed_data:
                return ""
        except (json.JSONDecodeError, AttributeError):
            pass
        return match.group(0)
    
    # Remove fenced tool JSON blocks
    cleaned_text = TOOL_CALL_FENCE_PATTERN.sub(remove_tool_call_block, text)
    # Remove inline tool JSON
    cleaned_text = TOOL_CALL_INLINE_PATTERN_OLD.sub("", cleaned_text)
    return cleaned_text.strip()

def remove_tool_json_content_new(text: str) -> str:
    """改进的移除工具JSON内容函数 - 使用基于括号平衡的方法"""
    
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
    
    # Step 2: Remove inline tool JSON - 使用更智能的方法
    # 查找所有可能的 JSON 对象
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

# 测试用例
test_cases = [
    # 测试案例 1: 只有工具调用JSON，应该被完全删除
    {
        "name": "纯工具调用JSON",
        "input": """{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]}""",
        "expected": ""
    },
    
    # 测试案例 2: 包含工具调用的 JSON 代码块
    {
        "name": "代码块中的工具调用",
        "input": """这是一些正常的文本内容。

```json
{
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "test_function",
        "arguments": "{\\"param\\": \\"value\\"}"
      }
    }
  ]
}
```

这部分内容应该被保留。""",
        "expected": """这是一些正常的文本内容。



这部分内容应该被保留。"""
    },
    
    # 测试案例 3: 混合内容
    {
        "name": "混合内容",
        "input": """让我为您执行一个函数调用：

{"tool_calls": [{"id": "call_789", "type": "function", "function": {"name": "search", "arguments": "{\\"query\\": \\"test\\"}"}}]}

函数执行结果如下：
- 找到了相关内容
- 处理完成

这里还有其他重要信息需要保留。""",
        "expected": """让我为您执行一个函数调用：



函数执行结果如下：
- 找到了相关内容
- 处理完成

这里还有其他重要信息需要保留。"""
    },
    
    # 测试案例 4: 不应该被删除的普通 JSON
    {
        "name": "普通JSON（应保留）",
        "input": """这是一个普通的 JSON 示例：
{"data": {"result": "success"}}

这不是工具调用，应该保留。""",
        "expected": """这是一个普通的 JSON 示例：
{"data": {"result": "success"}}

这不是工具调用，应该保留。"""
    },
    
    # 测试案例 5: 嵌套的复杂JSON
    {
        "name": "嵌套复杂JSON",
        "input": """开始文本
{"tool_calls": [{"id": "call_1", "function": {"name": "test", "arguments": "{\\"nested\\": {\\"deep\\": \\"value\\"}}"}}]}
中间文本
{"normal": {"data": "keep this"}}
结束文本""",
        "expected": """开始文本

中间文本
{"normal": {"data": "keep this"}}
结束文本"""
    }
]

def run_tests():
    print("=" * 80)
    print("测试正则表达式处理")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        print(f"\n测试案例: {test_case['name']}")
        print("-" * 40)
        print("输入文本:")
        print(repr(test_case['input']))
        
        print("\n使用原始函数处理后:")
        result_old = remove_tool_json_content_old(test_case['input'])
        print(repr(result_old))
        
        print("\n使用改进函数处理后:")
        result_new = remove_tool_json_content_new(test_case['input'])
        print(repr(result_new))
        
        print("\n期望结果:")
        print(repr(test_case['expected']))
        
        # 检查新函数是否正确
        if result_new == test_case['expected']:
            print("[PASS] 新函数通过测试")
            passed += 1
        else:
            print("[FAIL] 新函数测试失败")
            failed += 1
        
        print("-" * 40)
    
    print(f"\n\n总结: {passed} 个通过, {failed} 个失败")

if __name__ == "__main__":
    run_tests()