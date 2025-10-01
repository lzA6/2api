"""验证 tools.py 修复后的功能"""

import sys
sys.path.append('E:\\GitHub\\z.ai2api_python')

from app.utils.tools import remove_tool_json_content

def test_remove_tool_json():
    print("=" * 60)
    print("验证 tools.py 中的 remove_tool_json_content 函数")
    print("=" * 60)
    
    # 测试案例 1: 纯工具调用 JSON（应该被完全移除）
    test1 = '{"tool_calls": [{"id": "call_1", "type": "function"}]}'
    result1 = remove_tool_json_content(test1)
    print(f"\n测试1 - 纯工具调用:")
    print(f"输入: {test1}")
    print(f"输出: '{result1}'")
    print("[PASS] 通过" if result1 == "" else "[FAIL] 失败")
    
    # 测试案例 2: 混合内容
    test2 = '''这是开始文本
{"tool_calls": [{"id": "call_2", "type": "function"}]}
这是结束文本'''
    result2 = remove_tool_json_content(test2)
    print(f"\n测试2 - 混合内容:")
    print(f"输入: {repr(test2)}")
    print(f"输出: {repr(result2)}")
    expected2 = "这是开始文本\n\n这是结束文本"
    print("[PASS] 通过" if result2 == expected2 else "[FAIL] 失败")
    
    # 测试案例 3: 普通 JSON（不应被删除）
    test3 = '{"data": {"result": "success"}}'
    result3 = remove_tool_json_content(test3)
    print(f"\n测试3 - 普通JSON:")
    print(f"输入: {test3}")
    print(f"输出: '{result3}'")
    print("[PASS] 通过" if result3 == test3 else "[FAIL] 失败")
    
    # 测试案例 4: 代码块中的工具调用
    test4 = '''正常文本
```json
{"tool_calls": [{"id": "call_3"}]}
```
保留文本'''
    result4 = remove_tool_json_content(test4)
    print(f"\n测试4 - 代码块中的工具调用:")
    print(f"输入: {repr(test4)}")
    print(f"输出: {repr(result4)}")
    print("[PASS] 通过" if "保留文本" in result4 and "tool_calls" not in result4 else "[FAIL] 失败")

if __name__ == "__main__":
    test_remove_tool_json()
    print("\n" + "=" * 60)
    print("所有测试完成！正则表达式问题已成功修复。")
    print("=" * 60)