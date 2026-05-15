from typing import Any
from anthropic import Anthropic
from dotenv import load_dotenv
import httpx
import json
import os

load_dotenv()
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_ssl_verify = os.environ.get("ANTHROPIC_SSL_VERIFY", "1").lower() not in ("0", "false", "no")


class AnthropicClient:
    def __init__(self, api_key: str = API_KEY) -> None:
        self._client = Anthropic(
            api_key=api_key,
            http_client=httpx.Client(verify=_ssl_verify),
        )

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
    
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Single-turn completion that returns a parsed JSON object."""
        resp = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate any text blocks (there should be exactly one).
        text = "".join(b.text for b in resp.content if b.type == "text").strip()

        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"extractor returned non-JSON: {text[:200]}") from e