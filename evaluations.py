"""Run repeatable LangSmith evaluations against the local agent server."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Iterable, Mapping
from typing import Any

from dotenv import load_dotenv
from langgraph_sdk import get_client
from langsmith import aevaluate


def _run_outputs(run: Any) -> Mapping[str, Any]:
    if hasattr(run, "outputs"):
        return run.outputs or {}
    if isinstance(run, Mapping):
        return run.get("outputs") or {}
    return {}


def _example_outputs(example: Any) -> Mapping[str, Any]:
    if hasattr(example, "outputs"):
        return example.outputs or {}
    if isinstance(example, Mapping):
        return example.get("outputs") or {}
    return {}


def _collect_tool_names(value: Any) -> list[str]:
    names: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            calls = item.get("tool_calls", [])
            if isinstance(calls, list):
                for call in calls:
                    if not isinstance(call, Mapping):
                        continue
                    function = call.get("function", {})
                    name = call.get("name")
                    if not name and isinstance(function, Mapping):
                        name = function.get("name")
                    if isinstance(name, str) and name:
                        names.append(name)
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return list(dict.fromkeys(names))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def _evaluation_output(chunks: Iterable[Any]) -> dict[str, Any]:
    final_messages: list[Any] = []
    tool_names: list[str] = []

    for chunk in chunks:
        if isinstance(chunk, Mapping):
            event = chunk.get("event", chunk.get("type"))
            data = chunk.get("data", {})
        else:
            event = getattr(chunk, "event", None)
            data = getattr(chunk, "data", {})

        tool_names.extend(_collect_tool_names(data))
        if event == "values" and isinstance(data, Mapping):
            messages = data.get("messages")
            if isinstance(messages, list):
                final_messages = messages

    answer = ""
    for message in reversed(final_messages):
        if not isinstance(message, Mapping):
            continue
        if message.get("type", message.get("role")) not in {"ai", "assistant"}:
            continue
        answer = _content_text(message.get("content", ""))
        if answer.strip():
            break

    return {"answer": answer, "tool_calls": list(dict.fromkeys(tool_names))}


async def run_agent(
    inputs: Mapping[str, Any],
    *,
    url: str = "http://127.0.0.1:2024",
    assistant_id: str = "agent",
) -> dict[str, Any]:
    """Run one dataset question and return the answer and observed tools."""
    question = inputs.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Each evaluation example needs a non-empty 'question'.")

    async with get_client(url=url) as client:
        thread = await client.threads.create()
        chunks = client.runs.stream(
            thread_id=thread["thread_id"],
            assistant_id=assistant_id,
            input={"messages": [{"role": "user", "content": question}]},
            stream_mode=["values", "debug"],
            stream_subgraphs=True,
        )
        return _evaluation_output([chunk async for chunk in chunks])


def required_tools(run: Any, example: Any) -> dict[str, Any]:
    """Score whether every tool named by the example appeared in the trace."""
    expected = _example_outputs(example).get("required_tools", [])
    actual = _run_outputs(run).get("tool_calls", [])
    if not isinstance(expected, list) or not isinstance(actual, list):
        return {"score": 0, "comment": "Tool expectations or observed calls are malformed."}
    missing = [name for name in expected if name not in actual]
    return {
        "score": 0 if missing else 1,
        "comment": f"Missing required tools: {missing}" if missing else "All required tools were observed.",
    }


def required_facts(run: Any, example: Any) -> dict[str, Any]:
    """Score whether the final response contains the example's required facts."""
    expected = _example_outputs(example).get("required_facts", [])
    answer = _run_outputs(run).get("answer", "")
    if not isinstance(expected, list) or not isinstance(answer, str):
        return {"score": 0, "comment": "Fact expectations or response are malformed."}
    answer_lower = answer.casefold()
    missing = [fact for fact in expected if not isinstance(fact, str) or fact.casefold() not in answer_lower]
    return {
        "score": 0 if missing else 1,
        "comment": f"Required facts not found: {missing}" if missing else "All required facts were found.",
    }


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="LangSmith dataset name or ID")
    parser.add_argument(
        "--url",
        default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:2024"),
        help="LangGraph server URL (default: LANGGRAPH_URL or localhost:2024)",
    )
    parser.add_argument("--assistant-id", default="agent")
    parser.add_argument("--max-concurrency", type=int, default=1)
    args = parser.parse_args()

    async def target(inputs: Mapping[str, Any]) -> dict[str, Any]:
        return await run_agent(inputs, url=args.url, assistant_id=args.assistant_id)

    results = await aevaluate(
        target,
        data=args.dataset,
        evaluators=[required_tools, required_facts],
        experiment_prefix="deep-sales-assistant",
        description="Regression evaluation for tool selection and required response facts.",
        max_concurrency=args.max_concurrency,
    )
    print(f"Experiment: {results.experiment_name}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(_main())