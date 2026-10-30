"""Run repeatable LangSmith evaluations against the local agent server."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from langgraph_sdk import get_client
from langsmith import aevaluate
from pydantic import BaseModel, Field

from tools.sql import _read_only_connection


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


def _collect_tool_calls(value: Any) -> list[dict[str, Any]]:
    """Every tool call in the streamed chunks, in the order first seen.

    The same call shows up in many chunks (each `values` chunk repeats the
    whole message list), so calls are deduplicated by their id. Handles both
    LangChain (`name`/`args`) and OpenAI (`function.name`/`arguments`) shapes.
    """
    calls: dict[str, dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            tool_calls = item.get("tool_calls", [])
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    if not isinstance(call, Mapping):
                        continue
                    function = call.get("function")
                    function = function if isinstance(function, Mapping) else {}
                    name = call.get("name") or function.get("name")
                    args = call.get("args", function.get("arguments"))
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"raw": args}
                    if not isinstance(name, str) or not name:
                        continue
                    args = dict(args) if isinstance(args, Mapping) else {}
                    key = call.get("id") or json.dumps([name, args], sort_keys=True, default=str)
                    calls.setdefault(str(key), {"name": name, "args": args})
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return list(calls.values())


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


def _collect_pending_actions(value: Any) -> list[dict[str, Any]]:
    """Find the tool calls waiting for Jane's approval.

    An approval gate interrupts with `{"action_requests": [{"name", "args",
    ...}], "review_configs": [...]}`. It can appear in a streamed `values`
    chunk (under `__interrupt__`), in a debug event, or in the thread state,
    so search everything.
    """
    actions: dict[str, dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            requests = item.get("action_requests")
            if isinstance(requests, list):
                for request in requests:
                    if not isinstance(request, Mapping):
                        continue
                    name, args = request.get("name"), request.get("args")
                    if isinstance(name, str) and isinstance(args, Mapping):
                        action = {"name": name, "args": dict(args)}
                        actions.setdefault(json.dumps(action, sort_keys=True, default=str), action)
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return list(actions.values())


def _evaluation_output(chunks: Iterable[Any], state: Any = None) -> dict[str, Any]:
    final_messages: list[Any] = []
    chunk_data: list[Any] = []

    for chunk in chunks:
        if isinstance(chunk, Mapping):
            event = chunk.get("event", chunk.get("type"))
            data = chunk.get("data", {})
        else:
            event = getattr(chunk, "event", None)
            data = getattr(chunk, "data", {})

        chunk_data.append(data)
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

    trajectory = _collect_tool_calls(chunk_data)
    return {
        "answer": answer,
        "tool_calls": list(dict.fromkeys(call["name"] for call in trajectory)),
        "trajectory": trajectory,
        "pending_actions": _collect_pending_actions([chunk_data, state]),
    }


async def run_agent(
    inputs: Mapping[str, Any],
    *,
    url: str = "http://127.0.0.1:2024",
    assistant_id: str = "agent",
) -> dict[str, Any]:
    """Run one dataset question and return the answer, observed tools, and
    any tool calls left waiting for approval."""
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
        collected = [chunk async for chunk in chunks]
        # A run stops at the first approval gate and is never resumed here, so
        # gated writes (add_customer, mail_create_draft) never execute during
        # an evaluation. Their requested arguments are scored instead.
        state = await client.threads.get_state(thread["thread_id"])
        return _evaluation_output(collected, state)


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


def expected_pending_action(run: Any, example: Any) -> dict[str, Any]:
    """Score whether the run stopped for approval of the expected tool call.

    The example's `pending_action` names the gated tool and, optionally, args
    to check. A string arg passes if the expected text appears in the actual
    value (case-insensitive), so "a@b.example" matches "Ann <a@b.example>".
    """
    expected = _example_outputs(example).get("pending_action")
    if expected is None:
        return {"score": None, "comment": "No pending action expected."}
    actions = _run_outputs(run).get("pending_actions") or []
    if not actions:
        return {"score": 0, "comment": f"Run finished without asking to approve {expected['name']}."}

    def matches(action: Mapping[str, Any]) -> bool:
        if action.get("name") != expected["name"]:
            return False
        args = action.get("args") or {}
        for key, want in (expected.get("args") or {}).items():
            got = args.get(key)
            if isinstance(want, str):
                if not isinstance(got, str) or want.casefold() not in got.casefold():
                    return False
            elif got != want:
                return False
        return True

    if any(matches(a) for a in actions):
        return {"score": 1, "comment": f"Paused for approval of {expected['name']} as expected."}
    observed = [{"name": a.get("name"), "args": a.get("args")} for a in actions]
    return {"score": 0, "comment": f"Expected {expected}, but the run paused for {observed}."}


# The rfq-quote skill's pricing rule: 10% off orders of 50 or more tracks.
DISCOUNT_THRESHOLD = 50
DISCOUNT_RATE = Decimal("0.10")
_CENT = Decimal("0.01")
_MONEY = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(?![\d])")


def expected_quote(lines: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Price a quote from the database, the way the rfq-quote skill says to.

    Each line is `{"genre": <Genre.Name>, "quantity": <n>}`. Raises ValueError
    for a line that can't be priced exactly (an unknown genre, mixed prices,
    or more tracks than the genre has), since that's a bad example, not an
    agent failure.
    """
    conn = _read_only_connection()
    try:
        priced = []
        for line in lines:
            genre, quantity = line["genre"], int(line["quantity"])
            rows = conn.execute(
                "SELECT t.UnitPrice AS price, COUNT(*) AS n FROM Track t "
                "JOIN Genre g ON g.GenreId = t.GenreId WHERE g.Name = ? "
                "GROUP BY t.UnitPrice",
                (genre,),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError(f"Genre {genre!r} doesn't have exactly one track price.")
            if rows[0]["n"] < quantity:
                raise ValueError(f"Genre {genre!r} has only {rows[0]['n']} tracks.")
            unit = Decimal(str(rows[0]["price"]))
            priced.append({"genre": genre, "quantity": quantity, "unit_price": unit, "total": unit * quantity})
    finally:
        conn.close()

    quantity = sum(p["quantity"] for p in priced)
    subtotal = sum((p["total"] for p in priced), Decimal("0"))
    discount = Decimal("0")
    if quantity >= DISCOUNT_THRESHOLD:
        discount = (subtotal * DISCOUNT_RATE).quantize(_CENT, rounding=ROUND_HALF_UP)
    return {
        "lines": priced,
        "quantity": quantity,
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
    }


def _money_amounts(text: str) -> list[Decimal]:
    return [Decimal(f"{whole.replace(',', '')}.{cents}") for whole, cents in _MONEY.findall(text)]


def _draft(outputs: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The args of the draft waiting for approval, if the run reached one."""
    drafts = [a for a in outputs.get("pending_actions") or [] if a.get("name") == "mail_create_draft"]
    return (drafts[-1].get("args") or {}) if drafts else None


def _reply(outputs: Mapping[str, Any]) -> tuple[str, str]:
    """Return ("draft", body) if a draft was reached, else ("answer", answer)."""
    draft = _draft(outputs)
    if draft is not None:
        return "draft", str(draft.get("body", ""))
    return "answer", str(outputs.get("answer", ""))


def quote_accuracy(run: Any, example: Any) -> dict[str, Any]:
    """Score whether the quote's grand total matches the database's prices.

    Reads the body of the draft waiting for approval (or the final answer if
    no draft was reached) and looks for the correct total, allowing one cent
    for rounding. Below the discount threshold, a discounted total also
    fails: the subtotal is shown either way, so only the wrong total can tell
    the two apart.
    """
    spec = _example_outputs(example).get("quote")
    if spec is None:
        return {"score": None, "comment": "No quote expected."}
    quote = expected_quote(spec["lines"])

    source, text = _reply(_run_outputs(run))
    amounts = _money_amounts(text)
    total = quote["total"]
    summary = f"expected total ${total} for {quote['quantity']} tracks"
    if not any(abs(a - total) <= _CENT for a in amounts):
        return {"score": 0, "comment": f"The {source} doesn't contain the {summary}. Amounts found: {[str(a) for a in amounts]}"}

    if not quote["discount"]:
        wrong = (quote["subtotal"] * (1 - DISCOUNT_RATE)).quantize(_CENT, rounding=ROUND_HALF_UP)
        if any(abs(a - wrong) <= _CENT for a in amounts):
            return {"score": 0, "comment": f"The {source} applies a discount below {DISCOUNT_THRESHOLD} tracks (${wrong}); {summary}."}

    return {"score": 1, "comment": f"The {source} has the {summary}."}


def _customer_exists(email: str) -> bool:
    conn = _read_only_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM Customer WHERE lower(Email) = lower(?)", (email,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def tool_call_order(run: Any, example: Any) -> dict[str, Any]:
    """Score whether the agent did the safety steps before each gated write.

    Like the course's schema-before-query check, these rules hold for every
    run, not just ones whose example asks for them:
    - before `add_customer`, chinook-analyst searched for the customer (a
      `query_chinook` whose SQL mentions their email or last name), and the
      email really isn't in the database;
    - before a `mail_create_draft` whose body has prices, quote-reviewer was
      called (`task` with subagent_type "quote-reviewer").
    The pending call (the one waiting for approval) counts as the last step.
    """
    outputs = _run_outputs(run)
    calls = list(outputs.get("trajectory") or [])
    for action in outputs.get("pending_actions") or []:
        if action not in calls:
            calls.append(action)

    checked: list[str] = []
    problems: list[str] = []
    for i, call in enumerate(calls):
        args, before = call.get("args") or {}, calls[:i]
        if call.get("name") == "add_customer":
            email = str(args.get("email", ""))
            needles = [n.casefold() for n in (email, str(args.get("last_name", ""))) if n]
            checked.append(f"add_customer({email})")
            searched = any(
                c.get("name") == "query_chinook"
                and any(n in str((c.get("args") or {}).get("sql", "")).casefold() for n in needles)
                for c in before
            )
            if not searched:
                problems.append(f"add_customer({email}) ran without first searching for the customer.")
            if email and _customer_exists(email):
                problems.append(f"add_customer({email}) for a customer who already exists.")
        elif call.get("name") == "mail_create_draft" and _money_amounts(str(args.get("body", ""))):
            checked.append(f"mail_create_draft({args.get('to', '')})")
            reviewed = any(
                c.get("name") == "task" and (c.get("args") or {}).get("subagent_type") == "quote-reviewer"
                for c in before
            )
            if not reviewed:
                problems.append("A priced draft was saved without quote-reviewer checking it first.")

    if not checked:
        return {"score": None, "comment": "No gated writes to check."}
    if problems:
        return {"score": 0, "comment": " ".join(problems)}
    return {"score": 1, "comment": f"Safety steps done before: {', '.join(checked)}."}


# --- LLM-as-judge -----------------------------------------------------------
# These call a model, so unit tests replace `_judge` with a fake.


def _judge(schema: type[BaseModel]) -> Any:
    """A judge model that answers with `schema`."""
    from models import strong_model

    return strong_model.with_structured_output(schema)


def _quote_reference(example: Any) -> str:
    """The correct quote for the judge to compare against, if the example has one."""
    spec = _example_outputs(example).get("quote")
    if spec is None:
        return "No reference quote for this request."
    quote = expected_quote(spec["lines"])
    lines = [
        f"- {p['quantity']} {p['genre']} tracks x ${p['unit_price']} = ${p['total']}"
        for p in quote["lines"]
    ]
    if quote["discount"]:
        lines.append(f"- Volume discount (10%, {DISCOUNT_THRESHOLD}+ tracks): -${quote['discount']}")
    lines.append(f"- Grand total: ${quote['total']}")
    return "\n".join(lines)


def _inputs_question(example: Any) -> str:
    inputs = example.inputs if hasattr(example, "inputs") else (example or {}).get("inputs", {})
    return str((inputs or {}).get("question", ""))


class DraftReview(BaseModel):
    """A checklist review of one quote reply, from the rfq-quote skill's step 6."""

    thanks_customer: bool = Field(description="The reply thanks the customer.")
    itemized: bool = Field(
        description="Every requested item has its own line with description, quantity, unit price, and line total."
    )
    discount_correct: bool = Field(
        description="A discount that applies is shown as its own line; if none applies, none is claimed."
    )
    grand_total: bool = Field(description="The grand total is stated clearly.")
    next_step: bool = Field(description="It suggests a concrete next step for the customer.")
    tone: bool = Field(description="Friendly, professional, and concise, written as Jane.")
    no_overpromising: bool = Field(
        description="It promises nothing beyond the quote: no invented terms, deadlines, or licences, and no claim that anything was sent or processed."
    )
    issues: list[str] = Field(description="One short sentence per failed check.")


_DRAFT_CHECKS = [name for name in DraftReview.model_fields if name != "issues"]

DRAFT_JUDGE_PROMPT = """You review reply drafts that Jane Peacock, a sales \
support agent at the Chinook online music store, is about to send to \
customers who asked for a price quote. Judge the draft against each check. \
Use the reference quote for the correct numbers; don't recompute prices \
yourself. Be strict: a check passes only if the draft clearly meets it."""


def draft_quality(run: Any, example: Any) -> dict[str, Any]:
    """LLM-as-judge: score the draft reply against the rfq-quote checklist.

    The score is the fraction of checks passed; the comment lists failures.
    """
    draft = _draft(_run_outputs(run))
    if draft is None:
        return {"score": None, "comment": "No draft reply to judge."}

    review: DraftReview = _judge(DraftReview).invoke(
        [
            ("system", DRAFT_JUDGE_PROMPT),
            (
                "human",
                f"Customer request:\n{_inputs_question(example)}\n\n"
                f"Reference quote:\n{_quote_reference(example)}\n\n"
                f"Draft to: {draft.get('to', '')}\nSubject: {draft.get('subject', '')}\n\n"
                f"{draft.get('body', '')}",
            ),
        ]
    )
    failed = [name for name in _DRAFT_CHECKS if not getattr(review, name)]
    score = round((len(_DRAFT_CHECKS) - len(failed)) / len(_DRAFT_CHECKS), 3)
    if not failed:
        return {"score": score, "comment": "Passed every check."}
    return {"score": score, "comment": f"Failed: {', '.join(failed)}. {' '.join(review.issues)}"}


class PairwiseVerdict(BaseModel):
    preferred: Literal[0, 1, 2] = Field(description="1 if reply A is better, 2 if reply B is better, 0 if they're about equal.")
    reason: str = Field(description="One or two sentences explaining the verdict.")


PAIRWISE_PROMPT = """You compare two replies the Chinook sales assistant \
produced for the same customer request. Pick the one Jane could send with \
less editing: correct prices first (use the reference quote), then \
completeness (every item, discount, total, next step), then concise, \
friendly wording. A shorter reply isn't better if it leaves something out. \
Reply order is random; don't favour either position."""


def draft_preference(runs: list[Any], example: Any) -> dict[str, Any]:
    """Pairwise LLM-as-judge: which of two experiments' replies is better.

    With repetitions, each experiment has several runs per example; the
    first run of each experiment is compared.
    """
    first_by_experiment: dict[Any, Any] = {}
    for run in runs:
        first_by_experiment.setdefault(getattr(run, "session_id", run.id), run)
    pair = list(first_by_experiment.values())
    if len(pair) != 2:
        raise ValueError(f"draft_preference compares exactly two experiments, got {len(pair)}.")

    replies = [_reply(r.outputs or {}) for r in pair]
    if not any(text.strip() for _, text in replies):
        return {"key": "draft_preference", "scores": {r.id: 0 for r in pair}, "comment": "Neither run produced a reply."}

    verdict: PairwiseVerdict = _judge(PairwiseVerdict).invoke(
        [
            ("system", PAIRWISE_PROMPT),
            (
                "human",
                f"Customer request:\n{_inputs_question(example)}\n\n"
                f"Reference quote:\n{_quote_reference(example)}\n\n"
                f"Reply A ({replies[0][0]}):\n{replies[0][1]}\n\n"
                f"Reply B ({replies[1][0]}):\n{replies[1][1]}",
            ),
        ]
    )
    scores = {pair[0].id: int(verdict.preferred == 1), pair[1].id: int(verdict.preferred == 2)}
    return {"key": "draft_preference", "scores": scores, "comment": verdict.reason}


# --- Experiment metadata ----------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

# Everything that changes the agent's behaviour: code, prompts, and playbooks.
_AGENT_FILES = (
    "agent.py", "subagents.py", "models.py", "async_research.py",
    "newsletter_agent_graph.py", "AGENTS.md", "tools/*.py", "skills/**/*",
)


def agent_fingerprint(root: Path = PROJECT_DIR) -> str:
    """A short hash of the agent's code, prompts, and skills.

    Unlike the git SHA, it also changes for uncommitted edits, so two
    experiments with the same fingerprint ran the same agent.
    """
    digest = hashlib.sha256()
    paths = sorted({p for pattern in _AGENT_FILES for p in root.glob(pattern) if p.is_file()})
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def experiment_metadata() -> dict[str, Any]:
    """What ran, so experiments can be compared and filtered in LangSmith."""
    from models import model, strong_model

    return {
        "git_sha": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "agent_fingerprint": agent_fingerprint(),
        "model": getattr(model, "model", None) or getattr(model, "model_name", None),
        "strong_model": getattr(strong_model, "model", None) or getattr(strong_model, "model_name", None),
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
    parser.add_argument(
        "--repetitions", type=int, default=3,
        help="Runs per example; agents vary from run to run (default: 3)",
    )
    parser.add_argument(
        "--experiment-prefix", default="deep-sales-assistant",
        help="Name experiments by what you changed, e.g. 'analyst-on-sonnet'",
    )
    parser.add_argument("--no-judge", action="store_true", help="Skip the LLM-as-judge evaluator")
    args = parser.parse_args()

    async def target(inputs: Mapping[str, Any]) -> dict[str, Any]:
        return await run_agent(inputs, url=args.url, assistant_id=args.assistant_id)

    evaluators = [required_tools, required_facts, expected_pending_action, quote_accuracy, tool_call_order]
    if not args.no_judge:
        evaluators.append(draft_quality)

    metadata = experiment_metadata()
    if metadata["git_dirty"]:
        print("Note: uncommitted changes; agent_fingerprint identifies this version.")
    results = await aevaluate(
        target,
        data=args.dataset,
        evaluators=evaluators,
        experiment_prefix=args.experiment_prefix,
        description="Regression evaluation for tool selection, response facts, approval requests, quote prices, tool-call order, and draft quality.",
        metadata=metadata,
        num_repetitions=args.repetitions,
        max_concurrency=args.max_concurrency,
    )
    print(f"Experiment: {results.experiment_name}")
    print(f"Compare two experiments: uv run python evals/compare.py {results.experiment_name} <other-experiment>")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(_main())