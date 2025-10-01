"""
Response handlers for streaming and non-streaming responses
"""

import json
import time
from typing import Generator, Optional
import requests
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import settings
from app.models.schemas import (
    Message, Delta, Choice, Usage, OpenAIResponse, 
    UpstreamRequest, UpstreamData, UpstreamError, ModelItem
)
from app.utils.helpers import debug_log, call_upstream_api, transform_thinking_content
from app.core.token_manager import token_manager
from app.utils.sse_parser import SSEParser
from app.utils.tools import extract_tool_invocations, remove_tool_json_content
from app.utils.sse_tool_handler import SSEToolHandler


def create_openai_response_chunk(
    model: str,
    delta: Optional[Delta] = None,
    finish_reason: Optional[str] = None
) -> OpenAIResponse:
    """Create OpenAI response chunk for streaming"""
    return OpenAIResponse(
        id=f"chatcmpl-{int(time.time())}",
        object="chat.completion.chunk",
        created=int(time.time()),
        model=model,
        choices=[Choice(
            index=0,
            delta=delta or Delta(),
            finish_reason=finish_reason
        )]
    )


def handle_upstream_error(error: UpstreamError) -> Generator[str, None, None]:
    """Handle upstream error response"""
    debug_log(f"上游错误: code={error.code}, detail={error.detail}")
    
    # Send end chunk
    end_chunk = create_openai_response_chunk(
        model=settings.PRIMARY_MODEL,
        finish_reason="stop"
    )
    yield f"data: {end_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


class ResponseHandler:
    """Base class for response handling"""
    
    def __init__(self, upstream_req: UpstreamRequest, chat_id: str, auth_token: str):
        self.upstream_req = upstream_req
        self.chat_id = chat_id
        self.auth_token = auth_token
    
    def _call_upstream(self) -> requests.Response:
        """Call upstream API with error handling"""
        max_retries = settings.MAX_RETRIES
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                debug_log(f"尝试调用上游API (第 {retry_count + 1}/{max_retries} 次)")
                response = call_upstream_api(self.upstream_req, self.chat_id, self.auth_token)
                
                # Check if response is successful
                if response.status_code == 200:
                    # Mark token as successful
                    token_manager.mark_token_success(self.auth_token)
                    debug_log("上游API调用成功")
                    return response
                elif response.status_code in [401, 403]:
                    # Authentication/authorization error - mark token as failed
                    debug_log(f"Token认证失败 (状态码: {response.status_code}): {self.auth_token[:20]}...")
                    token_manager.mark_token_failed(self.auth_token)
                    
                    # Try to get a new token
                    new_token = token_manager.get_next_token()
                    if new_token and new_token != self.auth_token:
                        debug_log(f"尝试使用新token: {new_token[:20]}...")
                        self.auth_token = new_token
                        retry_count += 1
                        continue
                    else:
                        debug_log("没有更多可用token")
                        return response
                elif response.status_code in [429]:
                    # Rate limit - don't mark token as failed, just retry
                    debug_log(f"遇到速率限制 (状态码: {response.status_code})，等待后重试")
                    if retry_count < max_retries - 1:
                        import time
                        time.sleep(2 ** retry_count)  # 指数退避
                        retry_count += 1
                        continue
                    else:
                        return response
                elif response.status_code >= 500:
                    # Server error - retry without marking token as failed
                    debug_log(f"服务器错误 (状态码: {response.status_code})，稍后重试")
                    if retry_count < max_retries - 1:
                        import time
                        time.sleep(1)
                        retry_count += 1
                        continue
                    else:
                        return response
                else:
                    # Other client errors, return response as-is
                    debug_log(f"客户端错误 (状态码: {response.status_code})")
                    return response
                    
            except Exception as e:
                error_msg = str(e)
                debug_log(f"调用上游失败 (尝试 {retry_count + 1}/{max_retries}): {error_msg}")
                
                # 判断是否是连接问题还是token问题
                is_connection_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'timeout', 'network', 'dns', 'socket', 'ssl'
                ])
                
                if is_connection_error:
                    debug_log("检测到网络连接问题，不标记token失败")
                    # 网络问题不标记token失败，直接重试
                    if retry_count < max_retries - 1:
                        import time
                        time.sleep(2)  # 等待2秒后重试
                        retry_count += 1
                        continue
                    else:
                        raise Exception(f"网络连接问题，重试{max_retries}次后仍失败: {error_msg}")
                else:
                    # 其他错误可能是token问题，标记失败并尝试新token
                    debug_log("检测到可能的token问题，标记token失败")
                    token_manager.mark_token_failed(self.auth_token)
                    
                    # Try to get a new token
                    new_token = token_manager.get_next_token()
                    if new_token and new_token != self.auth_token and retry_count < max_retries - 1:
                        debug_log(f"尝试使用新token: {new_token[:20]}...")
                        self.auth_token = new_token
                        retry_count += 1
                        continue
                    else:
                        raise
        
        # If we get here, all retries failed
        raise Exception("所有重试尝试均失败")
    
    def _handle_upstream_error(self, response: requests.Response) -> None:
        """Handle upstream error response"""
        debug_log(f"上游返回错误状态: {response.status_code}")
        if settings.DEBUG_LOGGING:
            debug_log(f"上游错误响应: {response.text}")


class StreamResponseHandler(ResponseHandler):
    """Handler for streaming responses"""
    
    def __init__(self, upstream_req: UpstreamRequest, chat_id: str, auth_token: str, has_tools: bool = False):
        super().__init__(upstream_req, chat_id, auth_token)
        self.has_tools = has_tools
        self.buffered_content = ""
        self.tool_calls = None
        # Initialize SSE tool handler for improved tool processing
        self.tool_handler = SSEToolHandler(chat_id, settings.PRIMARY_MODEL) if has_tools else None
        # 思考状态跟踪
        self.first_thinking_chunk = True
    
    def handle(self) -> Generator[str, None, None]:
        """Handle streaming response"""
        debug_log(f"开始处理流式响应 (chat_id={self.chat_id})")
        
        try:
            response = self._call_upstream()
        except Exception:
            yield "data: {\"error\": \"Failed to call upstream\"}\n\n"
            return
        
        if response.status_code != 200:
            self._handle_upstream_error(response)
            yield "data: {\"error\": \"Upstream error\"}\n\n"
            return
        
        # Send initial role chunk
        first_chunk = create_openai_response_chunk(
            model=settings.PRIMARY_MODEL,
            delta=Delta(role="assistant")
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"
        
        # Process stream
        debug_log("开始读取上游SSE流")
        sent_initial_answer = False
        stream_ended_normally = False
        
        try:
            with SSEParser(response, debug_mode=settings.DEBUG_LOGGING) as parser:
                for event in parser.iter_json_data(UpstreamData):
                    upstream_data = event['data']
                    
                    # Check for errors
                    if self._has_error(upstream_data):
                        error = self._get_error(upstream_data)
                        yield from handle_upstream_error(error)
                        stream_ended_normally = True
                        break
                    
                    debug_log(f"解析成功 - 类型: {upstream_data.type}, 阶段: {upstream_data.data.phase}, "
                             f"内容长度: {len(upstream_data.data.delta_content or '')}, 完成: {upstream_data.data.done}")
                    
                    # Process content
                    yield from self._process_content_with_tools(upstream_data, sent_initial_answer)
                    
                    # Update sent_initial_answer flag if we sent content
                    if not sent_initial_answer and (upstream_data.data.delta_content or upstream_data.data.edit_content):
                        sent_initial_answer = True
                    
                    # Check if done
                    if upstream_data.data.done or upstream_data.data.phase == "done":
                        debug_log("检测到流结束信号")
                        yield from self._send_end_chunk()
                        stream_ended_normally = True
                        break
                        
        except Exception as e:
            debug_log(f"SSE流处理异常: {e}")
            # 流异常结束，发送错误响应
            if not stream_ended_normally:
                error_chunk = create_openai_response_chunk(
                    model=settings.PRIMARY_MODEL,
                    delta=Delta(content=f"\n\n[系统提示: 连接中断，响应可能不完整]")
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
        
        # 确保流正常结束
        if not stream_ended_normally:
            debug_log("流未正常结束，发送结束信号")
            yield from self._send_end_chunk(force_stop=True)
    
    def _has_error(self, upstream_data: UpstreamData) -> bool:
        """Check if upstream data contains error"""
        return bool(
            upstream_data.error or 
            upstream_data.data.error or 
            (upstream_data.data.inner and upstream_data.data.inner.error)
        )
    
    def _get_error(self, upstream_data: UpstreamData) -> UpstreamError:
        """Get error from upstream data"""
        return (
            upstream_data.error or 
            upstream_data.data.error or 
            (upstream_data.data.inner.error if upstream_data.data.inner else None)
        )
    
    def _process_content(
        self, 
        upstream_data: UpstreamData, 
        sent_initial_answer: bool
    ) -> Generator[str, None, None]:
        """Process content from upstream data"""
        content = upstream_data.data.delta_content or upstream_data.data.edit_content
        
        if not content:
            return
        
        # Transform thinking content
        if upstream_data.data.phase == "thinking":
            content = transform_thinking_content(content)
        
        # Buffer content if tools are enabled
        if self.has_tools:
            self.buffered_content += content
        else:
            # Handle initial answer content
            if (not sent_initial_answer and 
                upstream_data.data.edit_content and 
                upstream_data.data.phase == "answer"):
                
                content = self._extract_edit_content(upstream_data.data.edit_content)
                if content:
                    debug_log(f"发送普通内容: {content}")
                    chunk = create_openai_response_chunk(
                        model=settings.PRIMARY_MODEL,
                        delta=Delta(content=content)
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    sent_initial_answer = True
            
            # Handle delta content
            if upstream_data.data.delta_content:
                if content:
                    if upstream_data.data.phase == "thinking":
                        # 第一个思考块添加<think>开始标签，其他块保持纯内容
                        if self.first_thinking_chunk:
                            formatted_content = f"<think>{content}"
                            self.first_thinking_chunk = False
                        else:
                            formatted_content = content
                        
                        debug_log(f"发送思考内容: {content}")
                        chunk = create_openai_response_chunk(
                            model=settings.PRIMARY_MODEL,
                            delta=Delta(content=formatted_content)
                        )
                    else:
                        # 如果从thinking阶段转到其他阶段，需要结束thinking标签
                        if not self.first_thinking_chunk and upstream_data.data.phase == "answer":
                            # 先发送思考结束标签
                            thinking_end_chunk = create_openai_response_chunk(
                                model=settings.PRIMARY_MODEL,
                                delta=Delta(content="</think>")
                            )
                            yield f"data: {thinking_end_chunk.model_dump_json()}\n\n"
                            # 重置状态
                            self.first_thinking_chunk = True
                        
                        debug_log(f"发送普通内容: {content}")
                        chunk = create_openai_response_chunk(
                            model=settings.PRIMARY_MODEL,
                            delta=Delta(content=content)
                        )
                    yield f"data: {chunk.model_dump_json()}\n\n"
    
    def _extract_edit_content(self, edit_content: str) -> str:
        """Extract content from edit_content field"""
        parts = edit_content.split("</details>")
        return parts[1] if len(parts) > 1 else ""
    
    def _send_end_chunk(self, force_stop: bool = False) -> Generator[str, None, None]:
        """Send end chunk and DONE signal"""
        finish_reason = "stop"
        
        if self.has_tools and not force_stop:
            # Try to extract tool calls from buffered content
            self.tool_calls = extract_tool_invocations(self.buffered_content)
            
            if self.tool_calls:
                debug_log(f"检测到工具调用: {len(self.tool_calls)} 个")
                # Send tool calls with proper format
                for i, tc in enumerate(self.tool_calls):
                    tool_call_delta = {
                        "index": i,
                        "id": tc.get("id"),
                        "type": tc.get("type", "function"),
                        "function": tc.get("function", {}),
                    }
                    
                    out_chunk = create_openai_response_chunk(
                        model=settings.PRIMARY_MODEL,
                        delta=Delta(tool_calls=[tool_call_delta])
                    )
                    yield f"data: {out_chunk.model_dump_json()}\n\n"
                
                finish_reason = "tool_calls"
            else:
                # Send regular content
                trimmed_content = remove_tool_json_content(self.buffered_content)
                if trimmed_content:
                    debug_log(f"发送常规内容: {len(trimmed_content)} 字符")
                    content_chunk = create_openai_response_chunk(
                        model=settings.PRIMARY_MODEL,
                        delta=Delta(content=trimmed_content)
                    )
                    yield f"data: {content_chunk.model_dump_json()}\n\n"
        elif force_stop:
            # 强制结束时，发送缓冲的内容（如果有）
            if self.buffered_content:
                debug_log(f"强制结束，发送缓冲内容: {len(self.buffered_content)} 字符")
                content_chunk = create_openai_response_chunk(
                    model=settings.PRIMARY_MODEL,
                    delta=Delta(content=self.buffered_content)
                )
                yield f"data: {content_chunk.model_dump_json()}\n\n"
        
        # Send final chunk
        end_chunk = create_openai_response_chunk(
            model=settings.PRIMARY_MODEL,
            finish_reason=finish_reason
        )
        yield f"data: {end_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"
        debug_log(f"流式响应完成 (finish_reason: {finish_reason})")


    
    def _process_content_with_tools(
        self, 
        upstream_data: UpstreamData, 
        sent_initial_answer: bool
    ) -> Generator[str, None, None]:
        """Process content with improved tool handling"""
        # Handle tool calls with improved SSE tool handler
        if self.has_tools and self.tool_handler:
            # Check if this is a tool_call phase
            if upstream_data.data.phase == "tool_call":
                # Use the improved tool handler for tool call processing
                yield from self.tool_handler.process_tool_call_phase(
                    upstream_data.data.model_dump(), 
                    is_stream=True
                )
                return
            elif upstream_data.data.phase == "other":
                # Handle other phase which may contain tool completion signals
                yield from self.tool_handler.process_other_phase(
                    upstream_data.data.model_dump(), 
                    is_stream=True
                )
                return
        
        # Fall back to original content processing
        yield from self._process_content(upstream_data, sent_initial_answer)


class NonStreamResponseHandler(ResponseHandler):
    """Handler for non-streaming responses"""
    
    def __init__(self, upstream_req: UpstreamRequest, chat_id: str, auth_token: str, has_tools: bool = False):
        super().__init__(upstream_req, chat_id, auth_token)
        self.has_tools = has_tools
        # 思考状态跟踪
        self.first_thinking_chunk = True
        self.in_thinking_phase = False
    
    def handle(self) -> JSONResponse:
        """Handle non-streaming response"""
        debug_log(f"开始处理非流式响应 (chat_id={self.chat_id})")
        
        try:
            response = self._call_upstream()
        except Exception as e:
            debug_log(f"调用上游失败: {e}")
            raise HTTPException(status_code=502, detail="Failed to call upstream")
        
        if response.status_code != 200:
            self._handle_upstream_error(response)
            raise HTTPException(status_code=502, detail="Upstream error")
        
        # Collect full response
        full_content = []
        debug_log("开始收集完整响应内容")
        response_completed = False
        
        try:
            with SSEParser(response, debug_mode=settings.DEBUG_LOGGING) as parser:
                for event in parser.iter_json_data(UpstreamData):
                    upstream_data = event['data']
                    
                    if upstream_data.data.delta_content:
                        content = upstream_data.data.delta_content
                        
                        if upstream_data.data.phase == "thinking":
                            content = transform_thinking_content(content)
                            
                            # 处理思考内容的分块格式
                            if not self.in_thinking_phase:
                                # 进入思考阶段，添加开始标签
                                self.in_thinking_phase = True
                                if self.first_thinking_chunk:
                                    content = f"<think>{content}"
                                    self.first_thinking_chunk = False
                                else:
                                    content = f"<think>{content}"
                            # 如果已经在思考阶段，保持纯内容
                        else:
                            # 如果从thinking阶段转到其他阶段
                            if self.in_thinking_phase:
                                # 添加结束标签到前一个内容
                                if full_content and not self.first_thinking_chunk:
                                    full_content.append("</think>")
                                self.in_thinking_phase = False
                                self.first_thinking_chunk = True
                        
                        if content:
                            full_content.append(content)
                    
                    if upstream_data.data.done or upstream_data.data.phase == "done":
                        debug_log("检测到完成信号，停止收集")
                        response_completed = True
                        break
                        
        except Exception as e:
            debug_log(f"非流式响应收集异常: {e}")
            if not full_content:
                # 如果没有收集到任何内容，抛出异常
                raise HTTPException(status_code=502, detail=f"Response collection failed: {str(e)}")
            else:
                debug_log(f"部分内容收集成功，继续处理 ({len(full_content)} 个片段)")
        
        if not response_completed and not full_content:
            debug_log("响应未完成且无内容，可能是连接问题")
            raise HTTPException(status_code=502, detail="Incomplete response from upstream")
        
        # 如果响应结束时还在思考阶段，需要添加结束标签
        if self.in_thinking_phase and not self.first_thinking_chunk:
            full_content.append("</think>")
        
        final_content = "".join(full_content)
        debug_log(f"内容收集完成，最终长度: {len(final_content)}")
        
        # Handle tool calls for non-streaming
        tool_calls = None
        finish_reason = "stop"
        message_content = final_content
        
        if self.has_tools:
            tool_calls = extract_tool_invocations(final_content)
            if tool_calls:
                # Content must be null when tool_calls are present (OpenAI spec)
                message_content = None
                finish_reason = "tool_calls"
                debug_log(f"提取到工具调用: {json.dumps(tool_calls, ensure_ascii=False)}")
            else:
                # Remove tool JSON from content
                message_content = remove_tool_json_content(final_content)
                if not message_content:
                    message_content = final_content  # 保留原内容如果清理后为空
        
        # Build response
        response_data = OpenAIResponse(
            id=f"chatcmpl-{int(time.time())}",
            object="chat.completion",
            created=int(time.time()),
            model=settings.PRIMARY_MODEL,
            choices=[Choice(
                index=0,
                message=Message(
                    role="assistant",
                    content=message_content,
                    tool_calls=tool_calls
                ),
                finish_reason=finish_reason
            )],
            usage=Usage()
        )
        
        debug_log("非流式响应发送完成")
        return JSONResponse(content=response_data.model_dump(exclude_none=True))