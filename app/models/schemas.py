"""
Application data models
"""

from typing import Dict, List, Optional, Any, Union, Literal
from pydantic import BaseModel


class ContentPart(BaseModel):
    """Content part model for OpenAI's new content format"""

    type: str
    text: Optional[str] = None


class Message(BaseModel):
    """Chat message model"""

    role: str
    content: Optional[Union[str, List[ContentPart]]] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class OpenAIRequest(BaseModel):
    """OpenAI-compatible request model"""

    model: str
    messages: List[Message]
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None


class ModelItem(BaseModel):
    """Model information item"""

    id: str
    name: str
    owned_by: str


class UpstreamRequest(BaseModel):
    """Upstream service request model"""

    stream: bool
    model: str
    messages: List[Message]
    params: Dict[str, Any] = {}
    features: Dict[str, Any] = {}
    background_tasks: Optional[Dict[str, bool]] = None
    chat_id: Optional[str] = None
    id: Optional[str] = None
    mcp_servers: Optional[List[str]] = None
    model_item: Optional[ModelItem] = None
    tool_servers: Optional[List[str]] = None
    variables: Optional[Dict[str, str]] = None
    model_config = {"protected_namespaces": ()}


class Delta(BaseModel):
    """Stream delta model"""

    role: Optional[str] = None
    content: Optional[str] = "" or None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class Choice(BaseModel):
    """Response choice model"""

    index: int
    message: Optional[Message] = None
    delta: Optional[Delta] = None
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    """Token usage statistics"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIResponse(BaseModel):
    """OpenAI-compatible response model"""

    id: str
    object: str
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None


class UpstreamError(BaseModel):
    """Upstream error model"""

    detail: str
    code: int


class UpstreamDataInner(BaseModel):
    """Inner upstream data model"""

    error: Optional[UpstreamError] = None


class UpstreamDataData(BaseModel):
    """Upstream data content model"""

    delta_content: str = ""
    edit_content: str = ""
    phase: str = ""
    done: bool = False
    usage: Optional[Usage] = None
    error: Optional[UpstreamError] = None
    inner: Optional[UpstreamDataInner] = None


class UpstreamData(BaseModel):
    """Upstream data model"""

    type: str
    data: UpstreamDataData
    error: Optional[UpstreamError] = None


class Model(BaseModel):
    """Model information for listing"""

    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    """Models list response model"""

    object: str = "list"
    data: List[Model]
