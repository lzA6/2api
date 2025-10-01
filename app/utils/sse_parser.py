"""
SSE (Server-Sent Events) parser for streaming responses
"""

import json
from typing import Dict, Any, Generator, Optional, Type
import requests


class SSEParser:
    """Server-Sent Events parser for streaming responses"""

    def __init__(self, response: requests.Response, debug_mode: bool = False):
        """Initialize SSE parser

        Args:
            response: requests.Response object with stream=True
            debug_mode: Enable debug logging
        """
        self.response = response
        self.debug_mode = debug_mode
        self.buffer = ""
        self.line_count = 0

    def debug_log(self, format_str: str, *args) -> None:
        """Log debug message if debug mode is enabled"""
        if self.debug_mode:
            if args:
                print(f"[SSE_PARSER] {format_str % args}")
            else:
                print(f"[SSE_PARSER] {format_str}")

    def iter_events(self) -> Generator[Dict[str, Any], None, None]:
        """Iterate over SSE events

        Yields:
            dict: Parsed SSE event data
        """
        self.debug_log("开始解析 SSE 流")

        for line in self.response.iter_lines():
            self.line_count += 1

            # Skip empty lines
            if not line:
                continue

            # Decode bytes
            if isinstance(line, bytes):
                try:
                    line = line.decode("utf-8")
                except UnicodeDecodeError:
                    self.debug_log(f"第{self.line_count}行解码失败，跳过")
                    continue

            # Skip comment lines
            if line.startswith(":"):
                continue

            # Parse field-value pairs
            if ":" in line:
                field, value = line.split(":", 1)
                field = field.strip()
                value = value.lstrip()

                if field == "data":
                    self.debug_log(f"收到数据 (第{self.line_count}行): {value}")

                    # Try to parse JSON
                    try:
                        data = json.loads(value)
                        yield {"type": "data", "data": data, "raw": value}
                    except json.JSONDecodeError:
                        yield {"type": "data", "data": value, "raw": value, "is_json": False}

                elif field == "event":
                    yield {"type": "event", "event": value}

                elif field == "id":
                    yield {"type": "id", "id": value}

                elif field == "retry":
                    try:
                        retry = int(value)
                        yield {"type": "retry", "retry": retry}
                    except ValueError:
                        self.debug_log(f"无效的 retry 值: {value}")

    def iter_data_only(self) -> Generator[Dict[str, Any], None, None]:
        """Iterate only over data events"""
        for event in self.iter_events():
            if event["type"] == "data":
                yield event

    def iter_json_data(self, model_class: Optional[Type] = None) -> Generator[Dict[str, Any], None, None]:
        """Iterate only over JSON data events with optional validation

        Args:
            model_class: Optional Pydantic model class for validation

        Yields:
            dict: JSON data events
        """
        for event in self.iter_events():
            if event["type"] == "data" and event.get("is_json", True):
                try:
                    if model_class:
                        data = model_class.model_validate_json(event["raw"])
                        yield {"type": "data", "data": data, "raw": event["raw"]}
                    else:
                        yield event
                except Exception as e:
                    self.debug_log(f"数据验证失败: {e}")
                    continue

    def close(self) -> None:
        """Close the response connection"""
        if hasattr(self.response, "close"):
            self.response.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()
