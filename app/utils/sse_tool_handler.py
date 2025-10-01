#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SSE Tool Handler - 处理工具调用的SSE流
基于 Z.AI 原生的 edit_index 和 edit_content 机制，更原生地处理工具调用
"""

import json
import re
import time
from typing import Dict, Any, Optional, Generator, List

from app.utils.helpers import debug_log


class SSEToolHandler:

    def __init__(self, chat_id: str, model: str):
        self.chat_id = chat_id
        self.model = model

        # 工具调用状态
        self.has_tool_call = False
        self.tool_call_usage = None  # 工具调用的usage信息
        self.content_index = 0
        self.has_thinking = False

        self.content_buffer = bytearray()  # 使用字节数组提高性能
        self.last_edit_index = 0  # 上次编辑的位置

        # 工具调用解析状态
        self.active_tools = {}  # 活跃的工具调用 {tool_id: tool_info}
        self.completed_tools = []  # 已完成的工具调用
        self.tool_blocks_cache = {}  # 缓存解析的工具块

    def process_tool_call_phase(self, data: Dict[str, Any], is_stream: bool = True) -> Generator[str, None, None]:
        """
        处理tool_call阶段
        """
        if not self.has_tool_call:
            self.has_tool_call = True
            debug_log("🔧 进入工具调用阶段")

        edit_content = data.get("edit_content", "")
        edit_index = data.get("edit_index", 0)

        if not edit_content:
            return

        # debug_log(f"📦 接收内容片段 [index={edit_index}]: {edit_content[:1000]}...")

        # 更新内容缓冲区
        self._apply_edit_to_buffer(edit_index, edit_content)

        # 尝试解析和处理工具调用
        yield from self._process_tool_calls_from_buffer(is_stream)

    def _apply_edit_to_buffer(self, edit_index: int, edit_content: str):
        """
        在指定位置替换/插入内容更新内容缓冲区
        """
        edit_bytes = edit_content.encode('utf-8')
        required_length = edit_index + len(edit_bytes)

        # 扩展缓冲区到所需长度（如果需要）
        if len(self.content_buffer) < edit_index:
            # 如果edit_index超出当前缓冲区，用空字节填充
            self.content_buffer.extend(b'\x00' * (edit_index - len(self.content_buffer)))

        # 确保缓冲区足够长以容纳新内容
        if len(self.content_buffer) < required_length:
            self.content_buffer.extend(b'\x00' * (required_length - len(self.content_buffer)))

        # 在指定位置替换内容（不是插入，而是覆盖）
        end_index = edit_index + len(edit_bytes)
        self.content_buffer[edit_index:end_index] = edit_bytes

        # debug_log(f"📝 缓冲区更新 [index={edit_index}, 长度={len(self.content_buffer)}]")

    def _process_tool_calls_from_buffer(self, is_stream: bool) -> Generator[str, None, None]:
        """
        从内容缓冲区中解析和处理工具调用
        """
        try:
            # 解码内容并清理空字节
            content_str = self.content_buffer.decode('utf-8', errors='ignore').replace('\x00', '')
            yield from self._extract_and_process_tools(content_str, is_stream)
        except Exception as e:
            debug_log(f"📦 内容解析暂时失败，等待更多数据: {e}")
            # 不抛出异常，继续等待更多数据

    def _extract_and_process_tools(self, content_str: str, is_stream: bool) -> Generator[str, None, None]:
        """
        从内容字符串中提取和处理工具调用
        """
        # 查找所有 glm_block，包括不完整的
        pattern = r'<glm_block\s*>(.*?)(?:</glm_block>|$)'
        matches = re.findall(pattern, content_str, re.DOTALL)

        for block_content in matches:
            # 尝试解析每个块
            yield from self._process_single_tool_block(block_content, is_stream)

    def _process_single_tool_block(self, block_content: str, is_stream: bool) -> Generator[str, None, None]:
        """
        处理单个工具块，支持增量解析
        """
        try:
            # 尝试修复和解析完整的JSON
            fixed_content = self._fix_json_structure(block_content)
            tool_data = json.loads(fixed_content)
            metadata = tool_data.get("data", {}).get("metadata", {})

            tool_id = metadata.get("id", "")
            tool_name = metadata.get("name", "")
            arguments_raw = metadata.get("arguments", "{}")

            if not tool_id or not tool_name:
                return

            debug_log(f"🎯 解析完整工具块: {tool_name}(id={tool_id}), 参数: {arguments_raw}")

            # 检查是否是新工具或更新的工具
            yield from self._handle_tool_update(tool_id, tool_name, arguments_raw, is_stream)

        except json.JSONDecodeError as e:
            debug_log(f"📦 JSON解析失败: {e}, 尝试部分解析")
            # JSON 不完整，尝试部分解析
            yield from self._handle_partial_tool_block(block_content, is_stream)
        except Exception as e:
            debug_log(f"📦 工具块处理失败: {e}")

    def _fix_json_structure(self, content: str) -> str:
        """
        修复JSON结构中的常见问题
        """
        if not content:
            return content

        # 计算括号平衡
        open_braces = content.count('{')
        close_braces = content.count('}')

        # 如果闭括号多于开括号，移除多余的闭括号
        if close_braces > open_braces:
            excess = close_braces - open_braces
            fixed_content = content
            for _ in range(excess):
                # 从右侧移除多余的闭括号
                last_brace_pos = fixed_content.rfind('}')
                if last_brace_pos != -1:
                    fixed_content = fixed_content[:last_brace_pos] + fixed_content[last_brace_pos + 1:]
            return fixed_content

        return content

    def _handle_tool_update(self, tool_id: str, tool_name: str, arguments_raw: str, is_stream: bool) -> Generator[str, None, None]:
        """
        处理工具的创建或更新 - 更可靠的参数完整性检查
        """
        # 解析参数
        try:
            if isinstance(arguments_raw, str):
                # 先处理转义和清理
                cleaned_args = self._clean_arguments_string(arguments_raw)
                arguments = json.loads(cleaned_args) if cleaned_args.strip() else {}
            else:
                arguments = arguments_raw
        except json.JSONDecodeError:
            debug_log(f"📦 参数解析失败，暂不处理: {arguments_raw}")
            # 参数解析失败时，不创建或更新工具，等待更完整的数据
            return

        # 检查参数是否看起来完整（基本的完整性验证）
        is_args_complete = self._is_arguments_complete(arguments, arguments_raw)

        # 检查是否是新工具
        if tool_id not in self.active_tools:
            debug_log(f"🎯 发现新工具: {tool_name}(id={tool_id}), 参数完整性: {is_args_complete}")

            self.active_tools[tool_id] = {
                "id": tool_id,
                "name": tool_name,
                "arguments": arguments,
                "arguments_raw": arguments_raw,
                "status": "active",
                "sent_start": False,
                "last_sent_args": {},  # 跟踪上次发送的参数
                "args_complete": is_args_complete,
                "pending_send": True  # 标记需要发送
            }

            # 只有在参数看起来完整时才发送工具开始信号
            if is_stream and is_args_complete:
                yield self._create_tool_start_chunk(tool_id, tool_name, arguments)
                self.active_tools[tool_id]["sent_start"] = True
                self.active_tools[tool_id]["last_sent_args"] = arguments.copy()
                self.active_tools[tool_id]["pending_send"] = False
                debug_log(f"📤 发送完整工具开始: {tool_name}(id={tool_id})")

        else:
            # 更新现有工具
            current_tool = self.active_tools[tool_id]

            # 检查是否有实质性改进
            if self._is_significant_improvement(current_tool["arguments"], arguments,
                                               current_tool["arguments_raw"], arguments_raw):
                debug_log(f"🔄 工具参数有实质性改进: {tool_name}(id={tool_id})")

                current_tool["arguments"] = arguments
                current_tool["arguments_raw"] = arguments_raw
                current_tool["args_complete"] = is_args_complete

                # 如果之前没有发送过开始信号，且现在参数完整，发送开始信号
                if is_stream and not current_tool["sent_start"] and is_args_complete:
                    yield self._create_tool_start_chunk(tool_id, tool_name, arguments)
                    current_tool["sent_start"] = True
                    current_tool["last_sent_args"] = arguments.copy()
                    current_tool["pending_send"] = False
                    debug_log(f"📤 发送延迟的工具开始: {tool_name}(id={tool_id})")

                # 如果已经发送过开始信号，且参数有显著改进，发送参数更新
                elif is_stream and current_tool["sent_start"] and is_args_complete:
                    if self._should_send_argument_update(current_tool["last_sent_args"], arguments):
                        yield self._create_tool_arguments_chunk(tool_id, arguments)
                        current_tool["last_sent_args"] = arguments.copy()
                        debug_log(f"📤 发送参数更新: {tool_name}(id={tool_id})")

    def _is_arguments_complete(self, arguments: Dict[str, Any], arguments_raw: str) -> bool:
        """
        检查参数是否看起来完整
        """
        if not arguments:
            return False

        # 检查原始字符串是否看起来完整
        if not arguments_raw or not arguments_raw.strip():
            return False

        # 检查是否有明显的截断迹象
        raw_stripped = arguments_raw.strip()

        # 如果原始字符串不以}结尾，可能是截断的
        if not raw_stripped.endswith('}') and not raw_stripped.endswith('"'):
            return False

        # 检查是否有不完整的URL（常见的截断情况）
        for key, value in arguments.items():
            if isinstance(value, str):
                # 检查URL是否看起来完整
                if 'http' in value.lower():
                    # 如果URL太短或以不完整的域名结尾，可能是截断的
                    if len(value) < 10 or value.endswith('.go') or value.endswith('.goo'):
                        return False

                # 检查其他可能的截断迹象
                if len(value) > 0 and value[-1] in ['.', '/', ':', '=']:
                    # 以这些字符结尾可能表示截断
                    return False

        return True

    def _is_significant_improvement(self, old_args: Dict[str, Any], new_args: Dict[str, Any],
                                   old_raw: str, new_raw: str) -> bool:
        """
        检查新参数是否比旧参数有显著改进
        """
        # 如果新参数为空，不是改进
        if not new_args:
            return False
        
        if len(new_args) > len(old_args):
            return True

        # 检查值的改进
        for key, new_value in new_args.items():
            old_value = old_args.get(key, "")

            if isinstance(new_value, str) and isinstance(old_value, str):
                # 如果新值明显更长且更完整，是改进
                if len(new_value) > len(old_value) + 5:  # 至少长5个字符才算显著改进
                    return True

                # 如果旧值看起来是截断的，新值更完整，是改进
                if old_value.endswith(('.go', '.goo', '.com/', 'http')) and len(new_value) > len(old_value):
                    return True

        # 检查原始字符串的改进
        if len(new_raw) > len(old_raw) + 10:  # 原始字符串显著增长
            return True

        return False

    def _should_send_argument_update(self, last_sent: Dict[str, Any], new_args: Dict[str, Any]) -> bool:
        """
        判断是否应该发送参数更新 - 更严格的标准
        """
        # 如果参数完全相同，不发送
        if last_sent == new_args:
            return False

        # 如果新参数为空但之前有参数，不发送（避免倒退）
        if not new_args and last_sent:
            return False

        # 如果新参数有更多键，发送更新
        if len(new_args) > len(last_sent):
            return True

        # 检查是否有值变得显著更完整
        for key, new_value in new_args.items():
            last_value = last_sent.get(key, "")
            if isinstance(new_value, str) and isinstance(last_value, str):
                # 只有在值显著增长时才发送更新（避免微小变化）
                if len(new_value) > len(last_value) + 5:
                    return True
            elif new_value != last_value and new_value:  # 确保新值不为空
                return True

        return False

    def _handle_partial_tool_block(self, block_content: str, is_stream: bool) -> Generator[str, None, None]:
        """
        处理不完整的工具块，尝试提取可用信息
        """
        try:
            # 尝试提取工具ID和名称
            id_match = re.search(r'"id":\s*"([^"]+)"', block_content)
            name_match = re.search(r'"name":\s*"([^"]+)"', block_content)

            if id_match and name_match:
                tool_id = id_match.group(1)
                tool_name = name_match.group(1)

                # 尝试提取参数部分
                args_match = re.search(r'"arguments":\s*"([^"]*)', block_content)
                partial_args = args_match.group(1) if args_match else ""

                debug_log(f"📦 部分工具块: {tool_name}(id={tool_id}), 部分参数: {partial_args[:50]}")

                # 如果是新工具，先创建记录
                if tool_id not in self.active_tools:
                    # 尝试解析部分参数为字典
                    partial_args_dict = self._parse_partial_arguments(partial_args)

                    self.active_tools[tool_id] = {
                        "id": tool_id,
                        "name": tool_name,
                        "arguments": partial_args_dict,
                        "status": "partial",
                        "sent_start": False,
                        "last_sent_args": {},
                        "args_complete": False,
                        "partial_args": partial_args
                    }

                    if is_stream:
                        yield self._create_tool_start_chunk(tool_id, tool_name, partial_args_dict)
                        self.active_tools[tool_id]["sent_start"] = True
                        self.active_tools[tool_id]["last_sent_args"] = partial_args_dict.copy()
                else:
                    # 更新部分参数
                    self.active_tools[tool_id]["partial_args"] = partial_args
                    # 尝试更新解析的参数
                    new_partial_dict = self._parse_partial_arguments(partial_args)
                    if new_partial_dict != self.active_tools[tool_id]["arguments"]:
                        self.active_tools[tool_id]["arguments"] = new_partial_dict

        except Exception as e:
            debug_log(f"📦 部分块解析失败: {e}")

    def _clean_arguments_string(self, arguments_raw: str) -> str:
        """
        清理和标准化参数字符串，改进对不完整JSON的处理
        """
        if not arguments_raw:
            return "{}"

        # 移除首尾空白
        cleaned = arguments_raw.strip()

        # 处理特殊值
        if cleaned.lower() == "null":
            return "{}"

        # 处理转义的JSON字符串
        if cleaned.startswith('{\\"') and cleaned.endswith('\\"}'):
            # 这是一个转义的JSON字符串，需要反转义
            cleaned = cleaned.replace('\\"', '"')
        elif cleaned.startswith('"{\\"') and cleaned.endswith('\\"}'):
            # 双重转义的情况
            cleaned = cleaned[1:-1].replace('\\"', '"')
        elif cleaned.startswith('"') and cleaned.endswith('"'):
            # 简单的引号包围，去除外层引号
            cleaned = cleaned[1:-1]

        # 处理不完整的JSON字符串
        cleaned = self._fix_incomplete_json(cleaned)

        # 标准化空格（移除JSON中的多余空格，但保留字符串值中的空格）
        try:
            # 先尝试解析，然后重新序列化以标准化格式
            parsed = json.loads(cleaned)
            if parsed is None:
                return "{}"
            cleaned = json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))
        except json.JSONDecodeError:
            # 如果解析失败，只做基本的空格清理
            debug_log(f"📦 JSON标准化失败，保持原样: {cleaned[:50]}...")

        return cleaned

    def _fix_incomplete_json(self, json_str: str) -> str:
        """
        修复不完整的JSON字符串
        """
        if not json_str:
            return "{}"

        # 确保以{开头
        if not json_str.startswith('{'):
            json_str = '{' + json_str

        # 处理不完整的字符串值
        if json_str.count('"') % 2 != 0:
            # 奇数个引号，可能有未闭合的字符串
            json_str += '"'

        # 确保以}结尾
        if not json_str.endswith('}'):
            json_str += '}'

        return json_str

    def _parse_partial_arguments(self, arguments_raw: str) -> Dict[str, Any]:
        """
        解析不完整的参数字符串，尽可能提取有效信息
        """
        if not arguments_raw or arguments_raw.strip() == "" or arguments_raw.strip().lower() == "null":
            return {}

        try:
            # 先尝试清理字符串
            cleaned = self._clean_arguments_string(arguments_raw)
            result = json.loads(cleaned)
            # 确保返回字典类型
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            pass

        try:
            # 尝试修复常见的JSON问题
            fixed_args = arguments_raw.strip()

            # 处理转义字符
            if '\\' in fixed_args:
                fixed_args = fixed_args.replace('\\"', '"')

            # 如果不是以{开头，添加{
            if not fixed_args.startswith('{'):
                fixed_args = '{' + fixed_args

            # 如果不是以}结尾，尝试添加}
            if not fixed_args.endswith('}'):
                # 计算未闭合的引号和括号
                quote_count = fixed_args.count('"') - fixed_args.count('\\"')
                if quote_count % 2 != 0:
                    fixed_args += '"'
                fixed_args += '}'

            return json.loads(fixed_args)
        except json.JSONDecodeError:
            # 尝试提取键值对
            return self._extract_key_value_pairs(arguments_raw)
        except Exception:
            # 如果所有方法都失败，返回空字典
            return {}

    def _extract_key_value_pairs(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取键值对，作为最后的解析尝试
        """
        result = {}
        try:
            # 使用正则表达式提取简单的键值对
            import re

            # 匹配 "key": "value" 或 "key": value 格式
            pattern = r'"([^"]+)":\s*"([^"]*)"'
            matches = re.findall(pattern, text)

            for key, value in matches:
                result[key] = value

            # 匹配数字值
            pattern = r'"([^"]+)":\s*(\d+)'
            matches = re.findall(pattern, text)

            for key, value in matches:
                try:
                    result[key] = int(value)
                except ValueError:
                    result[key] = value

            # 匹配布尔值
            pattern = r'"([^"]+)":\s*(true|false)'
            matches = re.findall(pattern, text)

            for key, value in matches:
                result[key] = value.lower() == 'true'

        except Exception:
            pass

        return result

    def _complete_active_tools(self, is_stream: bool) -> Generator[str, None, None]:
        """
        完成所有活跃的工具调用 - 处理待发送的工具
        """
        tools_to_send = []

        for tool_id, tool in self.active_tools.items():
            # 如果工具还没有发送过且参数看起来完整，现在发送
            if is_stream and tool.get("pending_send", False) and not tool.get("sent_start", False):
                if tool.get("args_complete", False):
                    debug_log(f"📤 完成时发送待发送工具: {tool['name']}(id={tool_id})")
                    yield self._create_tool_start_chunk(tool_id, tool["name"], tool["arguments"])
                    tool["sent_start"] = True
                    tool["pending_send"] = False
                    tools_to_send.append(tool)
                else:
                    debug_log(f"⚠️ 跳过不完整的工具: {tool['name']}(id={tool_id})")

            tool["status"] = "completed"
            self.completed_tools.append(tool)
            debug_log(f"✅ 完成工具调用: {tool['name']}(id={tool_id})")

        self.active_tools.clear()

        if is_stream and (self.completed_tools or tools_to_send):
            # 发送工具完成信号
            yield self._create_tool_finish_chunk()

    def process_other_phase(self, data: Dict[str, Any], is_stream: bool = True) -> Generator[str, None, None]:
        """
        处理other阶段 - 检测工具调用结束和状态更新
        """
        edit_content = data.get("edit_content", "")
        edit_index = data.get("edit_index", 0)
        usage = data.get("usage")

        # 保存usage信息
        if self.has_tool_call and usage:
            self.tool_call_usage = usage
            debug_log(f"💾 保存工具调用usage: {usage}")

        # 如果有edit_content，继续更新内容缓冲区
        if edit_content:
            self._apply_edit_to_buffer(edit_index, edit_content)
            # 继续处理可能的工具调用更新
            yield from self._process_tool_calls_from_buffer(is_stream)

        # 检测工具调用结束的多种标记
        if self.has_tool_call and self._is_tool_call_finished(edit_content):
            debug_log("🏁 检测到工具调用结束")

            # 完成所有活跃的工具
            yield from self._complete_active_tools(is_stream)

            if is_stream:
                debug_log("🏁 发送工具调用完成信号")
                yield "data: [DONE]"

            # 重置工具调用状态
            self.has_tool_call = False

    def _is_tool_call_finished(self, edit_content: str) -> bool:
        """
        检测工具调用是否结束的多种标记
        """
        if not edit_content:
            return False

        # 检测各种结束标记
        end_markers = [
            "null,",  # 原有的结束标记
            '"status": "completed"',  # 状态完成标记
            '"is_error": false',  # 错误状态标记
        ]

        for marker in end_markers:
            if marker in edit_content:
                debug_log(f"🔍 检测到结束标记: {marker}")
                return True

        # 检查是否所有工具都有完整的结构
        if self.active_tools and '"status": "completed"' in self.content_buffer:
            return True

        return False

    def _reset_all_state(self):
        """重置所有状态"""
        self.has_tool_call = False
        self.tool_call_usage = None
        self.content_index = 0
        self.content_buffer = bytearray()
        self.last_edit_index = 0
        self.active_tools.clear()
        self.completed_tools.clear()
        self.tool_blocks_cache.clear()

    def _create_tool_start_chunk(self, tool_id: str, tool_name: str, initial_args: Dict[str, Any] = None) -> str:
        """创建工具调用开始的chunk，支持初始参数"""
        # 使用提供的初始参数，如果没有则使用空字典
        args_dict = initial_args or {}
        args_str = json.dumps(args_dict, ensure_ascii=False)

        chunk = {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": args_str},
                            }
                        ],
                    },
                    "finish_reason": None,
                    "index": self.content_index,
                    "logprobs": None,
                }
            ],
            "created": int(time.time()),
            "id": self.chat_id,
            "model": self.model,
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_zai_001",
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _create_tool_arguments_chunk(self, tool_id: str, arguments: Dict) -> str:
        """创建工具参数的chunk - 只包含参数更新，不包含函数名"""
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "id": tool_id,
                                "function": {"arguments": json.dumps(arguments, ensure_ascii=False)},
                            }
                        ],
                    },
                    "finish_reason": None,
                    "index": self.content_index,
                    "logprobs": None,
                }
            ],
            "created": int(time.time()),
            "id": self.chat_id,
            "model": self.model,
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_zai_001",
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _create_tool_finish_chunk(self) -> str:
        """创建工具调用完成的chunk"""
        chunk = {
            "choices": [
                {
                    "delta": {"role": "assistant", "content": None, "tool_calls": []},
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                }
            ],
            "created": int(time.time()),
            "id": self.chat_id,
            "usage": self.tool_call_usage or None,
            "model": self.model,
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_zai_001",
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"