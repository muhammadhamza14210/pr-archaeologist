"""The query agent: a single ReAct-style tool-use loop."""

import json
import sqlite3
from typing import Any
from rich.console import Console
from pr_arch.agent.prompts import SYSTEM_PROMPT
from pr_arch.agent.tools import TOOL_EXECUTORS, TOOL_SCHEMAS
from pr_arch.llm.anthropic import AnthropicClient

MAX_TURNS = 6 


def answer_question(
    llm: AnthropicClient,
    conn: sqlite3.Connection,
    question: str,
    console: Console,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]

    for turn in range(1, MAX_TURNS + 1):
        reply = llm.chat(SYSTEM_PROMPT, messages, TOOL_SCHEMAS)

        messages.append({"role": "assistant", "content": reply["raw_assistant_content"]})

        if reply["stop_reason"] != "tool_use":
            return reply["text"]

        # Execute every requested tool call and feed results back.
        tool_results: list[dict[str, Any]] = []
        for call in reply["tool_calls"]:
            name, tool_input = call["name"], call["input"]
            console.print(f"[dim]  → {name}({json.dumps(tool_input)})[/dim]")

            executor = TOOL_EXECUTORS.get(name)
            if executor is None:
                result: Any = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = executor(conn, **tool_input)
                    console.print(f"[dim]    {len(result)} result(s)[/dim]")
                except Exception as e:  # noqa: BLE001 — surface tool errors to the model
                    result = {"error": str(e)}
                    console.print(f"[red]    tool error: {e}[/red]")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

    return "[reached max turns without a final answer]"