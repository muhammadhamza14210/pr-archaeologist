from typing import Any
from anthropic import Anthropic
from dotenv import load_dotenv
import os

load_dotenv() 
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class AnthropicClient:
    def __init__(self, api_key: str = API_KEY) -> None:
        self._client = Anthropic(api_key=api_key)

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resp = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
        )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )

        return {
            "stop_reason": resp.stop_reason,
            "text": "\n".join(text_parts),
            "tool_calls": tool_calls,
            "raw_assistant_content": [b.model_dump() for b in resp.content],
        }