"""
OpenAI API endpoints
"""

import time
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import httpx

from app.core.config import settings
from app.models.schemas import OpenAIRequest, Message, ModelsResponse, Model
from app.utils.helpers import debug_log
from app.core.zai_transformer import ZAITransformer, generate_uuid
from app.utils.sse_tool_handler import SSEToolHandler

router = APIRouter()

# 全局转换器实例
transformer = ZAITransformer()


@router.get("/v1/models")
async def list_models():
    """List available models"""
    current_time = int(time.time())
    response = ModelsResponse(
        data=[
            Model(id=settings.PRIMARY_MODEL, created=current_time, owned_by="z.ai"),
            Model(id=settings.THINKING_MODEL, created=current_time, owned_by="z.ai"),
            Model(id=settings.SEARCH_MODEL, created=current_time, owned_by="z.ai"),
            Model(id=settings.AIR_MODEL, created=current_time, owned_by="z.ai"),
            Model(id=settings.GLM_46_MODEL, created=current_time, owned_by="z.ai"),
            Model(id=settings.GLM_46_THINKING_MODEL, created=current_time, owned_by="z.ai"),
        ]
    )
    return response


@router.post("/v1/chat/completions")
async def chat_completions(request: OpenAIRequest, authorization: str = Header(...)):
    """Handle chat completion requests with ZAI transformer"""
    role = request.messages[0].role if request.messages else "unknown"
    debug_log(f"😶‍🌫️ 收到 客户端 请求 - 模型: {request.model}, 流式: {request.stream}, 消息数: {len(request.messages)}, 角色: {role}, 工具数: {len(request.tools) if request.tools else 0}")
    
    try:
        # Validate API key (skip if SKIP_AUTH_TOKEN is enabled)
        if not settings.SKIP_AUTH_TOKEN:
            if not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
            
            api_key = authorization[7:]
            if api_key != settings.AUTH_TOKEN:
                raise HTTPException(status_code=401, detail="Invalid API key")
            
        # 使用新的转换器转换请求
        request_dict = request.model_dump()
        debug_log("🔄 开始转换请求格式: OpenAI -> Z.AI")
        
        transformed = await transformer.transform_request_in(request_dict)

        # 调用上游API
        async def stream_response():
            """流式响应生成器（包含重试机制）"""
            retry_count = 0
            last_error = None
            current_token = transformed.get("token", "")  # 获取当前使用的token

            while retry_count <= settings.MAX_RETRIES:
                try:
                    # 如果是重试，重新获取令牌并更新请求
                    if retry_count > 0:
                        delay = 2.0
                        debug_log(f"重试请求 ({retry_count}/{settings.MAX_RETRIES}) - 等待 {delay:.1f}s")
                        await asyncio.sleep(delay)

                        # 标记前一个token失败
                        if current_token:
                            transformer.mark_token_failure(current_token, Exception(f"Retry {retry_count}: {last_error}"))

                        # 重新获取令牌
                        debug_log("🔑 重新获取令牌用于重试...")
                        new_token = await transformer.get_token()
                        if not new_token:
                            debug_log("❌ 重试时无法获取有效的认证令牌")
                            raise Exception("重试时无法获取有效的认证令牌")
                        transformed["config"]["headers"]["Authorization"] = f"Bearer {new_token}"
                        current_token = new_token

                    async with httpx.AsyncClient(timeout=60.0) as client:
                        # 发送请求到上游
                        # debug_log(f"🎯 发送请求到 Z.AI: {transformed['config']['url']}")
                        async with client.stream(
                            "POST",
                            transformed["config"]["url"],
                            json=transformed["body"],
                            headers=transformed["config"]["headers"],
                        ) as response:
                            # 检查响应状态码
                            if response.status_code == 400:
                                # 400 错误，触发重试
                                error_text = await response.aread()
                                error_msg = error_text.decode('utf-8', errors='ignore')
                                debug_log(f"❌ 上游返回 400 错误 (尝试 {retry_count + 1}/{settings.MAX_RETRIES + 1})")
                                debug_log(f"上游错误响应: {error_msg}")

                                retry_count += 1
                                last_error = f"400 Bad Request: {error_msg}"

                                # 如果还有重试机会，继续循环
                                if retry_count <= settings.MAX_RETRIES:
                                    continue
                                else:
                                    # 达到最大重试次数，抛出错误
                                    debug_log(f"❌ 达到最大重试次数 ({settings.MAX_RETRIES})，请求失败")
                                    error_response = {
                                        "error": {
                                            "message": f"Request failed after {settings.MAX_RETRIES} retries: {last_error}",
                                            "type": "upstream_error",
                                            "code": 400
                                        }
                                    }
                                    yield f"data: {json.dumps(error_response)}\n\n"
                                    yield "data: [DONE]\n\n"
                                    return

                            elif response.status_code == 401:
                                # 认证错误，可能需要重新获取token
                                debug_log(f"❌ 认证失败 (401)，标记token失效")
                                if current_token:
                                    transformer.mark_token_failure(current_token, Exception("401 Unauthorized"))
                                
                                retry_count += 1
                                last_error = "401 Unauthorized - Token may be invalid"
                                
                                if retry_count <= settings.MAX_RETRIES:
                                    continue
                                else:
                                    error_response = {
                                        "error": {
                                            "message": "Authentication failed after retries",
                                            "type": "auth_error",
                                            "code": 401
                                        }
                                    }
                                    yield f"data: {json.dumps(error_response)}\n\n"
                                    yield "data: [DONE]\n\n"
                                    return
                            
                            elif response.status_code == 429:
                                # 速率限制，延长等待时间重试
                                debug_log(f"❌ 速率限制 (429)，将延长等待时间重试")
                                retry_count += 1
                                last_error = "429 Rate Limited"
                                
                                if retry_count <= settings.MAX_RETRIES:
                                    continue
                                else:
                                    error_response = {
                                        "error": {
                                            "message": "Rate limit exceeded",
                                            "type": "rate_limit_error", 
                                            "code": 429
                                        }
                                    }
                                    yield f"data: {json.dumps(error_response)}\n\n"
                                    yield "data: [DONE]\n\n"
                                    return
                            
                            elif response.status_code != 200:
                                # 其他错误，检查是否需要重试
                                error_text = await response.aread()
                                error_msg = error_text.decode('utf-8', errors='ignore')
                                debug_log(f"❌ 上游返回错误: {response.status_code}, 详情: {error_msg}")
                                
                                # 某些错误可以重试
                                retryable_codes = [502, 503, 504]
                                if response.status_code in retryable_codes and retry_count < settings.MAX_RETRIES:
                                    retry_count += 1
                                    last_error = f"{response.status_code}: {error_msg}"
                                    debug_log(f"⚠️ 服务器错误 {response.status_code}，准备重试")
                                    continue
                                
                                # 不可重试的错误或已达到重试上限
                                error_response = {
                                    "error": {
                                        "message": f"Upstream error: {response.status_code}",
                                        "type": "upstream_error",
                                        "code": response.status_code,
                                        "details": error_msg[:500]  # 限制错误详情长度
                                    }
                                }
                                yield f"data: {json.dumps(error_response)}\n\n"
                                yield "data: [DONE]\n\n"
                                return

                            # 200 成功，处理响应
                            debug_log(f"✅ Z.AI 响应成功，开始处理 SSE 流")
                            if retry_count > 0:
                                debug_log(f"✨ 第 {retry_count} 次重试成功")

                            # 标记token使用成功
                            if current_token:
                                transformer.mark_token_success(current_token)

                            # 初始化工具处理器（如果需要）
                            has_tools = transformed["body"].get("tools") is not None
                            has_mcp_servers = bool(transformed["body"].get("mcp_servers"))
                            tool_handler = None

                            # 如果有工具定义或MCP服务器，都需要工具处理器
                            if has_tools or has_mcp_servers:
                                chat_id = transformed["body"]["chat_id"]
                                model = request.model
                                tool_handler = SSEToolHandler(chat_id, model)

                                if has_tools and has_mcp_servers:
                                    debug_log(f"🔧 初始化工具处理器: {len(transformed['body'].get('tools', []))} 个OpenAI工具 + {len(transformed['body'].get('mcp_servers', []))} 个MCP服务器")
                                elif has_tools:
                                    debug_log(f"🔧 初始化工具处理器: {len(transformed['body'].get('tools', []))} 个OpenAI工具")
                                elif has_mcp_servers:
                                    debug_log(f"🔧 初始化工具处理器: {len(transformed['body'].get('mcp_servers', []))} 个MCP服务器")

                            # 处理状态
                            has_thinking = False
                            thinking_signature = None
                            first_thinking_chunk = True

                            # 处理SSE流 - 优化的buffer处理
                            buffer = bytearray()
                            incomplete_line = ""
                            line_count = 0
                            chunk_count = 0
                            last_activity = time.time()
                            debug_log("📡 开始接收 SSE 流数据...")

                            async for chunk in response.aiter_bytes():
                                chunk_count += 1
                                last_activity = time.time()
                                
                                if not chunk:
                                    continue

                                # 将新数据添加到buffer
                                buffer.extend(chunk)
                                
                                # 尝试解码并处理完整的行
                                try:
                                    # 解码为字符串并处理
                                    text_data = buffer.decode('utf-8')
                                    
                                    # 分割为行
                                    lines = text_data.split('\n')
                                    
                                    # 最后一行可能不完整，保存到incomplete_line
                                    if not text_data.endswith('\n'):
                                        incomplete_line = lines[-1]
                                        lines = lines[:-1]
                                    else:
                                        # 如果有未完成的行，将其与第一行合并
                                        if incomplete_line:
                                            lines[0] = incomplete_line + lines[0]
                                            incomplete_line = ""
                                    
                                    # 清空buffer，开始处理新的数据
                                    buffer = bytearray()
                                    if incomplete_line:
                                        buffer.extend(incomplete_line.encode('utf-8'))
                                    
                                    # 处理完整的行
                                    for current_line in lines:
                                        line_count += 1
                                        if not current_line.strip():
                                            continue

                                        if current_line.startswith("data:"):
                                            chunk_str = current_line[5:].strip()
                                            if not chunk_str or chunk_str == "[DONE]":
                                                if chunk_str == "[DONE]":
                                                    debug_log("📡 收到 [DONE] 信号")
                                                    yield "data: [DONE]\n\n"
                                                continue

                                            # debug_log(f"📦 解析数据块: {chunk_str[:200]}..." if len(chunk_str) > 200 else f"📦 解析数据块: {chunk_str}")

                                            try:
                                                chunk = json.loads(chunk_str)

                                                if chunk.get("type") == "chat:completion":
                                                    data = chunk.get("data", {})
                                                    phase = data.get("phase")

                                                    # 记录每个阶段（只在阶段变化时记录）
                                                    if phase and phase != getattr(stream_response, '_last_phase', None):
                                                        debug_log(f"📈 SSE 阶段: {phase}")
                                                        stream_response._last_phase = phase

                                                    # 处理工具调用
                                                    if phase == "tool_call" and tool_handler:
                                                        for output in tool_handler.process_tool_call_phase(data, True):
                                                            yield output

                                                    # 处理其他阶段（工具结束）
                                                    elif phase == "other" and tool_handler:
                                                        for output in tool_handler.process_other_phase(data, True):
                                                            yield output

                                                    # 处理思考内容
                                                    elif phase == "thinking":
                                                        if not has_thinking:
                                                            has_thinking = True
                                                            # 发送初始角色
                                                            role_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {"role": "assistant"},
                                                                        "finish_reason": None,
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            yield f"data: {json.dumps(role_chunk)}\n\n"

                                                        delta_content = data.get("delta_content", "")
                                                        if delta_content:
                                                            # 处理思考内容格式
                                                            if delta_content.startswith("<details"):
                                                                content = (
                                                                    delta_content.split("</summary>\n>")[-1].strip()
                                                                    if "</summary>\n>" in delta_content
                                                                    else delta_content
                                                                )
                                                            else:
                                                                content = delta_content
                                                            
                                                            # 第一个思考块添加<think>开始标签，其他块保持纯内容
                                                            if first_thinking_chunk:
                                                                formatted_content = f"<think>{content}"
                                                                first_thinking_chunk = False
                                                            else:
                                                                formatted_content = content

                                                            thinking_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {
                                                                            "role": "assistant",
                                                                            "content": formatted_content,
                                                                        },
                                                                        "finish_reason": None,
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            yield f"data: {json.dumps(thinking_chunk)}\n\n"

                                                    # 处理答案内容
                                                    elif phase == "answer":
                                                        edit_content = data.get("edit_content", "")
                                                        delta_content = data.get("delta_content", "")

                                                        # 如果还没有发送角色，先发送角色chunk
                                                        if not has_thinking:
                                                            has_thinking = True  # 设置标志避免重复发送
                                                            role_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {"role": "assistant"},
                                                                        "finish_reason": None,
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            debug_log("➡️ 发送初始角色chunk")
                                                            yield f"data: {json.dumps(role_chunk)}\n\n"

                                                        # 处理思考结束和答案开始
                                                        if edit_content and "</details>\n" in edit_content:
                                                            if has_thinking and not first_thinking_chunk:
                                                                # 发送思考结束标记</think>
                                                                thinking_signature = str(int(time.time() * 1000))
                                                                sig_chunk = {
                                                                    "choices": [
                                                                        {
                                                                            "delta": {
                                                                                "role": "assistant",
                                                                                "content": "</think>",
                                                                            },
                                                                            "finish_reason": None,
                                                                            "index": 0,
                                                                            "logprobs": None,
                                                                        }
                                                                    ],
                                                                    "created": int(time.time()),
                                                                    "id": transformed["body"]["chat_id"],
                                                                    "model": request.model,
                                                                    "object": "chat.completion.chunk",
                                                                    "system_fingerprint": "fp_zai_001",
                                                                }
                                                                yield f"data: {json.dumps(sig_chunk)}\n\n"

                                                            # 提取答案内容
                                                            content_after = edit_content.split("</details>\n")[-1]
                                                            if content_after:
                                                                content_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {
                                                                            "role": "assistant",
                                                                            "content": content_after,
                                                                        },
                                                                        "finish_reason": None,
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            yield f"data: {json.dumps(content_chunk)}\n\n"

                                                        # 处理增量内容
                                                        elif delta_content:
                                                            # 如果还没有发送角色
                                                            if not has_thinking:
                                                                has_thinking = True  # 避免重复发送
                                                                role_chunk = {
                                                                    "choices": [
                                                                        {
                                                                            "delta": {"role": "assistant"},
                                                                            "finish_reason": None,
                                                                            "index": 0,
                                                                            "logprobs": None,
                                                                        }
                                                                    ],
                                                                    "created": int(time.time()),
                                                                    "id": transformed["body"]["chat_id"],
                                                                    "model": request.model,
                                                                    "object": "chat.completion.chunk",
                                                                    "system_fingerprint": "fp_zai_001",
                                                                }
                                                                debug_log("➡️ 发送初始角色chunk")
                                                                yield f"data: {json.dumps(role_chunk)}\n\n"

                                                            content_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {
                                                                            "content": delta_content,
                                                                        },
                                                                        "finish_reason": None,
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            output_data = f"data: {json.dumps(content_chunk)}\n\n"
                                                            # debug_log(f"➡️ 输出内容块到客户端: {delta_content[:50]}...")
                                                            yield output_data

                                                    # 处理完成 - 当收到usage信息时
                                                    if data.get("usage"):
                                                        debug_log(f"📦 完成响应 - 使用统计: {json.dumps(data['usage'])}")

                                                        # 只有在非工具调用模式下才发送普通完成信号
                                                        if not tool_handler or not tool_handler.has_tool_call:
                                                            finish_chunk = {
                                                                "choices": [
                                                                    {
                                                                        "delta": {},  # 空的delta表示结束
                                                                        "finish_reason": "stop",
                                                                        "index": 0,
                                                                        "logprobs": None,
                                                                    }
                                                                ],
                                                                "usage": data["usage"],
                                                                "created": int(time.time()),
                                                                "id": transformed["body"]["chat_id"],
                                                                "model": request.model,
                                                                "object": "chat.completion.chunk",
                                                                "system_fingerprint": "fp_zai_001",
                                                            }
                                                            finish_output = f"data: {json.dumps(finish_chunk)}\n\n"
                                                            debug_log("➡️ 发送完成信号")
                                                            yield finish_output
                                                            debug_log("➡️ 发送 [DONE]")
                                                            yield "data: [DONE]\n\n"

                                            except json.JSONDecodeError as e:
                                                debug_log(f"❌ JSON解析错误: {e}, 内容: {chunk_str[:200]}")
                                            except Exception as e:
                                                debug_log(f"❌ 处理chunk错误: {e}")
                                
                                except UnicodeDecodeError:
                                    # 如果解码失败，可能是数据不完整，继续接收
                                    debug_log(f"⚠️ 数据解码失败，缓冲区大小: {len(buffer)}")
                                    if len(buffer) > 1024 * 1024:  # 1MB限制
                                        debug_log("❌ 缓冲区过大，清空重试")
                                        buffer = bytearray()
                                        incomplete_line = ""
                                except Exception as e:
                                    debug_log(f"❌ Buffer处理异常: {e}")
                                    # 清空buffer继续处理
                                    buffer = bytearray()
                                    incomplete_line = ""
                                
                                # 检查是否长时间没有活动（超时检查）
                                if time.time() - last_activity > 30:  # 30秒超时
                                    debug_log("⚠️ 检测到长时间无活动，可能连接中断")
                                    break

                            # 确保发送结束信号
                            if not tool_handler or not tool_handler.has_tool_call:
                                debug_log("📤 发送最终 [DONE] 信号")
                                yield "data: [DONE]\n\n"

                            debug_log(f"✅ SSE 流处理完成，共处理 {line_count} 行数据，{chunk_count} 个数据块")
                            
                            # 检查处理完整性
                            is_complete = True
                            completion_issues = []
                            
                            if line_count == 0:
                                is_complete = False
                                completion_issues.append("没有处理任何数据行")
                            elif chunk_count == 0:
                                is_complete = False
                                completion_issues.append("没有收到任何数据块")
                            elif chunk_count > 0:
                                debug_log(f"📊 平均每个数据块包含 {line_count/chunk_count:.1f} 行")
                            
                            # 检查工具调用完整性
                            if tool_handler and tool_handler.has_tool_call:
                                if not tool_handler.completed_tools:
                                    completion_issues.append("工具调用未正常完成")
                                else:
                                    debug_log(f"✅ 工具调用完成: {len(tool_handler.completed_tools)} 个工具")
                            
                            # 检查思考内容完整性（只有真正的thinking模式才需要签名）
                            # 注意：普通的answer阶段不需要thinking签名，只有thinking阶段才需要
                            # if has_thinking and not thinking_signature:
                            #     completion_issues.append("思考内容缺少签名")
                            
                            # 报告完整性状态
                            if is_complete and not completion_issues:
                                debug_log("✅ 响应完整性检查通过")
                            else:
                                debug_log(f"⚠️ 响应完整性问题: {', '.join(completion_issues)}")
                                
                                # 如果问题严重且还有重试机会，考虑重试
                                critical_issues = ["没有处理任何数据行", "没有收到任何数据块"]
                                has_critical_issue = any(issue in completion_issues for issue in critical_issues)
                                
                                if has_critical_issue and retry_count < settings.MAX_RETRIES:
                                    debug_log("🔄 检测到严重完整性问题，准备重试")
                                    retry_count += 1
                                    last_error = f"Incomplete response: {', '.join(completion_issues)}"
                                    continue
                            
                            # 成功处理完成，退出重试循环
                            return

                except Exception as e:
                    debug_log(f"❌ 流处理错误: {e}")
                    import traceback
                    debug_log(traceback.format_exc())

                    # 标记token失败
                    if current_token:
                        transformer.mark_token_failure(current_token, e)

                    # 检查是否还可以重试
                    retry_count += 1
                    last_error = str(e)

                    if retry_count > settings.MAX_RETRIES:
                        # 达到最大重试次数，返回错误
                        debug_log(f"❌ 达到最大重试次数 ({settings.MAX_RETRIES})，流处理失败")
                        error_response = {
                            "error": {
                                "message": f"Stream processing failed after {settings.MAX_RETRIES} retries: {last_error}",
                                "type": "stream_error"
                            }
                        }
                        yield f"data: {json.dumps(error_response)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

        # 返回流式响应
        debug_log("🚀 启动 SSE 流式响应")
        
        # 创建一个包装的生成器来追踪数据流
        async def logged_stream():
            chunk_count = 0
            try:
                debug_log("📤 开始向客户端流式传输数据...")
                async for chunk in stream_response():
                    chunk_count += 1
                    # debug_log(f"📤 发送块[{chunk_count}]: {chunk[:200]}..." if len(chunk) > 200 else f"  📤 发送块[{chunk_count}]: {chunk}")
                    yield chunk
                debug_log(f"✅ 流式传输完成，共发送 {chunk_count} 个数据块")
            except Exception as e:
                debug_log(f"❌ 流式传输中断: {e}")
                raise
        
        return StreamingResponse(
            logged_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"❌ 处理请求时发生错误: {str(e)}")
        import traceback

        debug_log(f"❌ 错误堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")